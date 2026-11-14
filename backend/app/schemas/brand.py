"""Brand API schemas.

Validation here is the gatekeeper for the JSONB columns: the database accepts any JSON,
so these models are what guarantee the stored shape is what agents expect.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

# ---------- Reusable field types ----------

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
# Generous but bounded: long enough for real guidelines, small enough to fit LLM prompts.
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)]
ListItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]


class BrandColor(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    hex: HexColor


class Competitor(BaseModel):
    name: Name
    website: HttpUrl | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None


class SocialLink(BaseModel):
    platform: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    url: HttpUrl


# ---------- Shared profile fields ----------


class BrandProfile(BaseModel):
    """All optional profile fields (shared by create and update)."""

    description: LongText | None = None
    industry: ShortText | None = None
    website: HttpUrl | None = None

    product_information: LongText | None = None
    target_audience: LongText | None = None
    brand_personality: LongText | None = None
    brand_voice: LongText | None = None
    positioning: LongText | None = None
    messaging: LongText | None = None

    brand_colors: list[BrandColor] = Field(default_factory=list, max_length=20)
    marketing_objectives: list[ListItem] = Field(default_factory=list, max_length=50)
    content_restrictions: list[ListItem] = Field(
        default_factory=list,
        max_length=50,
        description="Claims/messaging the brand must never use (checked by the Critic agent).",
    )
    competitors: list[Competitor] = Field(default_factory=list, max_length=30)
    social_links: list[SocialLink] = Field(default_factory=list, max_length=20)


# Fields whose DB columns are NOT NULL - `null` in a PATCH would be meaningless.
_NON_NULLABLE = {
    "name",
    "brand_colors",
    "marketing_objectives",
    "content_restrictions",
    "competitors",
    "social_links",
}


class BrandCreate(BrandProfile):
    organization_id: uuid.UUID
    name: Name


class BrandUpdate(BrandProfile):
    """Partial update: only fields present in the request are changed.

    Send `null` to clear a text field; send `[]` to clear a list.
    """

    name: Name | None = None

    # In an update, list fields default to "not provided" rather than [].
    brand_colors: list[BrandColor] | None = Field(default=None, max_length=20)
    marketing_objectives: list[ListItem] | None = Field(default=None, max_length=50)
    content_restrictions: list[ListItem] | None = Field(default=None, max_length=50)
    competitors: list[Competitor] | None = Field(default=None, max_length=30)
    social_links: list[SocialLink] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _reject_null_for_required_fields(self) -> "BrandUpdate":
        explicit_nulls = {
            field
            for field in self.model_fields_set & _NON_NULLABLE
            if getattr(self, field) is None
        }
        if explicit_nulls:
            raise ValueError(f"These fields cannot be null: {', '.join(sorted(explicit_nulls))}")
        return self


class BrandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_by_id: uuid.UUID | None
    name: str
    description: str | None
    industry: str | None
    website: str | None
    product_information: str | None
    target_audience: str | None
    brand_personality: str | None
    brand_voice: str | None
    positioning: str | None
    messaging: str | None
    brand_colors: list[BrandColor]
    marketing_objectives: list[str]
    content_restrictions: list[str]
    competitors: list[Competitor]
    social_links: list[SocialLink]
    created_at: datetime
    updated_at: datetime


class BrandSummary(BaseModel):
    """Lightweight list item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    industry: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime
