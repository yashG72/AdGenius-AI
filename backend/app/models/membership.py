"""Membership: links a user to an organization with a role (the basis of RBAC)."""

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class MembershipRole(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

    @property
    def rank(self) -> int:
        return _ROLE_RANK[self]

    def at_least(self, other: "MembershipRole") -> bool:
        """Role hierarchy check: OWNER > ADMIN > MEMBER."""
        return self.rank >= other.rank


_ROLE_RANK = {MembershipRole.MEMBER: 1, MembershipRole.ADMIN: 2, MembershipRole.OWNER: 3}


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        # A user can join a given organization only once.
        # (This index also serves lookups by organization_id, its leading column.)
        UniqueConstraint("organization_id", "user_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(
            MembershipRole,
            name="membership_role",
            # store "owner" (the value), not "OWNER" (the Python name)
            values_callable=lambda roles: [r.value for r in roles],
        ),
        default=MembershipRole.MEMBER,
    )

    organization: Mapped["Organization"] = relationship(
        back_populates="memberships", lazy="raise"
    )
    user: Mapped["User"] = relationship(back_populates="memberships", lazy="raise")

    def __repr__(self) -> str:
        return f"<Membership user={self.user_id} org={self.organization_id} role={self.role}>"
