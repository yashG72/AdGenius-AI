"""Public demo: one-click sign-in, read-only enforcement, idempotent seeding."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import demo
from app.core.config import get_settings
from app.core.security import hash_password
from app.models import (
    Brand,
    BrandDocument,
    Campaign,
    CampaignRun,
    Membership,
    MembershipRole,
    Organization,
    RunStatus,
    User,
)

pytestmark = pytest.mark.anyio
API = "/api/v1"
DEMO_EMAIL = "demo@adgenius.app"


@pytest.fixture
def demo_on(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_enabled", True)
    monkeypatch.setattr(settings, "demo_email", DEMO_EMAIL)


async def _demo_workspace(session: AsyncSession, run_status: RunStatus) -> dict:
    user = User(email=DEMO_EMAIL, password_hash=hash_password("x" * 20), full_name="Demo")
    org = Organization(name="Brewnest (Demo)", slug=f"demo-{uuid.uuid4().hex[:6]}")
    session.add_all([user, org])
    await session.flush()
    session.add(Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER))
    brand = Brand(organization_id=org.id, name="Brewnest", created_by_id=user.id)
    session.add(brand)
    await session.flush()
    campaign = Campaign(organization_id=org.id, brand_id=brand.id, name="Launch", brief={})
    session.add(campaign)
    await session.flush()
    session.add(
        CampaignRun(
            campaign_id=campaign.id,
            organization_id=org.id,
            version=1,
            status=run_status,
            brief_snapshot={},
            brand_snapshot={},
        )
    )
    await session.commit()
    return {"org": org.id, "brand": brand.id, "campaign": campaign.id}


async def _demo_headers(client: AsyncClient) -> dict:
    response = await client.post(f"{API}/auth/demo")
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ---------- Sign-in ----------


async def test_demo_login_is_off_by_default(client: AsyncClient) -> None:
    assert (await client.post(f"{API}/auth/demo")).status_code == 404


async def test_demo_login_waits_until_a_campaign_is_finished(
    client: AsyncClient, db_session: AsyncSession, demo_on
) -> None:
    assert (await client.post(f"{API}/auth/demo")).status_code == 503  # nothing seeded yet
    await _demo_workspace(db_session, RunStatus.RUNNING)
    response = await client.post(f"{API}/auth/demo")
    assert response.status_code == 503
    assert "being prepared" in response.json()["error"]["message"]


async def test_demo_login_signs_into_the_demo_workspace(
    client: AsyncClient, db_session: AsyncSession, demo_on
) -> None:
    ids = await _demo_workspace(db_session, RunStatus.COMPLETED)
    headers = await _demo_headers(client)

    me = (await client.get(f"{API}/auth/me", headers=headers)).json()
    assert me["is_demo"] is True
    assert [o["id"] for o in me["organizations"]] == [str(ids["org"])]


async def test_demo_password_login_is_impossible(
    client: AsyncClient, db_session: AsyncSession, demo_on
) -> None:
    await _demo_workspace(db_session, RunStatus.COMPLETED)
    response = await client.post(
        f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": "x" * 8}
    )
    assert response.status_code == 401


# ---------- Read-only ----------


async def test_demo_can_browse_but_not_change_anything(
    client: AsyncClient, db_session: AsyncSession, demo_on
) -> None:
    ids = await _demo_workspace(db_session, RunStatus.COMPLETED)
    headers = await _demo_headers(client)

    # Reading works.
    brands = await client.get(f"{API}/brands?organization_id={ids['org']}", headers=headers)
    assert brands.status_code == 200
    assert (
        await client.get(f"{API}/campaigns/{ids['campaign']}", headers=headers)
    ).status_code == 200

    # Every kind of change is refused with a friendly message.
    attempts = [
        client.patch(f"{API}/brands/{ids['brand']}", json={"name": "Hacked"}, headers=headers),
        client.delete(f"{API}/brands/{ids['brand']}", headers=headers),
        client.post(f"{API}/campaigns/{ids['campaign']}/generate", headers=headers),
        client.patch(f"{API}/auth/me", json={"full_name": "Hacked"}, headers=headers),
        client.post(
            f"{API}/auth/change-password",
            json={"current_password": "x" * 20, "new_password": "y" * 20},
            headers=headers,
        ),
        client.patch(f"{API}/organizations/{ids['org']}", json={"name": "X"}, headers=headers),
        client.post(f"{API}/organizations", json={"name": "Another workspace"}, headers=headers),
    ]
    for attempt in attempts:
        response = await attempt
        assert response.status_code == 403, response.text
        assert "read-only demo" in response.json()["error"]["message"]

    brand = await db_session.get(Brand, ids["brand"])
    assert brand.name == "Brewnest" and brand.deleted_at is None


async def test_demo_may_ask_the_knowledge_base(
    client: AsyncClient, db_session: AsyncSession, demo_on
) -> None:
    ids = await _demo_workspace(db_session, RunStatus.COMPLETED)
    headers = await _demo_headers(client)
    response = await client.post(
        f"{API}/brands/{ids['brand']}/knowledge/ask", json={"question": "Tagline?"}, headers=headers
    )
    assert response.status_code != 403  # allowed (may still fail for lack of an LLM in tests)


async def test_regular_users_are_unaffected(client: AsyncClient, register_and_login, demo_on):
    headers = await register_and_login("normal@example.com")
    response = await client.post(f"{API}/organizations", json={"name": "Mine"}, headers=headers)
    assert response.status_code == 201
    me = (await client.get(f"{API}/auth/me", headers=headers)).json()
    assert me["is_demo"] is False


@pytest.mark.parametrize(
    ("method", "path", "blocked"),
    [
        ("GET", "/api/v1/brands", False),
        ("GET", "/api/v1/campaign-runs/x/export.pdf", False),
        ("POST", "/api/v1/brands/x/knowledge/ask", False),
        ("POST", "/api/v1/brands/x/knowledge/search/", False),
        ("POST", "/api/v1/brands", True),
        ("PUT", "/api/v1/campaign-runs/x/script", True),
        ("DELETE", "/api/v1/documents/x", True),
        ("POST", "/api/v1/approvals/x/approve", True),
    ],
)
def test_demo_blocks_request(method: str, path: str, blocked: bool) -> None:
    assert demo.demo_blocks_request(method, path) is blocked


# ---------- Seeding ----------


async def test_seeding_builds_the_workspace_once(
    db_session: AsyncSession, demo_on, storage, monkeypatch: pytest.MonkeyPatch, queued
) -> None:
    """ensure_demo is idempotent: a second run (next restart) creates nothing new."""
    monkeypatch.setattr(demo, "get_storage", lambda: storage)
    finished: list = []

    async def no_wait(*_args):
        return None

    async def fake_finish(_sessions, user_id, campaign_id):
        finished.append(campaign_id)

    monkeypatch.setattr(demo, "_wait_for_documents", no_wait)
    monkeypatch.setattr(demo, "_ensure_finished_run", fake_finish)

    await demo.ensure_demo(db_session.bind)
    await demo.ensure_demo(db_session.bind)

    async def count(model) -> int:
        return await db_session.scalar(select(func.count()).select_from(model))

    assert await db_session.scalar(select(func.count()).where(User.email == DEMO_EMAIL)) == 1
    assert await count(Organization) == 1
    brand = await db_session.scalar(select(Brand))
    assert brand.name == "Brewnest" and brand.brand_colors and brand.content_restrictions
    assert await count(BrandDocument) == len(demo.DOCUMENTS)  # uploaded once, not twice
    assert len(queued["ingest"]) == len(demo.DOCUMENTS)
    assert await count(Campaign) == 1
    assert len(finished) == 2 and finished[0] == finished[1]


async def test_autopilot_approves_the_first_concept(
    db_session: AsyncSession, demo_on, monkeypatch: pytest.MonkeyPatch, queued
) -> None:
    from app.models import Approval

    ids = await _demo_workspace(db_session, RunStatus.AWAITING_APPROVAL)
    run = await db_session.scalar(select(CampaignRun))
    user = await db_session.scalar(select(User).where(User.email == DEMO_EMAIL))
    db_session.add(
        Approval(
            run_id=run.id,
            organization_id=ids["org"],
            kind="concept_selection",
            round=1,
            payload={"concepts": [{"concept_id": "C2"}, {"concept_id": "C3"}]},
        )
    )
    await db_session.commit()

    calls = {"n": 0}

    async def fast_sleep(_seconds):
        calls["n"] += 1
        if calls["n"] > 1:  # after approving, pretend the workflow finished
            run.status = RunStatus.COMPLETED
            await db_session.commit()

    monkeypatch.setattr(demo.asyncio, "sleep", fast_sleep)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def shared():
        yield db_session

    status = await demo._autopilot(shared, user.id, run.id)

    approval = await db_session.scalar(select(Approval))
    assert approval.decision["concept_id"] == "C2"
    assert queued["campaign"] == [run.id]
    assert status is RunStatus.COMPLETED
