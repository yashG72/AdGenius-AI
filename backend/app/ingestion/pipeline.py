"""Ingestion orchestration: runs inside the Celery worker.

Design points:
- Idempotent: an already-indexed document is skipped (unless force=True); vectors use
  deterministic IDs and old ones are removed first, so re-runs never duplicate data.
- Short DB transactions: status is committed before and after the slow work
  (extraction + embedding), never held open during it.
- Permanent vs transient failures: a broken file (IngestionError) is marked FAILED
  with a readable message and NOT retried. Anything else (Qdrant down, ...) is
  re-raised so Celery retries it with backoff.
- Deletion races: if the document is deleted while being processed, the freshly
  written vectors are removed again.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.storage import FileStorage
from app.ingestion import IngestionError
from app.ingestion.chunking import chunk_pages
from app.ingestion.embeddings import Embedder
from app.ingestion.extractors import extract
from app.ingestion.vector_store import ChunkMetadata, VectorStore
from app.models import BrandDocument, DocumentStatus

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


async def _set_failed(session_factory: SessionFactory, document_id: uuid.UUID, message: str):
    async with session_factory() as session:
        document = await session.get(BrandDocument, document_id)
        if document is not None and document.status is not DocumentStatus.DELETED:
            document.status = DocumentStatus.FAILED
            document.error_message = message[:2000]
            await session.commit()


async def ingest_document(
    document_id: uuid.UUID,
    *,
    session_factory: SessionFactory,
    storage: FileStorage,
    embedder: Embedder,
    vector_store: VectorStore,
    settings: Settings,
    force: bool = False,
) -> DocumentStatus | None:
    # ---- 1. Claim the document ----
    async with session_factory() as session:
        document = await session.get(BrandDocument, document_id, with_for_update=True)
        if document is None:
            logger.warning("Ingestion skipped: document %s not found", document_id)
            return None
        if document.status is DocumentStatus.DELETED:
            return DocumentStatus.DELETED
        if document.status is DocumentStatus.INDEXED and not force:
            return DocumentStatus.INDEXED  # duplicate task delivery: nothing to do

        document.status = DocumentStatus.PROCESSING
        document.error_message = None
        document.ingestion_attempts += 1
        await session.commit()

        meta = ChunkMetadata(
            organization_id=document.organization_id,
            brand_id=document.brand_id,
            document_id=document.id,
            document_type=document.document_type.value,
            original_filename=document.original_filename,
        )
        path = storage.local_path(document.storage_key)
        file_format = document.file_format

    # ---- 2. Extract, chunk, embed, index (no DB transaction open) ----
    try:
        if not path.exists():
            raise IngestionError("The stored file is missing.")
        pages = await asyncio.to_thread(
            extract, path, file_format, max_pdf_pages=settings.max_pdf_pages
        )
        chunks = await asyncio.to_thread(
            chunk_pages, pages, settings.chunk_size_tokens, settings.chunk_overlap_tokens
        )
        if not chunks:
            raise IngestionError(
                "No extractable text found. Scanned/image-only PDFs need OCR, "
                "which is not supported yet."
            )
        embeddings = await asyncio.to_thread(embedder.embed_documents, [c.text for c in chunks])

        await vector_store.ensure_collection(embedder.dense_dim)
        await vector_store.delete_document(meta.document_id)  # drop stale chunks first
        await vector_store.upsert_chunks(meta, chunks, embeddings)
    except IngestionError as exc:
        logger.info("Document %s failed ingestion: %s", document_id, exc)
        await _set_failed(session_factory, document_id, str(exc))
        return DocumentStatus.FAILED
    except Exception:
        logger.exception("Transient error while ingesting document %s", document_id)
        await _set_failed(session_factory, document_id, "Temporary error; retrying.")
        raise  # let Celery retry

    # ---- 3. Mark indexed (unless deleted meanwhile) ----
    async with session_factory() as session:
        document = await session.get(BrandDocument, document_id, with_for_update=True)
        if document is None or document.status is DocumentStatus.DELETED:
            await vector_store.delete_document(meta.document_id)
            return DocumentStatus.DELETED
        document.status = DocumentStatus.INDEXED
        document.page_count = sum(1 for p in pages if p.page is not None) or None
        document.chunk_count = len(chunks)
        document.indexed_at = datetime.now(UTC)
        await session.commit()

    logger.info("Indexed document %s: %d chunks", document_id, len(chunks))
    return DocumentStatus.INDEXED
