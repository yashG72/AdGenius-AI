"""Campaigns API + worker execution: versioned runs, approvals, outputs, SSE, isolation.

The Celery worker is simulated by calling `execute_run` directly with scripted agents.
"""

import json
import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.deps import AgentDeps
from app.agents.runner import CampaignWorkflow
from app.campaigns.executor import execute_run
from app.core.config import get_settings
from app.llm.client import LLMError
from tests.test_agents import concepts, llm, review, seq

pytestmark = pytest.mark.anyio

BRIEF = {
    "objective": "Brand awareness",
    "target_audience": "College students aged 18-25",
    "platform": "instagram",
    "duration_seconds": 30,
    "video_format": "9:16",
    "tone": "Youthful, humorous",
    "num_concepts": 3,
}


@pytest.fixture
async def ws(client: AsyncClient, register_and_login, db_session: AsyncSession, queued):
    owner = await register_and_login("owner@example.com")
    outsider = await register_and_login("outsider@example.com")
    org = (await client.post("/api/v1/organizations", json={"name": "A"}, headers=owner)).json()
    brand = (
        await client.post(
            "/api/v1/brands",
            headers=owner,
            json={
                "organization_id": org["id"],
                "name": "MANO",
                "content_restrictions": ["Never say 'healthy'"],
            },
        )
    ).json()
    saver = InMemorySaver()  # shared across worker calls = durable within the test

    async def work(run_id: str, fake=None):
        """Simulate the Celery worker processing the queued run."""
        deps = AgentDeps(
            llm=fake or llm(),
            settings=get_settings().model_copy(update={"agent_retry_initial_seconds": 0}),
        )
        return await execute_run(db_session, uuid.UUID(run_id), CampaignWorkflow(deps, saver))

    async def create_campaign(**overrides):
        body = {"brand_id": brand["id"], "name": "Campus Launch", "brief": BRIEF, **overrides}
        response = await client.post("/api/v1/campaigns", json=body, headers=owner)
        assert response.status_code == 201, response.text
        return response.json()

    async def generate(campaign_id: str) -> dict:
        response = await client.post(f"/api/v1/campaigns/{campaign_id}/generate", headers=owner)
        assert response.status_code == 202, response.text
        return response.json()

    return SimpleNamespace(
        owner=owner,
        outsider=outsider,
        org=org,
        brand=brand,
        work=work,
        create_campaign=create_campaign,
        generate=generate,
        queued=queued,
    )


async def get(client, url, headers, **params):
    response = await client.get(f"/api/v1{url}", headers=headers, params=params)
    return response


async def approve(client, ws, run_id, concept_id="C2"):
    detail = (await get(client, f"/campaign-runs/{run_id}", ws.owner)).json()
    approval_id = detail["pending_approval"]["id"]
    return await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"concept_id": concept_id},
        headers=ws.owner,
    )


# ---------- Campaign CRUD ----------


