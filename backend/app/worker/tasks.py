"""Celery tasks (TASK_MODE=celery). Thin wrappers around the async jobs in jobs.py.

Celery tasks are synchronous functions, while our DB/Qdrant code is async, so each task
runs its job on a fresh event loop. The jobs create their own short-lived resources.
"""

import asyncio
import uuid

from app.core.aio import run_async
from app.worker import jobs
from app.worker.celery_app import celery_app


@celery_app.task(
    name="documents.ingest",
    autoretry_for=(Exception,),  # permanent errors are handled inside; these are transient
    retry_backoff=True,  # 1s, 2s, 4s ... between attempts
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def ingest_document_task(document_id: str, force: bool = False) -> str | None:
    return asyncio.run(jobs.run_ingestion(uuid.UUID(document_id), force))


@celery_app.task(
    name="campaigns.execute",
    # Agent workflows are long (several LLM calls + web research), so allow more time.
    soft_time_limit=30 * 60,
    time_limit=35 * 60,
    max_retries=0,  # failures are recorded on the run; retry is an explicit API action
)
def execute_campaign_run_task(run_id: str) -> str:
    # run_async (not asyncio.run): psycopg's async mode needs a SelectorEventLoop on Windows.
    return run_async(jobs.run_campaign(uuid.UUID(run_id)))


@celery_app.task(
    name="documents.cleanup",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
)
def cleanup_documents_task(document_ids: list[str], brand_id: str | None = None) -> None:
    asyncio.run(
        jobs.run_cleanup(
            [uuid.UUID(d) for d in document_ids], uuid.UUID(brand_id) if brand_id else None
        )
    )


@celery_app.task(name="maintenance.purge_refresh_tokens")
def purge_refresh_tokens_task() -> int:
    return asyncio.run(jobs.purge_refresh_tokens())
