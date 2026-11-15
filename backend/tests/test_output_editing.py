"""Human edits of script/storyboard: new versions, normalisation, guards, PDF export."""

import pymupdf
import pytest
from httpx import AsyncClient

from tests.test_campaigns import approve, ws  # noqa: F401  (ws is a fixture)

pytestmark = pytest.mark.anyio


async def finished_run(client: AsyncClient, ws) -> dict:  # noqa: F811
    run = await ws.generate((await ws.create_campaign())["id"])
    await ws.work(run["id"])
    await approve(client, ws, run["id"])
    await ws.work(run["id"])
    return run


async def latest(client, ws, run_id, kind, **params):  # noqa: F811
    response = await client.get(
        f"/api/v1/campaign-runs/{run_id}/{kind}", headers=ws.owner, params=params
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_edited_script_becomes_new_human_version(client: AsyncClient, ws) -> None:  # noqa: F811
    run = await finished_run(client, ws)
    script = (await latest(client, ws, run["id"], "script"))["content"]
    script["scenes"][0]["voiceover"] = "Edited by a human copywriter."
    for scene in script["scenes"]:
        scene["duration_seconds"] = 12  # 3 x 12 = 36s: must be normalised back to 30s

    response = await client.put(
        f"/api/v1/campaign-runs/{run['id']}/script", json=script, headers=ws.owner
    )

    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["version"] == 2 and saved["source"] == "human" and saved["created_by_id"]
    assert saved["content"]["scenes"][-1]["end_time"] == 30
    assert saved["content"]["timing_adjusted"] is True
    current = await latest(client, ws, run["id"], "script")
    assert current["version"] == 2 and current["versions"] == 2
    assert current["content"]["scenes"][0]["voiceover"] == "Edited by a human copywriter."
    original = await latest(client, ws, run["id"], "script", version=1)
    assert original["source"] == "agent"  # the agent's version is kept


async def test_edited_storyboard_keeps_brief_aspect_ratio(client: AsyncClient, ws) -> None:  # noqa: F811
    run = await finished_run(client, ws)
    board = (await latest(client, ws, run["id"], "storyboard"))["content"]
    board["scenes"][0]["image_prompt"]["aspect_ratio"] = "16:9"
    board["scenes"][0]["image_prompt"]["prompt"] = "A new hand-written prompt"

    response = await client.put(
        f"/api/v1/campaign-runs/{run['id']}/storyboard", json=board, headers=ws.owner
    )

    assert response.status_code == 200
    scene = response.json()["content"]["scenes"][0]
    assert scene["image_prompt"]["aspect_ratio"] == "9:16"  # from the brief, not the edit
    assert scene["image_prompt"]["prompt"] == "A new hand-written prompt"


async def test_cannot_edit_unfinished_or_invalid(client: AsyncClient, ws) -> None:  # noqa: F811
    run = await ws.generate((await ws.create_campaign())["id"])
    await ws.work(run["id"])  # paused at concept approval
    body = {
        "title": "T",
        "opening_hook": "h",
        "call_to_action": "c",
        "scenes": [{"scene_number": 1, "duration_seconds": 30, "visual_summary": "v"}],
    }

    busy = await client.put(
        f"/api/v1/campaign-runs/{run['id']}/script", json=body, headers=ws.owner
    )
    assert busy.status_code == 409

    done = await finished_run(client, ws)
    invalid = await client.put(
        f"/api/v1/campaign-runs/{done['id']}/script", json={**body, "scenes": []}, headers=ws.owner
    )
    assert invalid.status_code == 422
    outsider = await client.put(
        f"/api/v1/campaign-runs/{done['id']}/script", json=body, headers=ws.outsider
    )
    assert outsider.status_code == 404


async def test_pdf_export_uses_latest_edit(client: AsyncClient, ws) -> None:  # noqa: F811
    run = await finished_run(client, ws)
    script = (await latest(client, ws, run["id"], "script"))["content"]
    script["title"] = "Human Edited Title"
    await client.put(f"/api/v1/campaign-runs/{run['id']}/script", json=script, headers=ws.owner)

    pdf = await client.get(f"/api/v1/campaign-runs/{run['id']}/export.pdf", headers=ws.owner)

    with pymupdf.open(stream=pdf.content, filetype="pdf") as doc:
        text = "\n".join(page.get_text() for page in doc)
    assert "Human Edited Title" in text
