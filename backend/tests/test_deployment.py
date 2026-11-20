"""Phase 13 deployment profile: inline jobs, optional Redis, Gemini embeddings, hosted DB URLs."""

import asyncio
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.checkpointer import psycopg_conninfo
from app.api import rate_limits
from app.api.v1.routes.health import get_readiness_checks
from app.core.config import Settings, get_settings
from app.core.rate_limit import InMemoryRateLimiter
from app.ingestion.embeddings import GeminiEmbedder
from app.models import Brand, BrandDocument, Campaign, CampaignRun, DocumentStatus, RunStatus
from app.research import cache
from app.worker import inline, jobs
from app.worker.inline import InlineRunner

pytestmark = pytest.mark.anyio


# ---------- Settings ----------


@pytest.mark.parametrize("value", ["", "none", "None", "off", "disabled"])
def test_redis_can_be_switched_off_explicitly(value: str) -> None:
    assert Settings(_env_file=None, task_mode="inline", redis_url=value).redis_url is None


def test_celery_mode_requires_redis() -> None:
    with pytest.raises(ValidationError, match="REDIS_URL"):
        Settings(_env_file=None, task_mode="celery", redis_url="")
    Settings(_env_file=None, task_mode="inline", redis_url="")  # fine without Redis


@pytest.mark.parametrize(
    "raw",
    [
        # Neon's "Connect" string, pasted verbatim
        "postgresql://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require",
        "postgres://u:p@ep-x.neon.tech/db?sslmode=require",
        "postgresql+asyncpg://u:p@ep-x.neon.tech/db?ssl=require",  # already converted
    ],
)
def test_hosted_database_urls_are_normalised_for_asyncpg(raw: str) -> None:
    settings = Settings(_env_file=None, database_url=raw)
    assert settings.database_url == "postgresql+asyncpg://u:p@ep-x.neon.tech/db?ssl=require"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "postgresql+asyncpg://u:p@ep-x.neon.tech/db?ssl=require",
            "postgresql://u:p@ep-x.neon.tech/db?sslmode=require",
        ),
        ("postgresql+asyncpg://u:p@localhost:5432/db", "postgresql://u:p@localhost:5432/db"),
    ],
)
def test_psycopg_conninfo_translates_ssl(url: str, expected: str) -> None:
    assert psycopg_conninfo(url) == expected


# ---------- Running without Redis ----------


def test_without_redis_everything_falls_back_to_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "redis_url", "")

    assert isinstance(rate_limits.get_rate_limiter(), InMemoryRateLimiter)
    assert rate_limits.get_rate_limiter() is rate_limits.get_rate_limiter()  # shared
    assert isinstance(cache.get_search_cache(), cache.InMemorySearchCache)
    assert "redis" not in get_readiness_checks(get_settings())


def test_with_redis_the_shared_backends_are_used() -> None:
    assert get_settings().redis_url  # local/test default
    assert isinstance(cache.get_search_cache(), cache.RedisSearchCache)
    assert "redis" in get_readiness_checks(get_settings())


# ---------- Inline job runner ----------


async def _drain(runner: InlineRunner) -> None:
    for _ in range(3):  # let call_soon_threadsafe callbacks spawn the tasks first
        await asyncio.sleep(0)
    for _ in range(200):
        await asyncio.sleep(0.01)
        if not runner._tasks:
            return
    raise AssertionError("jobs did not finish")


async def test_inline_runner_runs_jobs_and_retries_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = InlineRunner()
    runner.start(asyncio.get_running_loop())
    monkeypatch.setattr(asyncio, "sleep", _fast_sleep(asyncio.sleep))
    calls: list[str] = []

    async def flaky():
        calls.append("try")
        if calls.count("try") < 3:
            raise RuntimeError("rate limited")
        return "ok"

    async def broken():
        calls.append("broken")
        raise RuntimeError("always")

    assert runner.submit("ingest", "flaky", flaky, attempts=3)
    assert runner.submit("other", "broken", broken)  # failure is logged, never raised
    await _drain(runner)

    assert calls.count("try") == 3 and calls.count("broken") == 1


def _fast_sleep(real_sleep):
    async def sleep(seconds, *args, **kwargs):  # skip retry backoff, keep event-loop yields
        await real_sleep(0)

    return sleep


async def test_inline_runner_limits_concurrency() -> None:
    runner = InlineRunner(max_campaigns=1)
    runner.start(asyncio.get_running_loop())
    running, peak = 0, 0

    async def job():
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1

    for i in range(3):
        runner.submit("campaign", f"c{i}", job)
    await _drain(runner)
    assert peak == 1


async def test_unstarted_runner_refuses_jobs() -> None:
    async def job():
        return None

    assert InlineRunner().submit("other", "x", job) is False


async def test_submit_helpers_route_to_the_shared_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = InlineRunner()
    runner.start(asyncio.get_running_loop())
    monkeypatch.setattr(inline, "runner", runner)
    seen: list[tuple] = []

    async def fake_campaign(run_id):
        seen.append(("campaign", run_id))

    async def fake_ingestion(document_id, force=False):
        seen.append(("ingest", document_id, force))

    monkeypatch.setattr(jobs, "run_campaign", fake_campaign)
    monkeypatch.setattr(jobs, "run_ingestion", fake_ingestion)
    run_id, doc_id = uuid.uuid4(), uuid.uuid4()

    inline.submit_campaign(run_id)
    inline.submit_ingestion(doc_id, True)
    await _drain(runner)

    assert sorted(seen, key=str) == sorted(
        [("campaign", run_id), ("ingest", doc_id, True)], key=str
    )


