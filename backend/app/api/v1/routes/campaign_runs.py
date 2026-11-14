"""Campaign runs: detail, live events (SSE), regenerate/retry, approvals and outputs."""

import asyncio
import json
import re
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Header, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import CurrentUserDep, DbSessionDep, SettingsDep
from app.core.exceptions import ConflictError, NotFoundError
from app.exports.campaign_pdf import render_pdf
from app.models import Campaign, CampaignRun, OutputType
from app.schemas.analytics import EvaluationSummary
from app.schemas.campaign import (
    AgentRunRead,
    ApprovalRead,
    ApproveRequest,
    OutputRead,
    OutputVersionInfo,
    RejectRequest,
    RunDetail,
    RunSummary,
)
from app.schemas.common import ListResponse
from app.services import analytics_service, campaign_service
from app.worker import dispatch

router = APIRouter(tags=["campaign runs"])


# ---------- Run detail ----------


@router.get("/campaign-runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep) -> RunDetail:
    run = await campaign_service.get_run_for_user(session, run_id, user.id)
    approval = await campaign_service.pending_approval(session, run.id)
    return RunDetail(
        **RunSummary.model_validate(run).model_dump(),
        brief_snapshot=run.brief_snapshot,
        agent_runs=[
            AgentRunRead.model_validate(a)
            for a in await campaign_service.agent_runs(session, run.id)
        ],
        pending_approval=ApprovalRead.model_validate(approval) if approval else None,
        outputs=[
            OutputVersionInfo(output_type=t, latest_version=latest, versions=count)
            for t, latest, count in await campaign_service.output_index(session, run.id)
        ],
    )


@router.post(
    "/campaign-runs/{run_id}/regenerate",
    response_model=RunSummary,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a NEW run version from the campaign's current brief (old run is kept)",
)
async def regenerate(
    run_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep, background: BackgroundTasks
) -> RunSummary:
    previous = await campaign_service.get_run_for_user(session, run_id, user.id)
    campaign = await campaign_service.get_campaign_for_user(session, previous.campaign_id, user.id)
    run = await campaign_service.create_run(session, campaign, user, parent_run_id=previous.id)
    background.add_task(dispatch.enqueue_campaign_run, run.id)
    return RunSummary.model_validate(run)


@router.post(
    "/campaign-runs/{run_id}/retry",
    response_model=RunSummary,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Continue a failed run from its last checkpoint",
)
async def retry(
    run_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep, background: BackgroundTasks
) -> RunSummary:
    run = await campaign_service.get_run_for_user(session, run_id, user.id)
    run = await campaign_service.requeue_failed_run(session, run)
    background.add_task(dispatch.enqueue_campaign_run, run.id)
    return RunSummary.model_validate(run)


# ---------- Live events (Server-Sent Events) ----------


def _sse(event: str, data: Any, event_id: int | None = None) -> str:
    lines = [f"event: {event}"]
    if event_id is not None:
        lines.append(f"id: {event_id}")  # browser resends it as Last-Event-ID on reconnect
    lines.append("data: " + json.dumps(data, default=str))
    return "\n".join(lines) + "\n\n"


def _status_payload(run: CampaignRun, approval_id: uuid.UUID | None) -> dict[str, Any]:
    return {
        "status": run.status.value,
        "overall_score": run.overall_score,
        "error_message": run.error_message,
        "pending_approval_id": approval_id,
    }


@router.get(
    "/campaign-runs/{run_id}/events",
    summary="Live execution updates (text/event-stream)",
    response_description="SSE stream with `agent`, `status` and `end` events",
)
async def run_events(
    run_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    session: DbSessionDep,
    settings: SettingsDep,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Streams the run's progress until it finishes.

    - `agent`  one execution-trace step (id = its sequence number)
    - `status` whenever the run status changes (incl. awaiting_approval)
    - `end`    the run reached a final status; the stream closes
    Reconnecting with the Last-Event-ID header resumes after that step.
    """
    await campaign_service.get_run_for_user(session, run_id, user.id)  # auth before streaming
    after = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0

    async def stream():
        nonlocal after
        last_status, started, last_sent = None, time.monotonic(), time.monotonic()
        while not await request.is_disconnected():
            for step in await campaign_service.agent_runs(session, run_id, after):
                yield _sse("agent", AgentRunRead.model_validate(step).model_dump(), step.sequence)
                after, last_sent = step.sequence, time.monotonic()

            run = await session.get(CampaignRun, run_id, populate_existing=True)
            approval = await campaign_service.pending_approval(session, run_id)
            payload = _status_payload(run, approval.id if approval else None)
            if payload != last_status:
                yield _sse("status", payload)
                last_status, last_sent = payload, time.monotonic()
            await session.commit()  # end the read transaction: next poll sees new commits

            if run.status.is_terminal:
                yield _sse("end", payload)
                return
            if time.monotonic() - started > settings.sse_max_stream_seconds:
                return  # client reconnects with Last-Event-ID
            if time.monotonic() - last_sent > settings.sse_heartbeat_seconds:
                yield ": keep-alive\n\n"  # SSE comment: keeps proxies from closing the stream
                last_sent = time.monotonic()
            await asyncio.sleep(settings.sse_poll_interval_seconds)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- Approvals ----------


@router.get("/campaign-runs/{run_id}/approvals", response_model=ListResponse[ApprovalRead])
async def list_approvals(
    run_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep
) -> ListResponse[ApprovalRead]:
    await campaign_service.get_run_for_user(session, run_id, user.id)
    approvals = await campaign_service.list_approvals(session, run_id)
    return ListResponse(items=[ApprovalRead.model_validate(a) for a in approvals])


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRead)
async def approve(
    approval_id: uuid.UUID,
    data: ApproveRequest,
    user: CurrentUserDep,
    session: DbSessionDep,
    background: BackgroundTasks,
) -> ApprovalRead:
    approval = await campaign_service.get_approval_for_user(
        session, approval_id, user.id, lock=True
    )
    approval, run = await campaign_service.decide(
        session, approval, user, approve=True, concept_id=data.concept_id, feedback=data.feedback
    )
    background.add_task(dispatch.enqueue_campaign_run, run.id)
    return ApprovalRead.model_validate(approval)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRead)
async def reject(
    approval_id: uuid.UUID,
    data: RejectRequest,
    user: CurrentUserDep,
    session: DbSessionDep,
    background: BackgroundTasks,
) -> ApprovalRead:
    approval = await campaign_service.get_approval_for_user(
        session, approval_id, user.id, lock=True
    )
    approval, run = await campaign_service.decide(
        session, approval, user, approve=False, concept_id=None, feedback=data.feedback
    )
    background.add_task(dispatch.enqueue_campaign_run, run.id)
    return ApprovalRead.model_validate(approval)


# ---------- Evaluation dashboard & export ----------


@router.get("/campaign-runs/{run_id}/evaluation-summary", response_model=EvaluationSummary)
async def evaluation_summary(
    run_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep
) -> EvaluationSummary:
    """Score trend across Critic iterations, issues, revisions and agent timings."""
    run = await campaign_service.get_run_for_user(session, run_id, user.id)
    return EvaluationSummary(**await analytics_service.evaluation_summary(session, run))


@router.get(
    "/campaign-runs/{run_id}/export.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    summary="Download the finished campaign as a PDF",
)
async def export_pdf(run_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep) -> Response:
    run = await campaign_service.get_run_for_user(session, run_id, user.id)
    try:
        final, _ = await campaign_service.get_output(
            session, run.id, OutputType.FINAL_CAMPAIGN, None
        )
    except NotFoundError as exc:
        raise ConflictError("The campaign is not finished yet - nothing to export.") from exc
    campaign = await session.get(Campaign, run.campaign_id)
    context = {
        "campaign_name": campaign.name,
        "brand_name": run.brand_snapshot.get("name", ""),
        "run": {
            "version": run.version,
            "status": run.status.value,
            "overall_score": run.overall_score,
        },
        "brief": run.brief_snapshot,
        "final": final.content,
    }
    pdf = await run_in_threadpool(render_pdf, context)  # CPU work off the event loop
    filename = f"{_slug(campaign.name)}-v{run.version}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60] or "campaign"


# ---------- Outputs ----------


async def _output(session, user, run_id, output_type: OutputType, version: int | None):
    await campaign_service.get_run_for_user(session, run_id, user.id)
    output, total = await campaign_service.get_output(session, run_id, output_type, version)
    return OutputRead(
        run_id=output.run_id,
        output_type=output.output_type,
        version=output.version,
        versions=total,
        content=output.content,
        created_at=output.created_at,
    )


VersionQuery = Annotated[int | None, Query(ge=1, description="Default: latest version")]


@router.get("/campaign-runs/{run_id}/outputs/{output_type}", response_model=OutputRead)
async def get_output(
    run_id: uuid.UUID,
    output_type: OutputType,
    user: CurrentUserDep,
    session: DbSessionDep,
    version: VersionQuery = None,
) -> OutputRead:
    return await _output(session, user, run_id, output_type, version)


def _shortcut(path: str, output_type: OutputType) -> None:
    async def endpoint(
        run_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep, version: VersionQuery = None
    ) -> OutputRead:
        return await _output(session, user, run_id, output_type, version)

    endpoint.__name__ = f"get_{path}"
    router.add_api_route(
        f"/campaign-runs/{{run_id}}/{path}",
        endpoint,
        methods=["GET"],
        response_model=OutputRead,
        summary=f"Latest (or ?version=) {output_type.value.replace('_', ' ')}",
    )


for _path, _type in {
    "concepts": OutputType.CONCEPTS,
    "script": OutputType.SCRIPT,
    "storyboard": OutputType.STORYBOARD,
    "evaluation": OutputType.EVALUATION,
}.items():
    _shortcut(_path, _type)
