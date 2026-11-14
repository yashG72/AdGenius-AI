"""Health endpoints.

- /health        liveness:  "is the process up?" (no external calls, always fast)
- /health/ready  readiness: "can it serve traffic?" (checks dependencies; 503 if not)

Later phases add Redis and Qdrant to the readiness checks.
"""

import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSessionDep, SettingsDep
from app.core.exceptions import ServiceUnavailableError
from app.schemas.common import ErrorResponse, HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse, summary="Liveness check")
async def health_check(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness check (database connectivity)",
    responses={503: {"model": ErrorResponse, "description": "A dependency is down"}},
)
async def readiness_check(session: DbSessionDep) -> ReadinessResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Readiness check: database unavailable (%s)", type(exc).__name__)
        raise ServiceUnavailableError(
            "Database is unavailable.", details={"database": "unavailable"}
        ) from exc
    return ReadinessResponse(status="ok", checks={"database": "ok"})
