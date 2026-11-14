"""Reusable FastAPI dependencies.

Endpoints declare what they need (`user: CurrentUserDep`, `membership: OrgAdminDep`)
and FastAPI resolves it. Tests swap these out via `app.dependency_overrides`.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, NotFoundError, PermissionDeniedError
from app.core.security import decode_access_token
from app.db.session import get_db_session
from app.models import Membership, MembershipRole, User
from app.services import organization_service

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]

# Reads "Authorization: Bearer <token>" and adds the "Authorize" button to /docs.
# auto_error=False so we return our own error envelope instead of FastAPI's default.
_bearer = HTTPBearer(auto_error=False)


# ---------- Authentication ----------


async def get_current_user(
    session: DbSessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise AuthenticationError()
    user_id = decode_access_token(credentials.credentials, settings)
    # Re-check the database: a deactivated user is locked out even with a valid token.
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired token.")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


# ---------- Organization access (tenant isolation + RBAC) ----------


async def get_org_membership(
    organization_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep
) -> Membership:
    """The current user's membership in the organization from the URL path.

    Non-members get 404 (not 403) so they cannot even learn the organization exists.
    """
    membership = await organization_service.get_membership(session, organization_id, user.id)
    if membership is None:
        raise NotFoundError("Organization not found.")
    return membership


OrgMemberDep = Annotated[Membership, Depends(get_org_membership)]


def require_org_role(minimum: MembershipRole) -> Callable[..., Awaitable[Membership]]:
    """Dependency factory: membership must have at least `minimum` role."""

    async def dependency(membership: OrgMemberDep) -> Membership:
        if not membership.role.at_least(minimum):
            raise PermissionDeniedError(f"This action requires the {minimum.value} role.")
        return membership

    return dependency


OrgAdminDep = Annotated[Membership, Depends(require_org_role(MembershipRole.ADMIN))]
