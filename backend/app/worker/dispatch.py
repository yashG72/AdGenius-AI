"""API-side helpers that put jobs on the queue.

If Redis is down, the upload must still succeed: the document simply stays `pending`
and can be re-queued later via the reindex endpoint. So publishing never retries or
blocks the request, and failures are logged rather than raised.
"""

import logging
import uuid

logger = logging.getLogger(__name__)


def enqueue_ingestion(document_id: uuid.UUID, *, force: bool = False) -> bool:
    from app.worker.tasks import ingest_document_task

    try:
        ingest_document_task.apply_async(args=[str(document_id), force], retry=False)
        return True
    except Exception:
        logger.exception("Could not enqueue ingestion for document %s", document_id)
        return False


def enqueue_campaign_run(run_id: uuid.UUID) -> bool:
    """Queue one lifecycle step of a campaign run (start / resume / continue)."""
    from app.worker.tasks import execute_campaign_run_task

    try:
        execute_campaign_run_task.apply_async(args=[str(run_id)], retry=False)
        return True
    except Exception:
        logger.exception("Could not enqueue campaign run %s", run_id)
        return False


def enqueue_cleanup(document_ids: list[uuid.UUID], *, brand_id: uuid.UUID | None = None) -> bool:
    from app.worker.tasks import cleanup_documents_task

    try:
        cleanup_documents_task.apply_async(
            args=[[str(d) for d in document_ids], str(brand_id) if brand_id else None],
            retry=False,
        )
        return True
    except Exception:
        logger.exception(
            "Could not enqueue cleanup (documents=%s brand=%s)", document_ids, brand_id
        )
        return False
