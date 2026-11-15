"""Brand CRUD with organization-level isolation.

Every query is filtered by organization and by `deleted_at IS NULL`; a brand is only
ever loaded together with proof that the current user belongs to its organization.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Brand, BrandDocument, DocumentStatus, Membership, User
from app.schemas.brand import BrandCreate, BrandUpdate

DUPLICATE_NAME = "A brand with this name already exists in this organization."


def _active_brands() -> Select[tuple[Brand]]:
    return select(Brand).where(Brand.deleted_at.is_(None))


def _escape_like(value: str) -> str:
    """Treat % and _ in user search input literally, not as SQL wildcards."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _name_taken(
    session: AsyncSession,
    organization_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    # Case-insensitive: "Mano" and "MANO" count as the same brand.
    query = select(Brand.id).where(
        Brand.organization_id == organization_id,
        Brand.deleted_at.is_(None),
        func.lower(Brand.name) == name.lower(),
    )
    if exclude_id is not None:
        query = query.where(Brand.id != exclude_id)
    return bool(await session.scalar(query))


# ---------- Reads ----------


async def get_brand_for_user(
    session: AsyncSession, brand_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[Brand, Membership]:
    """Load a brand plus the user's membership in its organization, in ONE query.

    Brand missing, deleted, or in an organization the user doesn't belong to all look
    the same from outside: 404.
    """
    row = (
        await session.execute(
            select(Brand, Membership)
            .join(
                Membership,
                (Membership.organization_id == Brand.organization_id)
                & (Membership.user_id == user_id),
            )
            .where(Brand.id == brand_id, Brand.deleted_at.is_(None))
        )
    ).first()
    if row is None:
        raise NotFoundError("Brand not found.")
    return row[0], row[1]


async def list_brands(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    search: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Brand], int]:
    query = _active_brands().where(Brand.organization_id == organization_id)
    if search:
        query = query.where(Brand.name.ilike(f"%{_escape_like(search)}%", escape="\\"))

    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    brands = await session.scalars(query.order_by(Brand.name, Brand.id).limit(limit).offset(offset))
    return list(brands), total or 0


# ---------- Writes ----------


async def create_brand(session: AsyncSession, user: User, data: BrandCreate) -> Brand:
    if await _name_taken(session, data.organization_id, data.name):
        raise ConflictError(DUPLICATE_NAME)

    # mode="json" turns HttpUrl and nested models into plain JSON-compatible values.
    values = data.model_dump(mode="json", exclude={"organization_id"})
    brand = Brand(organization_id=data.organization_id, created_by_id=user.id, **values)
    session.add(brand)
    try:
        await session.commit()
    except IntegrityError as exc:  # concurrent create with the same name
        await session.rollback()
        raise ConflictError(DUPLICATE_NAME) from exc
    await session.refresh(brand)
    return brand


async def update_brand(session: AsyncSession, brand: Brand, data: BrandUpdate) -> Brand:
    changes = data.model_dump(mode="json", exclude_unset=True)
    new_name = changes.get("name")
    if new_name and await _name_taken(session, brand.organization_id, new_name, brand.id):
        raise ConflictError(DUPLICATE_NAME)

    for field, value in changes.items():
        setattr(brand, field, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(DUPLICATE_NAME) from exc
    await session.refresh(brand)
    return brand


async def delete_brand(session: AsyncSession, brand: Brand) -> None:
    """Soft delete the brand and all its documents.

    The caller queues the background cleanup of vectors and stored files.
    """
    now = datetime.now(UTC)
    brand.deleted_at = now
    await session.execute(
        update(BrandDocument)
        .where(
            BrandDocument.brand_id == brand.id,
            BrandDocument.status != DocumentStatus.DELETED,
        )
        .values(status=DocumentStatus.DELETED, deleted_at=now)
    )
    await session.commit()
