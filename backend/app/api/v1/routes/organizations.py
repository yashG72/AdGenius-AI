"""Organization (workspace) and membership endpoints."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUserDep, DbSessionDep, OrgAdminDep, OrgMemberDep
from app.models import Membership, MembershipRole, User
from app.schemas.common import ListResponse
from app.schemas.organization import (
    MemberAdd,
    MemberRead,
    MemberRoleUpdate,
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationWithRole,
)
from app.services import organization_service

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _member(membership: Membership, user: User) -> MemberRead:
    return MemberRead(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        joined_at=membership.created_at,
    )


@router.post("", response_model=OrganizationWithRole, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate, user: CurrentUserDep, session: DbSessionDep
) -> OrganizationWithRole:
    """Create a workspace. The creator becomes its owner."""
    organization = await organization_service.create_organization(session, user, data)
    await session.refresh(organization)
    return OrganizationWithRole.build(organization, MembershipRole.OWNER)


@router.get("", response_model=ListResponse[OrganizationWithRole])
async def list_organizations(
    user: CurrentUserDep, session: DbSessionDep
) -> ListResponse[OrganizationWithRole]:
    """Only organizations the current user belongs to."""
    rows = await organization_service.list_user_organizations(session, user.id)
    return ListResponse(items=[OrganizationWithRole.build(org, role) for org, role in rows])


@router.get("/{organization_id}", response_model=OrganizationWithRole)
async def get_organization(membership: OrgMemberDep) -> OrganizationWithRole:
    return OrganizationWithRole.build(membership.organization, membership.role)


@router.patch("/{organization_id}", response_model=OrganizationWithRole)
async def update_organization(
    data: OrganizationUpdate, membership: OrgAdminDep, session: DbSessionDep
) -> OrganizationWithRole:
    organization = await organization_service.update_organization(
        session, membership.organization, data
    )
    return OrganizationWithRole.build(organization, membership.role)


# ---------- Members ----------


@router.get("/{organization_id}/members", response_model=ListResponse[MemberRead])
async def list_members(membership: OrgMemberDep, session: DbSessionDep) -> ListResponse[MemberRead]:
    rows = await organization_service.list_members(session, membership.organization_id)
    return ListResponse(items=[_member(m, u) for m, u in rows])


@router.post(
    "/{organization_id}/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED
)
async def add_member(data: MemberAdd, actor: OrgAdminDep, session: DbSessionDep) -> MemberRead:
    """Add an existing registered user by email (email invitations come later)."""
    membership, user = await organization_service.add_member(session, actor, data.email, data.role)
    await session.refresh(membership)
    return _member(membership, user)


@router.patch("/{organization_id}/members/{user_id}", response_model=MemberRead)
async def change_member_role(
    user_id: uuid.UUID, data: MemberRoleUpdate, actor: OrgAdminDep, session: DbSessionDep
) -> MemberRead:
    membership, user = await organization_service.change_member_role(
        session, actor, user_id, data.role
    )
    return _member(membership, user)


@router.delete("/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(user_id: uuid.UUID, actor: OrgMemberDep, session: DbSessionDep) -> None:
    """Admins remove others; any member can remove themselves (leave)."""
    await organization_service.remove_member(session, actor, user_id)
