"""Authentication and user-profile API schemas."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.schemas.organization import OrganizationWithRole

# Upper bound stops attackers from sending megabyte "passwords" to burn hashing CPU.
NewPassword = Annotated[str, Field(min_length=8, max_length=128)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class _EmailMixin(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _lowercase(cls, value: str) -> str:
        return value.lower()


class RegisterRequest(_EmailMixin):
    password: NewPassword
    full_name: FullName


class LoginRequest(_EmailMixin):
    # No min_length here: the login form shouldn't reveal the password policy.
    password: str = Field(max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: NewPassword


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: FullName | None = None


class MeResponse(UserRead):
    organizations: list[OrganizationWithRole]
    is_demo: bool = Field(
        default=False, description="The shared read-only demo account (UI shows a banner)."
    )
