"""Document knowledge-base endpoints.

Upload returns immediately with status "pending"; poll GET /documents/{id} to watch it
move to "processing" and then "indexed" (or "failed" with an error_message).
Permissions: members upload, view and reindex; deleting requires admin.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status

from app.api.deps import CurrentUserDep, DbSessionDep, SettingsDep
from app.core.exceptions import PermissionDeniedError
from app.core.storage import FileStorage, get_storage
from app.models import DocumentStatus, DocumentType, MembershipRole
from app.schemas.common import PageResponse
from app.schemas.document import DocumentRead
from app.services import brand_service, document_service
from app.worker import dispatch

router = APIRouter(tags=["documents"])

StorageDep = Annotated[FileStorage, Depends(get_storage)]


@router.post(
    "/brands/{brand_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF, DOCX, TXT or CSV document",
)
async def upload_document(
    brand_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File(description="PDF, DOCX, TXT or CSV")],
    document_type: Annotated[DocumentType, Form()] = DocumentType.OTHER,
) -> DocumentRead:
    brand, _ = await brand_service.get_brand_for_user(session, brand_id, user.id)
    document = await document_service.upload_document(
        session,
        brand=brand,
        user=user,
        upload=file,
        document_type=document_type,
        storage=storage,
        settings=settings,
    )
    # Queued AFTER the response is sent: a slow/unavailable Redis never delays the user.
    background.add_task(dispatch.enqueue_ingestion, document.id)
    return DocumentRead.model_validate(document)


@router.get("/brands/{brand_id}/documents", response_model=PageResponse[DocumentRead])
async def list_documents(
    brand_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSessionDep,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PageResponse[DocumentRead]:
    await brand_service.get_brand_for_user(session, brand_id, user.id)
    documents, total = await document_service.list_documents(
        session, brand_id, status=status_filter, limit=limit, offset=offset
    )
    return PageResponse(
        items=[DocumentRead.model_validate(d) for d in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep
) -> DocumentRead:
    document, _ = await document_service.get_document_for_user(session, document_id, user.id)
    return DocumentRead.model_validate(document)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSessionDep,
    background: BackgroundTasks,
) -> None:
    document, membership = await document_service.get_document_for_user(
        session, document_id, user.id
    )
    if not membership.role.at_least(MembershipRole.ADMIN):
        raise PermissionDeniedError("Deleting a document requires the admin role.")
    await document_service.mark_deleted(session, document)
    background.add_task(dispatch.enqueue_cleanup, [document.id])


@router.post(
    "/documents/{document_id}/reindex",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run ingestion (e.g. after a failure or a chunking-settings change)",
)
async def reindex_document(
    document_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSessionDep,
    background: BackgroundTasks,
) -> DocumentRead:
    document, _ = await document_service.get_document_for_user(session, document_id, user.id)
    document = await document_service.reset_for_reindex(session, document)
    background.add_task(dispatch.enqueue_ingestion, document.id, force=True)
    return DocumentRead.model_validate(document)
