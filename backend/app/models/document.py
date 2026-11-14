"""Uploaded brand documents and their ingestion lifecycle.

Lifecycle:  pending -> processing -> indexed
                             \-> failed   (reindex sends it back to pending)
            any state -> deleted          (file + vectors removed in the background)
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


class DocumentType(enum.StrEnum):
    BRAND_GUIDELINES = "brand_guidelines"
    PRODUCT_CATALOGUE = "product_catalogue"
    PREVIOUS_CAMPAIGN = "previous_campaign"
    MARKETING_STRATEGY = "marketing_strategy"
    CUSTOMER_PERSONA = "customer_persona"
    COMPETITOR_ANALYSIS = "competitor_analysis"
    BRAND_TONE = "brand_tone"
    PRODUCT_SPECIFICATION = "product_specification"
    OTHER = "other"


class DocumentFormat(enum.StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    CSV = "csv"


def _pg_enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda members: [m.value for m in members])


class BrandDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brand_documents"
    __table_args__ = (
        # The same file can't be uploaded twice to one brand (unless the first was deleted).
        Index(
            "uq_brand_documents_brand_id_sha256_active",
            "brand_id",
            "sha256",
            unique=True,
            postgresql_where=text("status <> 'deleted'"),
        ),
    )

    # organization_id is denormalized (also reachable via brand) so tenant filters and
    # vector payloads never need a join.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), index=True
    )
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # ---------- File ----------
    original_filename: Mapped[str] = mapped_column(String(255))  # display only
    file_format: Mapped[DocumentFormat] = mapped_column(_pg_enum(DocumentFormat, "document_format"))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    document_type: Mapped[DocumentType] = mapped_column(
        _pg_enum(DocumentType, "document_type"), default=DocumentType.OTHER
    )

    # ---------- Ingestion ----------
    status: Mapped[DocumentStatus] = mapped_column(
        _pg_enum(DocumentStatus, "document_status"), default=DocumentStatus.PENDING
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    ingestion_attempts: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    page_count: Mapped[int | None]
    chunk_count: Mapped[int | None]
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<BrandDocument {self.original_filename} {self.status}>"