async def test_campaign_crud_and_validation(client: AsyncClient, ws) -> None:
    campaign = await ws.create_campaign()
    assert campaign["latest_run"] is None and campaign["run_count"] == 0
    assert campaign["brief"]["duration_seconds"] == 30
    assert campaign["organization_id"] == ws.org["id"]

    patched = await client.patch(
        f"/api/v1/campaigns/{campaign['id']}",
        headers=ws.owner,
        json={"name": "Renamed", "brief": {**BRIEF, "duration_seconds": 15}},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed" and patched.json()["brief"]["duration_seconds"] == 15

    listed = (await get(client, "/campaigns", ws.owner, organization_id=ws.org["id"])).json()
    assert listed["total"] == 1

    bad = await client.post(
        "/api/v1/campaigns",
        headers=ws.owner,
        json={"brand_id": ws.brand["id"], "name": "X", "brief": {**BRIEF, "duration_seconds": 500}},
    )
    assert bad.status_code == 422


async def test_campaigns_are_tenant_isolated(client: AsyncClient, ws) -> None:
    campaign = await ws.create_campaign()

    assert (await get(client, f"/campaigns/{campaign['id']}", ws.outsider)).status_code == 404
    foreign = await client.post(
        "/api/v1/campaigns",
        headers=ws.outsider,
        json={"brand_id": ws.brand["id"], "name": "X", "brief": BRIEF},
    )
    assert foreign.status_code == 404
    gen = await client.post(f"/api/v1/campaigns/{campaign['id']}/generate", headers=ws.outsider)
    assert gen.status_code == 404


# ---------- Full lifecycle ----------


async def test_generate_approve_complete(client: AsyncClient, ws) -> None:
    campaign = await ws.create_campaign()
    run = await ws.generate(campaign["id"])
    assert run["version"] == 1 and run["status"] == "queued"
    assert [str(r) for r in ws.queued["campaign"]] == [run["id"]]
    dup = await client.post(f"/api/v1/campaigns/{campaign['id']}/generate", headers=ws.owner)
    assert dup.status_code == 409  # one active run per campaign

    # Worker: research + concepts, then pause for approval.
    assert (await ws.work(run["id"])).status.value == "awaiting_approval"
    detail = (await get(client, f"/campaign-runs/{run['id']}", ws.owner)).json()
    assert detail["status"] == "awaiting_approval"
    assert [a["agent"] for a in detail["agent_runs"]][:2] == ["campaign_manager", "brand_research"]
    assert [a["sequence"] for a in detail["agent_runs"]] == list(
        range(1, len(detail["agent_runs"]) + 1)
    )
    assert {o["output_type"] for o in detail["outputs"]} >= {
        "execution_plan",
        "brand_research",
        "concepts",
    }
    assert len(detail["pending_approval"]["payload"]["concepts"]) == 3
    concepts_out = (await get(client, f"/campaign-runs/{run['id']}/concepts", ws.owner)).json()
    assert (
        concepts_out["version"] == 1 and concepts_out["content"]["recommended_concept_id"] == "C2"
    )
    assert (await get(client, f"/campaign-runs/{run['id']}/script", ws.owner)).status_code == 404

    # Human decision via the API.
    bad = await approve(client, ws, run["id"], concept_id="C9")
    assert bad.status_code == 400
    ok = await approve(client, ws, run["id"], concept_id="C2")
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    assert ok.json()["decided_by_id"] is not None
    assert (await get(client, f"/campaign-runs/{run['id']}", ws.owner)).json()["status"] == "queued"
    again = await client.post(
        f"/api/v1/approvals/{ok.json()['id']}/approve", json={"concept_id": "C1"}, headers=ws.owner
    )
    assert again.status_code == 409
    assert len(ws.queued["campaign"]) == 2  # resume queued

    # Worker: production + critic.
    finished = await ws.work(run["id"])
    assert finished.status.value == "completed" and finished.overall_score == 90
    for path in ("script", "storyboard", "evaluation"):
        out = await get(client, f"/campaign-runs/{run['id']}/{path}", ws.owner)
        assert out.status_code == 200, path
    final = await get(client, f"/campaign-runs/{run['id']}/outputs/final_campaign", ws.owner)
    assert final.json()["content"]["creative_strategy"]["selected_concept_id"] == "C2"
    approvals = (await get(client, f"/campaign-runs/{run['id']}/approvals", ws.owner)).json()
    assert [a["status"] for a in approvals["items"]] == ["approved"]
    summary = (await get(client, f"/campaigns/{campaign['id']}", ws.owner)).json()
    assert summary["latest_run"]["status"] == "completed" and summary["run_count"] == 1


async def test_revisions_are_kept_as_output_versions(client: AsyncClient, ws) -> None:
    fake = llm(critic=seq(review(60, target="storyboard"), review(90)))
    run = await ws.generate((await ws.create_campaign())["id"])
    await ws.work(run["id"], fake)
    await approve(client, ws, run["id"])
    await ws.work(run["id"], fake)

    latest = (await get(client, f"/campaign-runs/{run['id']}/storyboard", ws.owner)).json()
    first = (
        await get(client, f"/campaign-runs/{run['id']}/storyboard", ws.owner, version=1)
    ).json()
    assert latest["version"] == 2 and latest["versions"] == 2 and first["version"] == 1
    script = (await get(client, f"/campaign-runs/{run['id']}/script", ws.owner)).json()
    assert script["versions"] == 1  # storyboard-only issue: script untouched
    evaluation = (await get(client, f"/campaign-runs/{run['id']}/evaluation", ws.owner)).json()
    assert evaluation["versions"] == 2 and evaluation["content"]["passed"]


async def test_reject_regenerates_concepts(client: AsyncClient, ws) -> None:
    fake = llm(strategist=seq(concepts("Old"), concepts("New")))
    run = await ws.generate((await ws.create_campaign())["id"])
    await ws.work(run["id"], fake)
    approval_id = (await get(client, f"/campaign-runs/{run['id']}", ws.owner)).json()[
        "pending_approval"
    ]["id"]

    empty = await client.post(
        f"/api/v1/approvals/{approval_id}/reject", json={"feedback": " "}, headers=ws.owner
    )
    assert empty.status_code == 422
    rejected = await client.post(
        f"/api/v1/approvals/{approval_id}/reject",
        json={"feedback": "Funnier please"},
        headers=ws.owner,
    )
    assert rejected.status_code == 200
    await ws.work(run["id"], fake)

    detail = (await get(client, f"/campaign-runs/{run['id']}", ws.owner)).json()
    assert detail["status"] == "awaiting_approval"
    assert detail["pending_approval"]["round"] == 2
    assert detail["pending_approval"]["payload"]["concepts"][0]["title"] == "New 1"
    approvals = (await get(client, f"/campaign-runs/{run['id']}/approvals", ws.owner)).json()
    assert [a["status"] for a in approvals["items"]] == ["rejected", "pending"]
    assert (await get(client, f"/campaign-runs/{run['id']}/concepts", ws.owner)).json()[
        "versions"
    ] == 2


# ---------- Versioning ----------


async def test_regenerate_creates_new_version_with_new_brief(client: AsyncClient, ws) -> None:
    campaign = await ws.create_campaign()
    v1 = await ws.generate(campaign["id"])
    await ws.work(v1["id"])
    await approve(client, ws, v1["id"])
    await ws.work(v1["id"])
    await client.patch(
        f"/api/v1/campaigns/{campaign['id']}",
        headers=ws.owner,
        json={"brief": {**BRIEF, "duration_seconds": 15}},
    )

    response = await client.post(f"/api/v1/campaign-runs/{v1['id']}/regenerate", headers=ws.owner)

    assert response.status_code == 202
    v2 = (await get(client, f"/campaign-runs/{response.json()['id']}", ws.owner)).json()
    assert v2["version"] == 2 and v2["parent_run_id"] == v1["id"]
    assert v2["brief_snapshot"]["duration_seconds"] == 15
    old = (await get(client, f"/campaign-runs/{v1['id']}", ws.owner)).json()
    assert old["brief_snapshot"]["duration_seconds"] == 30 and old["status"] == "completed"
    runs = (await get(client, f"/campaigns/{campaign['id']}/runs", ws.owner)).json()["items"]
    assert [r["version"] for r in runs] == [2, 1]


# ---------- Failures, retry, idempotency ----------


async def test_failed_run_retries_from_checkpoint(client: AsyncClient, ws) -> None:
    run = await ws.generate((await ws.create_campaign())["id"])

    failed = await ws.work(run["id"], llm(strategist=seq(LLMError())))
    assert failed.status.value == "failed" and "LLMError" in failed.error_message

    not_failed = await ws.create_campaign(name="Other")
    other_run = await ws.generate(not_failed["id"])
    await ws.work(other_run["id"])
    conflict = await client.post(f"/api/v1/campaign-runs/{other_run['id']}/retry", headers=ws.owner)
    assert conflict.status_code == 409  # only failed/queued runs can be retried

    retried = await client.post(f"/api/v1/campaign-runs/{run['id']}/retry", headers=ws.owner)
    assert retried.status_code == 202 and retried.json()["status"] == "queued"
    resumed = await ws.work(run["id"])
    assert resumed.status.value == "awaiting_approval" and resumed.attempts == 2

    agents = [
        a["agent"]
        for a in (await get(client, f"/campaign-runs/{run['id']}", ws.owner)).json()["agent_runs"]
    ]
    assert agents.count("campaign_manager") == 1  # research was NOT redone


async def test_duplicate_worker_deliveries_are_harmless(client: AsyncClient, ws) -> None:
    run = await ws.generate((await ws.create_campaign())["id"])
    await ws.work(run["id"])
    await ws.work(run["id"])  # redelivered while awaiting a decision: no-op

    approvals = (await get(client, f"/campaign-runs/{run['id']}/approvals", ws.owner)).json()
    assert len(approvals["items"]) == 1
    await approve(client, ws, run["id"])
    await ws.work(run["id"])
    steps = len((await get(client, f"/campaign-runs/{run['id']}", ws.owner)).json()["agent_runs"])
    await ws.work(run["id"])  # redelivered after completion: no-op
    after = (await get(client, f"/campaign-runs/{run['id']}", ws.owner)).json()
    assert after["status"] == "completed" and len(after["agent_runs"]) == steps


async def test_runs_approvals_outputs_are_tenant_isolated(client: AsyncClient, ws) -> None:
    run = await ws.generate((await ws.create_campaign())["id"])
    await ws.work(run["id"])
    detail = (await get(client, f"/campaign-runs/{run['id']}", ws.owner)).json()

    for url in (
        f"/campaign-runs/{run['id']}",
        f"/campaign-runs/{run['id']}/approvals",
        f"/campaign-runs/{run['id']}/concepts",
        f"/campaign-runs/{run['id']}/events",
    ):
        assert (await get(client, url, ws.outsider)).status_code == 404, url
    hijack = await client.post(
        f"/api/v1/approvals/{detail['pending_approval']['id']}/approve",
        json={"concept_id": "C1"},
        headers=ws.outsider,
    )
    assert hijack.status_code == 404


# ---------- Server-Sent Events ----------


def parse_sse(raw: str) -> list[dict]:
    events = []
    for block in raw.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1)
            for line in block.splitlines()
            if ": " in line and not line.startswith(":")
        )
        if "event" in fields:
            events.append(
                {
                    "event": fields["event"],
                    "id": fields.get("id"),
                    "data": json.loads(fields["data"]),
                }
            )
    return events


