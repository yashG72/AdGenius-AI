"""Authentication and current-user profile endpoints."""

from fastapi import APIRouter, status

from app.api.deps import CurrentUserDep, DbSessionDep, SettingsDep
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


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, session: DbSessionDep) -> UserRead:
    user = await auth_service.register_user(session, data)
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, session: DbSessionDep, settings: SettingsDep) -> TokenResponse:
    user = await auth_service.authenticate(session, data.email, data.password)
    return await auth_service.issue_tokens(session, user, settings)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    data: RefreshRequest, session: DbSessionDep, settings: SettingsDep
) -> TokenResponse:
    return await auth_service.rotate_refresh_token(session, data.refresh_token, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: RefreshRequest, session: DbSessionDep) -> None:
    await auth_service.logout(session, data.refresh_token)


@router.get("/me", response_model=MeResponse)
async def read_me(user: CurrentUserDep, session: DbSessionDep) -> MeResponse:
    organizations = await organization_service.list_user_organizations(session, user.id)
    return MeResponse(
        **UserRead.model_validate(user).model_dump(),
        organizations=[OrganizationWithRole.build(org, role) for org, role in organizations],
    )


@router.patch("/me", response_model=UserRead)
async def update_me(data: UserUpdate, user: CurrentUserDep, session: DbSessionDep) -> UserRead:
    if data.full_name is not None:
        user.full_name = data.full_name
        await session.commit()
    return UserRead.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: ChangePasswordRequest, user: CurrentUserDep, session: DbSessionDep
) -> None:
    await auth_service.change_password(session, user, data.current_password, data.new_password)
