"""Brand profile. Belongs to one organization; campaigns and documents hang off it.

Free-form narrative fields are TEXT. Structured lists (colors, competitors, social links,
objectives, restrictions) are JSONB so AI agents can consume them as data, and their
shape is validated by the Pydantic schemas before they reach the database.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

_EMPTY_JSON_LIST = text("'[]'::jsonb")


def _json_list() -> Mapped[list[Any]]:
    return mapped_column(JSONB, default=list, server_default=_EMPTY_JSON_LIST)


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (
        # Brand names are unique per organization, but only among non-deleted brands,
        # so a deleted brand's name can be reused.
        Index(
            "uq_brands_organization_id_name_active",
            "organization_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # ---------- Identity ----------
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(2048))

    # ---------- Strategy (narrative) ----------
    product_information: Mapped[str | None] = mapped_column(Text)
    target_audience: Mapped[str | None] = mapped_column(Text)
    brand_personality: Mapped[str | None] = mapped_column(Text)
    brand_voice: Mapped[str | None] = mapped_column(Text)
    positioning: Mapped[str | None] = mapped_column(Text)
    messaging: Mapped[str | None] = mapped_column(Text)

    # ---------- Structured (JSONB) ----------
    brand_colors: Mapped[list[dict[str, str]]] = _json_list()  # [{name, hex}]
    marketing_objectives: Mapped[list[str]] = _json_list()
    content_restrictions: Mapped[list[str]] = _json_list()  # enforced by the Critic agent
    competitors: Mapped[list[dict[str, Any]]] = _json_list()  # [{name, website, notes}]
    social_links: Mapped[list[dict[str, str]]] = _json_list()  # [{platform, url}]

    # Soft delete: the row stays so campaign history keeps its brand reference.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Brand {self.name}>"
