"""In-process job runner (TASK_MODE=inline).

Free hosting plans give one web process and no background workers. In that mode the
jobs from jobs.py run as asyncio tasks on the API's own event loop instead of being sent
to Celery. They are mostly waiting on the network (Gemini, Tavily, Qdrant), so they share
the loop with HTTP requests comfortably.

Trade-offs versus Celery (acceptable for a single small instance):
- a restart interrupts running jobs. `recover()` runs at startup and re-schedules
  unfinished work; both jobs are idempotent, and a campaign continues from its last
  LangGraph checkpoint, so nothing is lost or duplicated;
- concurrency is bounded by semaphores to keep memory use predictable.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.models import BrandDocument, CampaignRun, DocumentStatus, RunStatus

logger = logging.getLogger(__name__)

JobFactory = Callable[[], Awaitable[Any]]


class InlineRunner:
    def __init__(self, max_campaigns: int = 1, max_ingestions: int = 1) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: set[asyncio.Task] = set()  # strong refs: asyncio only keeps weak ones
        self._max = {"campaign": max_campaigns, "ingest": max_ingestions, "other": 2}
        self._limits: dict[str, asyncio.Semaphore] = {}

    def start(self, loop: asyncio.AbstractEventLoop, max_campaigns: int | None = None) -> None:
        """Bind to the API's event loop (called once, at application startup)."""
        self._loop = loop
        if max_campaigns is not None:
            self._max["campaign"] = max_campaigns
        self._limits = {kind: asyncio.Semaphore(n) for kind, n in self._max.items()}

    @property
    def started(self) -> bool:
        return self._loop is not None

    def submit(self, kind: str, name: str, job: JobFactory, attempts: int = 1) -> bool:
        """Schedule a job. Safe to call from any thread (e.g. FastAPI BackgroundTasks)."""
        if self._loop is None or self._loop.is_closed():
            logger.error("Inline runner not started; dropping job %s", name)
            return False
        self._loop.call_soon_threadsafe(self._spawn, kind, name, job, attempts)
        return True

    def _spawn(self, kind: str, name: str, job: JobFactory, attempts: int) -> None:
        task = asyncio.create_task(self._run(kind, name, job, attempts), name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, kind: str, name: str, job: JobFactory, attempts: int) -> None:
        async with self._limits.get(kind, self._limits["other"]):
            for attempt in range(1, attempts + 1):
                try:
                    result = await job()
                    logger.info("Job %s finished: %s", name, result)
                    return
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if attempt == attempts:
                        logger.exception("Job %s failed after %d attempt(s)", name, attempt)
                        return
                    logger.warning("Job %s failed (attempt %d); retrying", name, attempt)
                    await asyncio.sleep(2**attempt)

    async def stop(self) -> None:
        """Cancel running jobs on shutdown; recover() picks them up on the next start."""
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def recover(self, engine: AsyncEngine) -> None:
        """Re-schedule work a previous process left unfinished (crash, deploy, sleep)."""
        from app.worker import dispatch

        async with async_sessionmaker(engine)() as session:
            run_ids = list(
                await session.scalars(
                    select(CampaignRun.id).where(
                        CampaignRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING])
                    )
                )
            )
            document_ids = list(
                await session.scalars(
                    select(BrandDocument.id).where(
                        BrandDocument.status.in_(
                            [DocumentStatus.PENDING, DocumentStatus.PROCESSING]
                        )
                    )
                )
            )
        for document_id in document_ids:
            dispatch.enqueue_ingestion(document_id)
        for run_id in run_ids:
            dispatch.enqueue_campaign_run(run_id)
        if run_ids or document_ids:
            logger.info(
                "Recovered %d campaign run(s) and %d document(s)", len(run_ids), len(document_ids)
            )


runner = InlineRunner()


def submit_ingestion(document_id: uuid.UUID, force: bool) -> bool:
    from app.worker import jobs

    # Transient failures (e.g. an embedding API rate limit) get two more tries,
    # like the Celery task's autoretry.
    return runner.submit(
        "ingest", f"ingest:{document_id}", lambda: jobs.run_ingestion(document_id, force), 3
    )


def submit_campaign(run_id: uuid.UUID) -> bool:
    from app.worker import jobs

    # No automatic retry: failures are recorded on the run; retry is a user action.
    return runner.submit("campaign", f"campaign:{run_id}", lambda: jobs.run_campaign(run_id))


def submit_cleanup(document_ids: list[uuid.UUID], brand_id: uuid.UUID | None) -> bool:
    from app.worker import jobs

    return runner.submit(
        "other", "cleanup", lambda: jobs.run_cleanup(document_ids, brand_id), attempts=3
    )
