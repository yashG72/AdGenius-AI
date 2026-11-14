"""Health endpoints.

- /health        liveness:  "is the process up?" (no external calls, always fast)
- /health/ready  readiness: "can it serve traffic?" (checks database, Redis, Qdrant;
                 503 with per-service details if any is down)
"""

import logging
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text

from app.api.deps import DbSessionDep, SettingsDep
from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError
from app.schemas.common import ErrorResponse, HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

Check = Callable[[], Awaitable[None]]


async def _check_redis(settings: Settings) -> None:
    client = redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        await client.ping()
    finally:
        await client.aclose()


async def _check_qdrant(settings: Settings) -> None:
    client = AsyncQdrantClient(url=settings.qdrant_url, timeout=2)
    try:
        await client.get_collections()
    finally:
        await client.close()


def get_readiness_checks(settings: SettingsDep) -> dict[str, Check]:
    """External dependency checks (overridden in tests)."""
    return {
        "redis": partial(_check_redis, settings),
        "qdrant": partial(_check_qdrant, settings),
    }


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
    summary="Readiness check (database, Redis, Qdrant)",
    responses={503: {"model": ErrorResponse, "description": "A dependency is down"}},
)
async def readiness_check(
    session: DbSessionDep,
    checks: Annotated[dict[str, Check], Depends(get_readiness_checks)],
) -> ReadinessResponse:
    async def database() -> None:
        await session.execute(text("SELECT 1"))

    results: dict[str, str] = {}
    for name, check in {"database": database, **checks}.items():
        try:
            await check()
            results[name] = "ok"
        except Exception as exc:
            logger.warning("Readiness check: %s unavailable (%s)", name, type(exc).__name__)
            results[name] = "unavailable"

    if any(state != "ok" for state in results.values()):
        raise ServiceUnavailableError("A required service is unavailable.", details=results)
    return ReadinessResponse(status="ok", checks=results)
