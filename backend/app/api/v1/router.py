"""Aggregates every v1 route module into a single router."""

from fastapi import APIRouter

from app.api.v1.routes import (
    auth,
    brands,
    documents,
    health,
    knowledge,
    organizations,
    research,
)
from app.schemas.common import ErrorResponse

api_router = APIRouter(
    # Documents the shared error shape on every endpoint in OpenAPI.
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    }
)

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(brands.router)
api_router.include_router(documents.router)
api_router.include_router(knowledge.router)
api_router.include_router(research.router)