async def stream(client, ws, run_id, **headers) -> list[dict]:
    async with client.stream(
        "GET", f"/api/v1/campaign-runs/{run_id}/events", headers={**ws.owner, **headers}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        return parse_sse("".join([chunk async for chunk in response.aiter_text()]))


async def test_sse_streams_trace_then_end(client: AsyncClient, ws) -> None:
    run = await ws.generate((await ws.create_campaign())["id"])
    await ws.work(run["id"])
    await approve(client, ws, run["id"])
    await ws.work(run["id"])

    events = await stream(client, ws, run["id"])

    agents = [e for e in events if e["event"] == "agent"]
    assert agents[0]["data"]["agent"] == "campaign_manager"
    assert [int(e["id"]) for e in agents] == list(range(1, len(agents) + 1))
    assert events[-1]["event"] == "end" and events[-1]["data"]["status"] == "completed"

    resumed = await stream(client, ws, run["id"], **{"Last-Event-ID": agents[-3]["id"]})
    assert [e["data"]["agent"] for e in resumed if e["event"] == "agent"] == [
        e["data"]["agent"] for e in agents[-2:]
    ]


async def test_sse_reports_awaiting_approval(client: AsyncClient, ws) -> None:
    run = await ws.generate((await ws.create_campaign())["id"])
    await ws.work(run["id"])
    quick = get_settings().model_copy(
        update={"sse_max_stream_seconds": 0.05, "sse_poll_interval_seconds": 0.01}
    )
    client._transport.app.dependency_overrides[get_settings] = lambda: quick

    events = await stream(client, ws, run["id"])

    status = [e for e in events if e["event"] == "status"][0]["data"]
    assert status["status"] == "awaiting_approval" and status["pending_approval_id"]
    assert all(e["event"] != "end" for e in events)  # paused, not finished
