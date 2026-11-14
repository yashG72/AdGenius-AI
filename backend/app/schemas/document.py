"""Document API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import DocumentFormat, DocumentStatus, DocumentType


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    brand_id: uuid.UUID
    uploaded_by_id: uuid.UUID | None
    original_filename: str
    file_format: DocumentFormat
    document_type: DocumentType
    size_bytes: int
    sha256: str
    status: DocumentStatus
    error_message: str | None
    ingestion_attempts: int
    page_count: int | None
    chunk_count: int | None
    indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime
