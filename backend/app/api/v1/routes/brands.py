"""Brand endpoints.

Permissions: any organization member can create, view and edit brands;
deleting a brand requires the admin role.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, status

from app.api.deps import CurrentUserDep, DbSessionDep, OrgMemberDep
from app.core.exceptions import PermissionDeniedError
from app.models import MembershipRole
from app.schemas.brand import BrandCreate, BrandRead, BrandSummary, BrandUpdate
from app.schemas.common import PageResponse
from app.services import brand_service, organization_service
from app.worker import dispatch

router = APIRouter(prefix="/brands", tags=["brands"])


@router.post("", response_model=BrandRead, status_code=status.HTTP_201_CREATED)
async def create_brand(data: BrandCreate, user: CurrentUserDep, session: DbSessionDep) -> BrandRead:
    await organization_service.require_membership(session, data.organization_id, user.id)
    brand = await brand_service.create_brand(session, user, data)
    return BrandRead.model_validate(brand)


@router.get("", response_model=PageResponse[BrandSummary])
async def list_brands(
    membership: OrgMemberDep,  # requires ?organization_id=... and membership in it
    session: DbSessionDep,
    search: Annotated[str | None, Query(max_length=100, description="Filter by name")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PageResponse[BrandSummary]:
    brands, total = await brand_service.list_brands(
        session, membership.organization_id, search=search, limit=limit, offset=offset
    )
    return PageResponse(
        items=[BrandSummary.model_validate(b) for b in brands],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{brand_id}", response_model=BrandRead)
async def get_brand(brand_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep) -> BrandRead:
    brand, _ = await brand_service.get_brand_for_user(session, brand_id, user.id)
    return BrandRead.model_validate(brand)


@router.patch("/{brand_id}", response_model=BrandRead)
async def update_brand(
    brand_id: uuid.UUID, data: BrandUpdate, user: CurrentUserDep, session: DbSessionDep
) -> BrandRead:
    brand, _ = await brand_service.get_brand_for_user(session, brand_id, user.id)
    brand = await brand_service.update_brand(session, brand, data)
    return BrandRead.model_validate(brand)


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brand(
    brand_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep, background: BackgroundTasks
) -> None:
    brand, membership = await brand_service.get_brand_for_user(session, brand_id, user.id)
    if not membership.role.at_least(MembershipRole.ADMIN):
        raise PermissionDeniedError("Deleting a brand requires the admin role.")
    await brand_service.delete_brand(session, brand)
    # Remove its vectors + stored files in the background (queued after the response).
    background.add_task(dispatch.enqueue_cleanup, [], brand_id=brand.id)
