"""Phase 12 hardening: rate limits, login lockout, security headers, body limits,
config guards, token housekeeping, queue routing and research cache/recency fixes."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.agents.deps import AgentDeps
from app.agents.nodes.competitor_analyst import make_competitor_analyst
from app.api.rate_limits import KNOWLEDGE_ASK, REGISTER_PER_IP, client_ip
from app.core.config import Settings, get_settings
from app.core.rate_limit import InMemoryRateLimiter, Limit, RedisRateLimiter
from app.core.security import hash_token
from app.models import RefreshToken, User
from app.research.competitor import CompetitorReportDraft, ResearchPlan
from app.services.auth_service import purge_expired_refresh_tokens
from tests.conftest import DEFAULT_PASSWORD
from tests.fakes import FakeLLM, FakeSearchProvider
from tests.test_agents import FakeCompetitor
from tests.test_web_research import CTX, DRAFT, make_service

pytestmark = pytest.mark.anyio
API = "/api/v1"


# ---------- Limiter core ----------


async def test_in_memory_limiter_counts_peeks_and_resets() -> None:
    limiter, limit = InMemoryRateLimiter(), Limit("t", 2, 60)

    assert (await limiter.hit(limit, "a")).allowed
    assert (await limiter.hit(limit, "a")).allowed
    blocked = await limiter.hit(limit, "a")
    assert not blocked.allowed and blocked.count == 3 and 1 <= blocked.retry_after <= 60
    assert (await limiter.hit(limit, "b")).allowed  # subjects are independent
    assert (await limiter.peek(limit, "a")).count == 3  # peek does not add

    await limiter.reset(limit, "a")
    assert (await limiter.peek(limit, "a")).count == 0


async def test_in_memory_limiter_window_expires() -> None:
    limiter, limit = InMemoryRateLimiter(), Limit("t", 1, 60)
    await limiter.hit(limit, "a")
    key = next(iter(limiter._windows))
    limiter._windows[key] = (0.0, 99)  # pretend the window ended long ago
    assert (await limiter.hit(limit, "a")).allowed


class _BrokenRedis:
    def register_script(self, _script):
        async def run(**_kwargs):
            raise ConnectionError("redis down")

        return run

    async def delete(self, *_keys):
        raise ConnectionError("redis down")


async def test_redis_limiter_fails_open_when_redis_is_down() -> None:
    limiter = RedisRateLimiter(_BrokenRedis())  # type: ignore[arg-type]
    limit = Limit("t", 1, 60)
    for _ in range(3):
        assert (await limiter.hit(limit, "a")).allowed
    await limiter.reset(limit, "a")  # must not raise


# ---------- Client IP behind proxies ----------


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


@pytest.mark.parametrize(
    ("peer", "forwarded", "expected"),
    [
        ("203.0.113.5", "1.2.3.4", "203.0.113.5"),  # untrusted peer: header ignored
        ("127.0.0.1", "198.51.100.7", "198.51.100.7"),  # trusted proxy: header used
        ("127.0.0.1", "6.6.6.6, 198.51.100.7", "198.51.100.7"),  # spoofed left part ignored
        ("127.0.0.1", "198.51.100.7, 127.0.0.1", "198.51.100.7"),  # skip our own proxies
        ("127.0.0.1", None, "127.0.0.1"),
        ("10.1.2.3", "198.51.100.7", "198.51.100.7"),  # CIDR entries work
    ],
)
def test_client_ip(peer: str, forwarded: str | None, expected: str) -> None:
    settings = get_settings().model_copy(update={"trusted_proxies": ["127.0.0.1", "10.0.0.0/8"]})
    assert client_ip(_request(peer, forwarded), settings) == expected


# ---------- Login brute-force protection ----------


async def _login(client: AsyncClient, email: str, password: str, ip: str = "198.51.100.1"):
    return await client.post(
        f"{API}/auth/login",
        json={"email": email, "password": password},
        headers={"X-Forwarded-For": ip},
    )


async def test_account_locks_after_repeated_failures(client: AsyncClient, register_and_login):
    await register_and_login("victim@example.com")

    for i in range(get_settings().login_max_failures):
        # Spread over many IPs: the per-account counter still catches it.
        response = await _login(client, "victim@example.com", "wrong", ip=f"198.51.100.{i + 10}")
        assert response.status_code == 401

    locked = await _login(client, "VICTIM@example.com", DEFAULT_PASSWORD)  # even the right one
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "rate_limited"
    assert int(locked.headers["Retry-After"]) > 0

    assert await register_and_login("bystander@example.com")  # other accounts unaffected


async def test_successful_login_clears_failure_count(client: AsyncClient, register_and_login):
    await register_and_login("forgetful@example.com")
    limit = get_settings().login_max_failures
    for _ in range(limit - 1):
        await _login(client, "forgetful@example.com", "wrong")
    assert (await _login(client, "forgetful@example.com", DEFAULT_PASSWORD)).status_code == 200
    for _ in range(limit - 1):
        await _login(client, "forgetful@example.com", "wrong")
    assert (await _login(client, "forgetful@example.com", DEFAULT_PASSWORD)).status_code == 200


async def test_unknown_email_locks_the_same_way(client: AsyncClient) -> None:
    """Same answers for existing and missing accounts: no user enumeration."""
    for _ in range(get_settings().login_max_failures):
        assert (await _login(client, "ghost@example.com", "x")).status_code == 401
    assert (await _login(client, "ghost@example.com", "x")).status_code == 429


# ---------- Endpoint limits ----------


async def test_register_is_limited_per_client_ip(client: AsyncClient, rate_limiter) -> None:
    await rate_limiter.hit(REGISTER_PER_IP, "198.51.100.66", amount=REGISTER_PER_IP.requests)
    body = {"email": "new@example.com", "password": "long-enough-pw", "full_name": "New"}

    blocked = await client.post(
        f"{API}/auth/register", json=body, headers={"X-Forwarded-For": "198.51.100.66"}
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["details"]["limit"] == "register-ip"

    allowed = await client.post(
        f"{API}/auth/register", json=body, headers={"X-Forwarded-For": "198.51.100.67"}
    )
    assert allowed.status_code == 201


async def test_expensive_endpoints_are_limited_per_user(
    client: AsyncClient, register_and_login, rate_limiter, db_session: AsyncSession
) -> None:
    headers = await register_and_login("asker@example.com")
    user_id = await db_session.scalar(select(User.id).where(User.email == "asker@example.com"))
    await rate_limiter.hit(KNOWLEDGE_ASK, str(user_id), amount=KNOWLEDGE_ASK.requests)

    # The limit is checked before any lookup (the brand doesn't even exist).
    response = await client.post(
        f"{API}/brands/{uuid.uuid4()}/knowledge/ask", json={"question": "hi?"}, headers=headers
    )
    assert response.status_code == 429
    assert "Retry-After" in response.headers


async def test_rate_limiting_can_be_disabled(
    client: AsyncClient, rate_limiter, monkeypatch: pytest.MonkeyPatch
) -> None:
    await rate_limiter.hit(REGISTER_PER_IP, "127.0.0.1", amount=100)
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)
    body = {"email": "free@example.com", "password": "long-enough-pw", "full_name": "F"}
    assert (await client.post(f"{API}/auth/register", json=body)).status_code == 201


# ---------- HTTP hardening ----------


async def test_security_headers(client: AsyncClient) -> None:
    response = await client.get(f"{API}/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"
    assert "Strict-Transport-Security" not in response.headers  # off unless HTTPS

    docs = await client.get("/docs")  # Swagger UI needs its CDN scripts
    assert "Content-Security-Policy" not in docs.headers


async def test_oversized_json_body_is_rejected(client: AsyncClient) -> None:
    huge = "x" * (get_settings().max_json_body_kb * 1024 + 10)
    response = await client.post(
        f"{API}/auth/login",
        content=f'{{"email":"a@b.co","password":"{huge}"}}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_oversized_chunked_body_is_rejected(client: AsyncClient) -> None:
    """No Content-Length (chunked upload): bytes are counted as they arrive."""
    chunk = b"x" * 64 * 1024

    async def stream():
        yield b'{"email":"a@b.co","password":"'
        for _ in range(get_settings().max_json_body_kb // 64 + 2):
            yield chunk
        yield b'"}'

    response = await client.post(
        f"{API}/auth/login", content=stream(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"jwt_secret_key": "short"}, "JWT_SECRET_KEY"),
        ({"debug": True}, "DEBUG"),
        ({"cors_origins": ["*"]}, "CORS_ORIGINS"),
        ({"database_url": "postgresql+asyncpg://u:p@localhost:5432/app"}, "DATABASE_URL"),
    ],
)
def test_production_settings_are_guarded(overrides: dict, message: str) -> None:
    good = {
        "environment": "production",
        "jwt_secret_key": "k" * 40,
        "database_url": "postgresql+asyncpg://u:p@db.example.com/app",
    }
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **{**good, **overrides})


def test_production_settings_accept_a_safe_config() -> None:
    Settings(
        _env_file=None,
        environment="production",
        jwt_secret_key="k" * 40,
        database_url="postgresql+asyncpg://u:p@db.example.com/app",
    )


# ---------- Token housekeeping ----------


async def test_purge_removes_only_fully_expired_families(db_session: AsyncSession) -> None:
    user = User(email="purge@example.com", password_hash="x", full_name="P")
    db_session.add(user)
    await db_session.flush()
    now = datetime.now(UTC)

    def token(family: uuid.UUID, expired_days_ago: float, revoked: bool = False) -> RefreshToken:
        return RefreshToken(
            user_id=user.id,
            family_id=family,
            token_hash=hash_token(uuid.uuid4().hex),
            expires_at=now - timedelta(days=expired_days_ago),
            revoked_at=now if revoked else None,
        )

    dead, alive, recent = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db_session.add_all(
        [
            token(dead, 40, revoked=True),
            token(dead, 30),  # whole family expired long ago -> purged
            token(alive, 40, revoked=True),  # consumed, but its family is still live:
            token(alive, -20),  # kept, so reuse detection still works
            token(recent, 2),  # expired within the grace period -> kept
        ]
    )
    await db_session.commit()

    assert await purge_expired_refresh_tokens(db_session) == 2
    families = set(await db_session.scalars(select(RefreshToken.family_id)))
    assert families == {alive, recent}


# ---------- Worker queues ----------


def test_campaign_tasks_use_their_own_queue() -> None:
    import app.worker.tasks  # noqa: F401  (registers the tasks)
    from app.worker.celery_app import celery_app

    def queue(task: str) -> str:
        return celery_app.amqp.router.route({}, task)["queue"].name

    assert queue("campaigns.execute") == "campaigns"
    assert queue("documents.ingest") == queue("documents.cleanup") == "default"
    assert "maintenance.purge_refresh_tokens" in celery_app.tasks
    schedule = celery_app.conf.beat_schedule["purge-expired-refresh-tokens"]
    assert schedule["task"] == "maintenance.purge_refresh_tokens"


# ---------- Research: recency + stable plan cache ----------


async def test_trend_queries_are_restricted_to_recent_pages() -> None:
    plan = ResearchPlan(queries=["fizzco campaign", "beverage trends 2026", "latest soda ads"])
    provider = FakeSearchProvider()
    llm = FakeLLM({ResearchPlan: plan, CompetitorReportDraft: DRAFT})

    await make_service(llm, provider).research(CTX)

    assert provider.options["fizzco campaign"].time_range is None
    assert provider.options["beverage trends 2026"].time_range == "year"
    assert provider.options["latest soda ads"].time_range == "year"


async def test_research_focus_ignores_llm_wording_so_the_plan_cache_hits() -> None:
    competitor = FakeCompetitor()
    deps = AgentDeps(
        llm=None, settings=get_settings(), knowledge=None, competitor_researcher=competitor
    )
    node = make_competitor_analyst(deps)
    brief = {"platform": "Instagram", "target_audience": "students", "competitor_focus": "colas"}
    for wording in ["campus drinks ads", "student beverage advertising"]:  # LLM output varies
        plan = {"competitor_research_enabled": True, "competitor_research_focus": wording}
        await node({"plan": plan, "brand": {"name": "MANO"}, "brief": brief, "events": []})

    first, second = competitor.contexts
    assert first.render() == second.render()  # identical -> same plan cache key
    assert "colas" in first.focus and "campus" not in first.focus
