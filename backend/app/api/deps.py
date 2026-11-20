"""Reusable FastAPI dependencies.

Endpoints declare what they need (`user: CurrentUserDep`, `membership: OrgAdminDep`)
and FastAPI resolves it. Tests swap these out via `app.dependency_overrides`.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.db.session import get_db_session
from app.demo import demo_blocks_request, is_demo_user
from app.models import Membership, MembershipRole, User
from app.services import organization_service

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]

# Reads "Authorization: Bearer <token>" and adds the "Authorize" button to /docs.
# auto_error=False so we return our own error envelope instead of FastAPI's default.
_bearer = HTTPBearer(auto_error=False)


# ---------- Authentication ----------


async def get_current_user(
    request: Request,
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
    # The shared demo account is read-only. Enforced HERE - the one place every
    # authenticated request passes through - so no endpoint can be forgotten.
    if is_demo_user(user, settings) and demo_blocks_request(request.method, request.url.path):
        raise PermissionDeniedError(
            "This is a read-only demo. Create a free account to make changes "
            "and run your own campaigns."
        )
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


# ---------- Organization access (tenant isolation + RBAC) ----------


def require_org_role(minimum: MembershipRole) -> Callable[..., Awaitable[Membership]]:
    """Dependency factory: the current user's membership in `organization_id`.

    `organization_id` is read from the URL path (/organizations/{organization_id}) or,
    when not in the path, from the query string (?organization_id=...).
    """

    async def dependency(
        organization_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep
    ) -> Membership:
        return await organization_service.require_membership(
            session, organization_id, user.id, minimum
        )

    return dependency


OrgMemberDep = Annotated[Membership, Depends(require_org_role(MembershipRole.MEMBER))]
OrgAdminDep = Annotated[Membership, Depends(require_org_role(MembershipRole.ADMIN))]
