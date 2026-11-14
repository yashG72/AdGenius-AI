"""Celery tasks. Thin wrappers: each one builds its resources and calls async code.

Celery tasks are synchronous functions, while our DB/Qdrant code is async, so each task
runs `asyncio.run(...)` with its own short-lived DB engine (NullPool: no connections
outlive the task's event loop).
"""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.aio import run_async
from app.core.config import get_settings
from app.core.storage import get_storage
from app.ingestion.embeddings import get_embedder
from app.ingestion.pipeline import ingest_document
from app.ingestion.vector_store import VectorStore, create_qdrant_client
from app.models import BrandDocument
from app.worker.celery_app import celery_app


async def _run_ingestion(document_id: uuid.UUID, force: bool) -> str | None:
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


@celery_app.task(
    name="documents.ingest",
    autoretry_for=(Exception,),  # permanent errors are handled inside; these are transient
    retry_backoff=True,  # 1s, 2s, 4s ... between attempts
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def ingest_document_task(document_id: str, force: bool = False) -> str | None:
    return asyncio.run(_run_ingestion(uuid.UUID(document_id), force))


async def _cleanup(document_ids: list[uuid.UUID], brand_id: uuid.UUID | None) -> None:
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


async def _execute_campaign_run(run_id: uuid.UUID) -> str:
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
    finally:
        await engine.dispose()


@celery_app.task(
    name="campaigns.execute",
    # Agent workflows are long (several LLM calls + web research), so allow more time.
    soft_time_limit=30 * 60,
    time_limit=35 * 60,
    max_retries=0,  # failures are recorded on the run; retry is an explicit API action
)
def execute_campaign_run_task(run_id: str) -> str:
    # run_async (not asyncio.run): psycopg's async mode needs a SelectorEventLoop on Windows.
    return run_async(_execute_campaign_run(uuid.UUID(run_id)))


@celery_app.task(
    name="documents.cleanup",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
)
def cleanup_documents_task(document_ids: list[str], brand_id: str | None = None) -> None:
    asyncio.run(
        _cleanup([uuid.UUID(d) for d in document_ids], uuid.UUID(brand_id) if brand_id else None)
    )
