"""Organizations and memberships, including the role rules (RBAC).

Role rules:
- Any member can view the organization and its member list, and can leave it.
- Admins and owners can rename it and add/remove/re-role members and admins.
- Only owners can grant the owner role or change/remove an existing owner.
- An organization must always keep at least one owner.
"""

import re
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models import Membership, MembershipRole, Organization, User
from app.schemas.organization import OrganizationCreate, OrganizationUpdate

# ---------- Lookups ----------


async def get_membership(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> Membership | None:
    """The user's membership in the org (with the org loaded), or None if not a member."""
    return await session.scalar(
        select(Membership)
        .options(joinedload(Membership.organization))
        .where(Membership.organization_id == organization_id, Membership.user_id == user_id)
    )


async def list_user_organizations(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Organization, MembershipRole]]:
    rows = await session.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == user_id)
        .order_by(Organization.name)
    )
    return [(org, role) for org, role in rows.all()]


# ---------- Organizations ----------


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:90].strip("-")
    return slug if len(slug) >= 3 else f"org-{slug}".strip("-")


async def _slug_taken(session: AsyncSession, slug: str) -> bool:
    return bool(await session.scalar(select(Organization.id).where(Organization.slug == slug)))


async def _available_slug(session: AsyncSession, name: str) -> str:
    base = slugify(name)
    candidate = base
    while await _slug_taken(session, candidate):
        candidate = f"{base}-{secrets.token_hex(3)}"
    return candidate


async def create_organization(
    session: AsyncSession, user: User, data: OrganizationCreate
) -> Organization:
    if data.slug:
        if await _slug_taken(session, data.slug):
            raise ConflictError("This organization slug is already taken.")
        slug = data.slug
    else:
        slug = await _available_slug(session, data.name)

    organization = Organization(name=data.name, slug=slug)
    session.add(organization)
    await session.flush()
    session.add(
        Membership(organization_id=organization.id, user_id=user.id, role=MembershipRole.OWNER)
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("This organization slug is already taken.") from exc
    return organization


async def update_organization(
    session: AsyncSession, organization: Organization, data: OrganizationUpdate
) -> Organization:
    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    new_slug = changes.get("slug")
    if new_slug and new_slug != organization.slug and await _slug_taken(session, new_slug):
        raise ConflictError("This organization slug is already taken.")

    for field, value in changes.items():
        setattr(organization, field, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("This organization slug is already taken.") from exc
    await session.refresh(organization)  # reload server-updated updated_at
    return organization


# ---------- Members ----------


async def list_members(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[tuple[Membership, User]]:
    rows = await session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == organization_id)
        .order_by(Membership.created_at)
    )
    return [(membership, user) for membership, user in rows.all()]


async def _owner_count(session: AsyncSession, organization_id: uuid.UUID) -> int:
    return await session.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.organization_id == organization_id,
            Membership.role == MembershipRole.OWNER,
        )
    )


async def _get_target(
    session: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[Membership, User]:
    row = (
        await session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.organization_id == organization_id, Membership.user_id == user_id)
        )
    ).first()
    if row is None:
        raise NotFoundError("Member not found.")
    return row[0], row[1]


def _require_owner_for(actor: Membership, *roles: MembershipRole) -> None:
    """Only owners may touch the owner role (granting it or acting on an owner)."""
    if MembershipRole.OWNER in roles and actor.role is not MembershipRole.OWNER:
        raise PermissionDeniedError("Only owners can manage owners.")


async def add_member(
    session: AsyncSession, actor: Membership, email: str, role: MembershipRole
) -> tuple[Membership, User]:
    _require_owner_for(actor, role)
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        raise NotFoundError("No user with this email exists.")
    if await get_membership(session, actor.organization_id, user.id):
        raise ConflictError("This user is already a member.")

    membership = Membership(organization_id=actor.organization_id, user_id=user.id, role=role)
    session.add(membership)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("This user is already a member.") from exc
    return membership, user


async def change_member_role(
    session: AsyncSession, actor: Membership, user_id: uuid.UUID, new_role: MembershipRole
) -> tuple[Membership, User]:
    target, user = await _get_target(session, actor.organization_id, user_id)
    _require_owner_for(actor, target.role, new_role)

    if (
        target.role is MembershipRole.OWNER
        and new_role is not MembershipRole.OWNER
        and await _owner_count(session, actor.organization_id) <= 1
    ):
        raise ConflictError("An organization must keep at least one owner.")

    target.role = new_role
    await session.commit()
    await session.refresh(target)
    return target, user


async def remove_member(session: AsyncSession, actor: Membership, user_id: uuid.UUID) -> None:
    target, _ = await _get_target(session, actor.organization_id, user_id)
    is_self = target.user_id == actor.user_id

    if not is_self:
        if not actor.role.at_least(MembershipRole.ADMIN):
            raise PermissionDeniedError("Only admins can remove other members.")
        _require_owner_for(actor, target.role)

    if (
        target.role is MembershipRole.OWNER
        and await _owner_count(session, actor.organization_id) <= 1
    ):
        raise ConflictError("An organization must keep at least one owner.")

    await session.delete(target)
    await session.commit()
