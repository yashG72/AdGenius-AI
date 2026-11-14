"""Schemas shared across the API."""

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ListResponse(BaseModel, Generic[T]):
    """Envelope for collections: `{"items": [...]}`.

    Using an object (not a bare list) lets pagination fields (total, cursor) be added
    later without breaking clients.
    """

    items: list[T]


class PageResponse(ListResponse[T], Generic[T]):
    """A page of a larger collection (offset pagination)."""

    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """Shape of every error response (documented in OpenAPI)."""

    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ok"]
    checks: dict[str, str]
