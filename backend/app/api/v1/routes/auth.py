"""Authentication and current-user profile endpoints."""

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUserDep, DbSessionDep, SettingsDep
from app.api.rate_limits import (
    DEMO_LOGIN_PER_IP,
    LOGIN_PER_IP,
    PASSWORD_CHANGE,
    REFRESH_PER_IP,
    REGISTER_PER_IP,
    RateLimiterDep,
    humanize_seconds,
    limit_by_ip,
    limit_by_user,
)
from app.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitedError,
    ServiceUnavailableError,
)
from app.core.rate_limit import Limit
from app.demo import demo_ready, get_demo_user, is_demo_user
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserRead,
    UserUpdate,
)
from app.schemas.organization import OrganizationWithRole
from app.services import auth_service, organization_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_by_ip(REGISTER_PER_IP))],
)
async def register(data: RegisterRequest, session: DbSessionDep) -> UserRead:
    user = await auth_service.register_user(session, data)
    return UserRead.model_validate(user)


@router.post(
    "/login", response_model=TokenResponse, dependencies=[Depends(limit_by_ip(LOGIN_PER_IP))]
)
async def login(
    data: LoginRequest, session: DbSessionDep, settings: SettingsDep, limiter: RateLimiterDep
) -> TokenResponse:
    # Brute-force protection per ACCOUNT (the per-IP limit alone misses attacks spread
    # over many IPs). Only failures count; a successful login clears the counter.
    # The lockout answers the same way whether or not the email exists.
    failures = Limit("login-failures", settings.login_max_failures, settings.login_lockout_seconds)
    if settings.rate_limit_enabled:
        state = await limiter.peek(failures, data.email)
        if state.count >= failures.requests:
            raise RateLimitedError(
                "Too many failed sign-in attempts for this account. "
                f"Try again in {humanize_seconds(state.retry_after)}.",
                retry_after=state.retry_after,
            )
    try:
        user = await auth_service.authenticate(session, data.email, data.password)
    except AuthenticationError:
        if settings.rate_limit_enabled:
            await limiter.hit(failures, data.email)
        raise
    if settings.rate_limit_enabled:
        await limiter.reset(failures, data.email)
    return await auth_service.issue_tokens(session, user, settings)


@router.post(
    "/demo",
    response_model=TokenResponse,
    summary="Sign in to the shared read-only demo workspace (no account needed)",
    dependencies=[Depends(limit_by_ip(DEMO_LOGIN_PER_IP))],
)
async def demo_login(session: DbSessionDep, settings: SettingsDep) -> TokenResponse:
    if not settings.demo_enabled:
        raise NotFoundError("The demo is not available on this server.")
    user = await get_demo_user(session, settings)
    if user is None or not await demo_ready(session, user):
        # Seeding runs once after a fresh deploy (the agents need a few minutes).
        raise ServiceUnavailableError(
            "The demo workspace is still being prepared. Please try again in a few minutes."
        )
    return await auth_service.issue_tokens(session, user, settings)


@router.post(
    "/refresh", response_model=TokenResponse, dependencies=[Depends(limit_by_ip(REFRESH_PER_IP))]
)
async def refresh(
    data: RefreshRequest, session: DbSessionDep, settings: SettingsDep
) -> TokenResponse:
    return await auth_service.rotate_refresh_token(session, data.refresh_token, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: RefreshRequest, session: DbSessionDep) -> None:
    await auth_service.logout(session, data.refresh_token)


@router.get("/me", response_model=MeResponse)
async def read_me(user: CurrentUserDep, session: DbSessionDep, settings: SettingsDep) -> MeResponse:
    organizations = await organization_service.list_user_organizations(session, user.id)
    return MeResponse(
        **UserRead.model_validate(user).model_dump(),
        organizations=[OrganizationWithRole.build(org, role) for org, role in organizations],
        is_demo=is_demo_user(user, settings),
    )


@router.patch("/me", response_model=UserRead)
async def update_me(data: UserUpdate, user: CurrentUserDep, session: DbSessionDep) -> UserRead:
    if data.full_name is not None:
        user.full_name = data.full_name
        await session.commit()
    return UserRead.model_validate(user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_by_user(PASSWORD_CHANGE))],
)
async def change_password(
    data: ChangePasswordRequest, user: CurrentUserDep, session: DbSessionDep
) -> None:
    await auth_service.change_password(session, user, data.current_password, data.new_password)
