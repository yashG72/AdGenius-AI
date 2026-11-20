"""The background jobs themselves, as plain async functions.

They run in one of two places (TASK_MODE):
- "celery": wrapped by Celery tasks (app/worker/tasks.py) in separate worker processes;
- "inline": scheduled on the API's own event loop (app/worker/inline.py) - for hosting
  plans without background workers.

Each job builds its own short-lived resources (DB engine with NullPool, Qdrant client),
so it never shares connections with whatever loop or process runs it.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.storage import get_storage
from app.ingestion.embeddings import get_embedder
from app.ingestion.pipeline import ingest_document
from app.ingestion.vector_store import VectorStore, create_qdrant_client
from app.models import BrandDocument, RunStatus

logger = logging.getLogger(__name__)


async def run_ingestion(document_id: uuid.UUID, force: bool = False) -> str | None:
    """Extract, chunk, embed and index one document (idempotent)."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    client = create_qdrant_client(settings)
    try:
        status = await ingest_document(
            document_id,
            session_factory=async_sessionmaker(engine, expire_on_commit=False),
            storage=get_storage(),
            embedder=get_embedder(),
            vector_store=VectorStore(client, settings.qdrant_collection),
            settings=settings,
            force=force,
        )
        return status.value if status else None
    finally:
        await client.close()
        await engine.dispose()


async def run_cleanup(document_ids: list[uuid.UUID], brand_id: uuid.UUID | None) -> None:
    """Remove vectors and stored files of deleted documents (or of a whole brand)."""
    settings = get_settings()
    client = create_qdrant_client(settings)
    store = VectorStore(client, settings.qdrant_collection)
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        if brand_id is not None:
            await store.delete_brand(brand_id)
        for document_id in document_ids:
            await store.delete_document(document_id)

        # Remove stored files of every deleted document involved.
        async with async_sessionmaker(engine)() as session:
            query = select(BrandDocument.storage_key)
            if brand_id is not None:
                query = query.where(BrandDocument.brand_id == brand_id)
            else:
                query = query.where(BrandDocument.id.in_(document_ids))
            storage = get_storage()
            for key in await session.scalars(query):
                storage.delete(key)
    finally:
        await client.close()
        await engine.dispose()


async def run_campaign(run_id: uuid.UUID) -> str:
    """One lifecycle step of a campaign run (start / resume / continue)."""
    from app.agents.checkpointer import postgres_checkpointer
    from app.agents.factory import live_agent_deps
    from app.agents.runner import CampaignWorkflow
    from app.campaigns.executor import execute_run

    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        # Three sessions: run bookkeeping, live progress recording, and the Brand
        # Research agent's document search (which runs in parallel with other work).
        async with (
            sessions() as session,
            sessions() as recorder_session,
            sessions() as knowledge_session,
            postgres_checkpointer(settings.database_url) as saver,
            live_agent_deps(knowledge_session, settings) as deps,
        ):
            run = await execute_run(
                session, run_id, CampaignWorkflow(deps, saver), recorder_session=recorder_session
            )
            return run.status.value
    except Exception as exc:
        # execute_run records its own failures; this catches crashes BEFORE it runs
        # (database or checkpointer unreachable, missing API key...). Without it the run
        # would sit in "queued" forever and the UI would spin.
        await _mark_failed(sessions, run_id, exc)
        raise
    finally:
        await engine.dispose()


async def _mark_failed(sessions: async_sessionmaker, run_id: uuid.UUID, exc: Exception) -> None:
    from datetime import UTC, datetime

    from app.models import CampaignRun

    try:
        async with sessions() as session:
            run = await session.get(CampaignRun, run_id)
            if run is not None and not run.status.is_terminal:
                run.status = RunStatus.FAILED
                run.error_message = f"Could not start the workflow: {type(exc).__name__}"
                run.finished_at = datetime.now(UTC)
                await session.commit()
    except Exception:  # the database itself may be what failed
        logger.exception("Could not mark campaign run %s as failed", run_id)


async def purge_refresh_tokens() -> int:
    from app.services.auth_service import purge_expired_refresh_tokens

    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as session:
            deleted = await purge_expired_refresh_tokens(session)
    finally:
        await engine.dispose()
    logger.info("Purged %d expired refresh tokens", deleted)
    return deleted
