"""Phase 9: PDF export, evaluation summary and organization dashboard."""

import pymupdf
import pytest
from httpx import AsyncClient

from app.exports.campaign_pdf import build_html, render_pdf
from tests.test_agents import llm, review, seq
from tests.test_campaigns import approve, ws  # noqa: F401  (ws is a fixture)

pytestmark = pytest.mark.anyio


async def finished_run(client: AsyncClient, ws, fake=None, name="Campus Launch") -> dict:  # noqa: F811
    run = await ws.generate((await ws.create_campaign(name=name))["id"])
    await ws.work(run["id"], fake)
    await approve(client, ws, run["id"])
    await ws.work(run["id"], fake)
    return run


def pdf_text(data: bytes) -> str:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


# ---------- PDF ----------


async def test_export_pdf(client: AsyncClient, ws) -> None:  # noqa: F811
    run = await finished_run(client, ws)

    response = await client.get(f"/api/v1/campaign-runs/{run['id']}/export.pdf", headers=ws.owner)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="campus-launch-v1.pdf"' in response.headers["content-disposition"]
    text = pdf_text(response.content)
    for section in (
        "1. Research report",
        "2. Creative strategy",
        "3. Script",
        "4. Storyboard",
        "5. Quality evaluation",
        "(SELECTED)",
        "Page 1 of",
    ):
        assert section in text, section


async def test_export_requires_finished_run_and_access(client: AsyncClient, ws) -> None:  # noqa: F811
    run = await ws.generate((await ws.create_campaign())["id"])
    await ws.work(run["id"])  # paused at approval: nothing final yet
    url = f"/api/v1/campaign-runs/{run['id']}/export.pdf"

    assert (await client.get(url, headers=ws.owner)).status_code == 409
    assert (await client.get(url, headers=ws.outsider)).status_code == 404


def test_pdf_escapes_untrusted_text() -> None:
    evil = "<script>alert(1)</script></td></table><h1>INJECTED</h1>"
    ctx = {
        "campaign_name": f"Evil {evil}",
        "brand_name": "MANO",
        "run": {"version": 1, "status": "completed", "overall_score": 88.0},
        "brief": {
            "objective": evil,
            "platform": "instagram",
            "video_format": "9:16",
            "duration_seconds": 30,
        },
        "final": {
            "creative_strategy": {
                "concepts": [{"concept_id": "C1", "title": evil, "core_idea": evil}],
                "selected_concept_id": "C1",
            }
        },
    }

    html = build_html(ctx)
    assert "<script>" not in html and "&lt;script&gt;" in html
    text = pdf_text(render_pdf(ctx))
    assert "<script>alert(1)</script>" in text  # shown literally, not interpreted


# ---------- Evaluation summary ----------


async def test_evaluation_summary_tracks_revisions(client: AsyncClient, ws) -> None:  # noqa: F811
    fake = llm(critic=seq(review(60, target="storyboard"), review(90)))
    run = await finished_run(client, ws, fake)

    response = await client.get(
        f"/api/v1/campaign-runs/{run['id']}/evaluation-summary", headers=ws.owner
    )

    assert response.status_code == 200, response.text
    summary = response.json()
    assert [i["overall_score"] for i in summary["iterations"]] == [60, 90]
    assert [i["passed"] for i in summary["iterations"]] == [False, True]
    assert summary["iterations"][0]["issue_counts"]["medium"] == 1
    assert summary["score_change"] == 30 and summary["passed"] and summary["threshold"] == 80
    assert summary["revision_history"] == [
        {"iteration": 1, "overall_score": 60.0, "issue_count": 1, "routed_to": "visual_director"}
    ]
    timings = {t["agent"]: t["runs"] for t in summary["agent_timings"]}
    assert (
        timings["critic"] == 2 and timings["visual_director"] == 2 and timings["scriptwriter"] == 1
    )
    assert summary["total_agent_ms"] >= 0


async def test_evaluation_summary_before_critic_is_404(client: AsyncClient, ws) -> None:  # noqa: F811
    run = await ws.generate((await ws.create_campaign())["id"])
    await ws.work(run["id"])

    response = await client.get(
        f"/api/v1/campaign-runs/{run['id']}/evaluation-summary", headers=ws.owner
    )
    assert response.status_code == 404


# ---------- Organization dashboard ----------


async def test_dashboard(client: AsyncClient, ws) -> None:  # noqa: F811
    await finished_run(client, ws, name="Done")
    waiting = await ws.generate((await ws.create_campaign(name="Waiting"))["id"])
    await ws.work(waiting["id"])
    url = f"/api/v1/organizations/{ws.org['id']}/dashboard"

    response = await client.get(url, headers=ws.owner)

    assert response.status_code == 200, response.text
    data = response.json()
    totals = data["totals"]
    assert totals["brands"] == 1 and totals["campaigns"] == 2 and totals["runs"] == 2
    assert totals["runs_completed"] == 1 and totals["runs_awaiting_approval"] == 1
    assert totals["runs_active"] == 1
    quality = data["quality"]
    assert quality["evaluated_runs"] == 1 and quality["average_score"] == 90
    assert quality["approval_rate"] == 1 and quality["first_pass_rate"] == 1
    assert quality["average_revisions"] == 0
    assert {c["name"] for c in data["recent_campaigns"]} == {"Done", "Waiting"}
    agents = {a["agent"] for a in data["agent_activity"]}
    assert {"campaign_manager", "critic", "creative_strategist"} <= agents
    assert data["recent_activity"][0]["campaign_name"] in {"Done", "Waiting"}

    assert (await client.get(url, headers=ws.outsider)).status_code == 404
