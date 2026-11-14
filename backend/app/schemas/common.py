"""Schemas shared across the API."""

from typing import Any, Literal

from pydantic import BaseModel


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
