"""Document upload, listing, deletion and reindexing (HTTP side).

The heavy lifting (extraction, embedding, indexing) happens in the Celery worker;
this module only validates, stores, records metadata and queues work.
"""

import hashlib
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError, PayloadTooLargeError
from app.core.storage import FileStorage
from app.ingestion.validation import format_from_filename, sanitize_filename, verify_content
from app.models import Brand, BrandDocument, DocumentStatus, DocumentType, Membership, User

_READ_BLOCK = 1024 * 1024  # 1 MiB
DUPLICATE_FILE = "This file has already been uploaded to this brand."


async def _stage_upload(upload: UploadFile, staging_dir: Path, max_bytes: int):
    """Copy the upload to a staging file while hashing it and enforcing the size limit."""
    digest = hashlib.sha256()
    size = 0
    staged = tempfile.NamedTemporaryFile(dir=staging_dir, delete=False)  # noqa: SIM115
    path = Path(staged.name)
    try:
        with staged:
            while block := await upload.read(_READ_BLOCK):
                size += len(block)
                if size > max_bytes:
                    raise PayloadTooLargeError(
                        f"Files may be at most {max_bytes // (1024 * 1024)} MB."
                    )
                digest.update(block)
                await run_in_threadpool(staged.write, block)
    except BaseException:
        # Synchronous on purpose: must also run when the request is being cancelled.
        path.unlink(missing_ok=True)  # noqa: ASYNC240
        raise
    return path, size, digest.hexdigest()


async def upload_document(
    session: AsyncSession,
    *,
    brand: Brand,
    user: User,
    upload: UploadFile,
    document_type: DocumentType,
    storage: FileStorage,
    settings: Settings,
) -> BrandDocument:
    filename = sanitize_filename(upload.filename)
    file_format = format_from_filename(filename)  # 415 before reading anything

    staged, size, sha256 = await _stage_upload(
        upload, storage.temp_dir(), settings.max_upload_size_mb * 1024 * 1024
    )
    try:
        if size == 0:
            raise BadRequestError("The uploaded file is empty.")
        await run_in_threadpool(verify_content, staged, file_format)

        existing = await session.scalar(
            select(BrandDocument.id).where(
                BrandDocument.brand_id == brand.id,
                BrandDocument.sha256 == sha256,
                BrandDocument.status != DocumentStatus.DELETED,
            )
        )
        if existing:
            raise ConflictError(DUPLICATE_FILE, details={"document_id": str(existing)})

        document_id = uuid.uuid4()
        storage_key = f"{brand.organization_id}/{brand.id}/{document_id}.{file_format.value}"
        document = BrandDocument(
            id=document_id,
            organization_id=brand.organization_id,
            brand_id=brand.id,
            uploaded_by_id=user.id,
            original_filename=filename,
            file_format=file_format,
            size_bytes=size,
            sha256=sha256,
            storage_key=storage_key,
            document_type=document_type,
            status=DocumentStatus.PENDING,
        )
        await run_in_threadpool(storage.save, staged, storage_key)
        session.add(document)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            storage.delete(storage_key)
            raise ConflictError(DUPLICATE_FILE) from exc
        await session.refresh(document)
        return document
    finally:
        staged.unlink(missing_ok=True)  # no-op if it was moved into storage


async def get_document_for_user(
    session: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[BrandDocument, Membership]:
    """Document + the user's membership in its org, in one query. Otherwise 404."""
    row = (
        await session.execute(
            select(BrandDocument, Membership)
            .join(Brand, Brand.id == BrandDocument.brand_id)
            .join(
                Membership,
                (Membership.organization_id == BrandDocument.organization_id)
                & (Membership.user_id == user_id),
            )
            .where(
                BrandDocument.id == document_id,
                BrandDocument.status != DocumentStatus.DELETED,
                Brand.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        raise NotFoundError("Document not found.")
    return row[0], row[1]


async def list_documents(
    session: AsyncSession,
    brand_id: uuid.UUID,
    *,
    status: DocumentStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[BrandDocument], int]:
    query = select(BrandDocument).where(
        BrandDocument.brand_id == brand_id, BrandDocument.status != DocumentStatus.DELETED
    )
    if status is not None:
        query = query.where(BrandDocument.status == status)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    documents = await session.scalars(
        query.order_by(BrandDocument.created_at.desc(), BrandDocument.id)
        .limit(limit)
        .offset(offset)
    )
    return list(documents), total or 0


async def mark_deleted(session: AsyncSession, document: BrandDocument) -> None:
    """Hide immediately; the worker removes vectors and the stored file afterwards."""
    document.status = DocumentStatus.DELETED
    document.deleted_at = datetime.now(UTC)
    await session.commit()


async def reset_for_reindex(session: AsyncSession, document: BrandDocument) -> BrandDocument:
    if document.status is DocumentStatus.PROCESSING:
        raise ConflictError("This document is currently being processed.")
    document.status = DocumentStatus.PENDING
    document.error_message = None
    await session.commit()
    await session.refresh(document)
    return document
