"""Organization (tenant / workspace). Every brand, document and campaign belongs to one."""

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.membership import Membership


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255))
    # URL-friendly unique identifier, e.g. "acme-creative".
    slug: Mapped[str] = mapped_column(String(100), unique=True)

    # lazy="raise": accessing this without explicitly loading it raises an error instead of
    # silently firing a query (implicit lazy loading does not work with async sessions).
    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan", lazy="raise"
    )

    def __repr__(self) -> str:
        return f"<Organization {self.slug}>"
