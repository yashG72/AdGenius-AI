"""FastAPI application entry point.

Run locally (from the `backend/` folder):

    uvicorn app.main:app --reload
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    REQUEST_ID_HEADER,
    BodySizeLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.tracing import configure_tracing
from app.db.session import engine
from app.ingestion.vector_store import get_qdrant_client
from app.research.cache import get_redis
from app.worker.inline import runner

logger = logging.getLogger(__name__)


async def _recover_jobs() -> None:
    try:
        await runner.recover(engine)
    except Exception:  # e.g. database still waking up: never block or crash startup
        logger.exception("Could not recover unfinished jobs")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup (the DB pool connects lazily on first query).
    logger.info("Starting %s v%s", app.title, app.version)
    settings = get_settings()
    # Hosts only (never credentials): makes "connected to the wrong place" obvious in logs.
    logger.info(
        "Database host: %s | Qdrant: %s | Redis: %s | jobs: %s | embeddings: %s",
        urlsplit(settings.database_url).hostname,
        urlsplit(settings.qdrant_url).hostname,
        urlsplit(settings.redis_url).hostname if settings.redis_url else "off",
        settings.task_mode,
        settings.embedding_provider,
    )
    if settings.task_mode == "inline":
        # Jobs run on this event loop (no Celery workers). Pick up anything a previous
        # process left unfinished - in the background, so startup never waits on it.
        runner.start(asyncio.get_running_loop(), settings.inline_max_concurrent_campaigns)
        recovery = asyncio.create_task(_recover_jobs())
    yield
    # Shutdown: stop inline jobs, close pooled DB connections and shared clients cleanly.
    if settings.task_mode == "inline":
        recovery.cancel()
        await runner.stop()
    await engine.dispose()
    if get_qdrant_client.cache_info().currsize:
        await get_qdrant_client().close()
    if get_redis.cache_info().currsize:  # only created if REDIS_URL is set
        await get_redis().aclose()
    logger.info("Shut down %s", app.title)


def create_app() -> FastAPI:
    """Application factory: builds a fully configured FastAPI instance."""
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_tracing(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    # Middleware added last runs first, so CORS wraps everything. Order (outer -> inner):
    # CORS -> request ID -> security headers -> body size limit -> routes.
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_json_bytes=settings.max_json_body_kb * 1024,
        # Multipart framing adds a little overhead around the file itself.
        max_multipart_bytes=(settings.max_upload_size_mb + 1) * 1024 * 1024,
    )
    app.add_middleware(
        SecurityHeadersMiddleware, api_prefix=settings.api_v1_prefix, hsts=settings.hsts_enabled
    )
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Browsers hide response headers from cross-origin JavaScript unless exposed here.
        # Content-Disposition carries the PDF export's filename.
        expose_headers=[REQUEST_ID_HEADER, "Content-Disposition"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