async def test_recover_requeues_unfinished_work(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models import Organization, User
    from app.worker import dispatch

    user = User(email="recover@example.com", password_hash="x", full_name="R")
    org = Organization(name="Recover", slug=f"recover-{uuid.uuid4().hex[:6]}")
    db_session.add_all([user, org])
    await db_session.flush()
    brand = Brand(organization_id=org.id, name="B", created_by_id=user.id)
    db_session.add(brand)
    await db_session.flush()
    campaign = Campaign(
        organization_id=org.id, brand_id=brand.id, name="C", brief={}, created_by_id=user.id
    )
    db_session.add(campaign)
    await db_session.flush()

    def run(status: RunStatus, version: int) -> CampaignRun:
        return CampaignRun(
            campaign_id=campaign.id,
            organization_id=org.id,
            version=version,
            status=status,
            brief_snapshot={},
            brand_snapshot={},
        )

    def doc(status: DocumentStatus) -> BrandDocument:
        return BrandDocument(
            organization_id=org.id,
            brand_id=brand.id,
            original_filename="a.txt",
            storage_key=uuid.uuid4().hex,
            file_format="txt",
            size_bytes=1,
            sha256=uuid.uuid4().hex * 2,
            status=status,
        )

    interrupted, waiting = run(RunStatus.RUNNING, 1), run(RunStatus.QUEUED, 2)
    pending = doc(DocumentStatus.PENDING)
    db_session.add_all(
        [interrupted, waiting, run(RunStatus.COMPLETED, 3), pending, doc(DocumentStatus.INDEXED)]
    )
    await db_session.commit()

    requeued: list = []
    monkeypatch.setattr(dispatch, "enqueue_campaign_run", lambda rid: requeued.append(rid))
    monkeypatch.setattr(dispatch, "enqueue_ingestion", lambda did: requeued.append(did))

    await InlineRunner().recover(db_session.bind)

    assert set(requeued) == {interrupted.id, waiting.id, pending.id}


async def test_campaign_job_crash_before_execution_marks_run_failed(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash outside the executor (e.g. checkpointer unreachable) must not leave the
    run stuck in "queued" with the UI spinning forever."""
    from contextlib import asynccontextmanager

    from app.agents import checkpointer
    from app.models import Organization

    org = Organization(name="Crash", slug=f"crash-{uuid.uuid4().hex[:6]}")
    db_session.add(org)
    await db_session.flush()
    brand = Brand(organization_id=org.id, name="B")
    db_session.add(brand)
    await db_session.flush()
    campaign = Campaign(organization_id=org.id, brand_id=brand.id, name="C", brief={})
    db_session.add(campaign)
    await db_session.flush()
    run = CampaignRun(
        campaign_id=campaign.id,
        organization_id=org.id,
        version=1,
        status=RunStatus.QUEUED,
        brief_snapshot={},
        brand_snapshot={},
    )
    db_session.add(run)
    await db_session.commit()

    @asynccontextmanager
    async def shared_session():  # the job's sessions -> the test's transaction
        yield db_session

    @asynccontextmanager
    async def unreachable(_url):
        raise OSError("connection refused")
        yield

    monkeypatch.setattr(jobs, "async_sessionmaker", lambda *a, **k: shared_session)
    monkeypatch.setattr(checkpointer, "postgres_checkpointer", unreachable)

    with pytest.raises(OSError):
        await jobs.run_campaign(run.id)

    await db_session.refresh(run)
    assert run.status is RunStatus.FAILED
    assert "OSError" in run.error_message and run.finished_at is not None


# ---------- Gemini embeddings ----------


class _Embedding:
    def __init__(self, values):
        self.values = values


class _Response:
    def __init__(self, n):
        self.embeddings = [_Embedding([0.1, 0.2]) for _ in range(n)]


class _FakeModels:
    def __init__(self, failures: int):
        self.failures, self.calls = failures, []

    def embed_content(self, *, model, contents, config):
        from google.genai import errors

        self.calls.append((len(contents), config.task_type, config.output_dimensionality))
        if self.failures:
            self.failures -= 1
            raise errors.APIError(
                429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}}
            )
        return _Response(len(contents))


def _gemini(failures: int = 0) -> GeminiEmbedder:
    embedder = object.__new__(GeminiEmbedder)  # skip __init__: no network, no models
    embedder._client = type("C", (), {"models": _FakeModels(failures)})()
    embedder._model, embedder._dim, embedder._max_attempts = "gemini-embedding-001", 2, 4
    return embedder


def test_gemini_dense_embeddings_batch_and_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    monkeypatch.setattr(time, "sleep", lambda _s: None)
    embedder = _gemini(failures=2)

    vectors = embedder._dense([f"text {i}" for i in range(150)], "RETRIEVAL_DOCUMENT")

    assert len(vectors) == 150
    calls = embedder._client.models.calls
    assert [c[0] for c in calls] == [100, 100, 100, 50]  # 2 retries of batch 1, then batch 2
    assert all(c[1] == "RETRIEVAL_DOCUMENT" and c[2] == 2 for c in calls)


def test_gemini_embeddings_give_up_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    from google.genai import errors

    monkeypatch.setattr(time, "sleep", lambda _s: None)
    with pytest.raises(errors.APIError):
        _gemini(failures=10)._dense(["x"], "RETRIEVAL_QUERY")
