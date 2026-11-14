"""Organization and membership API schemas."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints, field_validator

from app.models import MembershipRole, Organization

OrgName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
# lowercase words separated by single hyphens, e.g. "acme-creative"
Slug = Annotated[
    str,
    StringConstraints(min_length=3, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
]


class OrganizationCreate(BaseModel):
    name: OrgName
    slug: Slug | None = None  # generated from the name when omitted


class OrganizationUpdate(BaseModel):
    name: OrgName | None = None
    slug: Slug | None = None


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # build directly from ORM objects

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime


class OrganizationWithRole(OrganizationRead):
    """An organization as seen by the current user, including their role in it."""

    role: MembershipRole

    @classmethod
    def build(cls, organization: Organization, role: MembershipRole) -> "OrganizationWithRole":
        return cls(**OrganizationRead.model_validate(organization).model_dump(), role=role)


class MemberRead(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: MembershipRole
    joined_at: datetime


class MemberAdd(BaseModel):
    email: EmailStr
    role: MembershipRole = MembershipRole.MEMBER

    @field_validator("email")
    @classmethod
    def _lowercase(cls, value: str) -> str:
        return value.lower()


class MemberRoleUpdate(BaseModel):
    role: MembershipRole
