"""Execute one step of a campaign run's lifecycle (called by the Celery worker).

There is ONE entry point, and it decides what to do from durable state rather than
from the task message - so a duplicated or redelivered task is harmless:

    workflow not started             -> start it
    paused + a decided approval      -> resume with that decision (marks it applied)
    paused, nothing decided yet      -> nothing to do (just sync status)
    started but unfinished (crash)   -> continue from the last checkpoint
    run already finished             -> no-op

Afterwards the run's status is synced from the workflow, and a pending Approval row
is opened when the workflow pauses for concept selection.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes.approval import ConceptDecision
from app.agents.runner import CampaignWorkflow, RunView
from app.agents.schemas import CampaignBrief
from app.campaigns.recorder import RunRecorder
from app.models import Approval, ApprovalStatus, Campaign, CampaignRun, RunStatus

logger = logging.getLogger(__name__)

WORKFLOW_TO_RUN_STATUS = {
    "awaiting_concept_approval": RunStatus.AWAITING_APPROVAL,
    "approved": RunStatus.COMPLETED,
    "needs_human_review": RunStatus.NEEDS_REVIEW,
    "concepts_rejected": RunStatus.CONCEPTS_REJECTED,
}


def _now() -> datetime:
    return datetime.now(UTC)


async def _decided_unapplied_approval(session: AsyncSession, run_id: uuid.UUID) -> Approval | None:
    return await session.scalar(
        select(Approval)
        .where(
            Approval.run_id == run_id,
            Approval.status != ApprovalStatus.PENDING,
            Approval.applied_at.is_(None),
        )
        .order_by(Approval.decided_at.desc())
        .limit(1)
    )


async def _sync(session: AsyncSession, run: CampaignRun, view: RunView) -> None:
    status = WORKFLOW_TO_RUN_STATUS.get(view.status)
    if status is None:  # stream ended without reaching a pause or the end
        run.status = RunStatus.FAILED
        run.error_message = run.error_message or "The workflow stopped unexpectedly."
    else:
        run.status = status
    if run.status.is_terminal:
        run.finished_at = _now()

    if run.status is RunStatus.AWAITING_APPROVAL and view.pending_approval:
        pending = await session.scalar(
            select(Approval).where(
                Approval.run_id == run.id, Approval.status == ApprovalStatus.PENDING
            )
        )
        if pending is None:
            session.add(
                Approval(
                    run_id=run.id,
                    organization_id=run.organization_id,
                    kind="concept_selection",
                    round=view.pending_approval.get("round", 1),
                    payload=view.pending_approval,
                )
            )


async def execute_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    workflow: CampaignWorkflow,
    recorder_session: AsyncSession | None = None,
) -> CampaignRun:
    run = await session.get(CampaignRun, run_id, with_for_update=True)
    if run is None:
        raise LookupError(f"campaign run {run_id} not found")
    if run.status.is_terminal:
        # Finished (or failed) already: a duplicate/redelivered task does nothing.
        # Retrying a failed run is explicit: the API sets it back to QUEUED first.
        return run

    run.status = RunStatus.RUNNING
    run.attempts += 1
    run.error_message = None
    run.finished_at = None
    run.started_at = run.started_at or _now()
    await session.commit()

    thread = str(run.id)
    recorder = RunRecorder(recorder_session or session, run.id)
    # Attached to every LangSmith trace of this run, so traces can be filtered by
    # organization / campaign / run version when debugging agent behaviour.
    trace_metadata = {
        "organization_id": str(run.organization_id),
        "campaign_id": str(run.campaign_id),
        "run_id": str(run.id),
        "run_version": run.version,
        "attempt": run.attempts,
    }
    try:
        view = await workflow.view(thread)
        if view.status == "not_started":
            campaign = await session.get(Campaign, run.campaign_id)
            brief = CampaignBrief.model_validate(
                {
                    **run.brief_snapshot,
                    "brand_id": campaign.brand_id,
                    "campaign_name": campaign.name,
                }
            )
            view = await workflow.start(
                thread, brief, run.brand_snapshot, recorder.on_update, trace_metadata
            )
        elif view.status == "awaiting_concept_approval":
            approval = await _decided_unapplied_approval(session, run.id)
            if approval is not None:
                decision = ConceptDecision.model_validate(approval.decision)
                approval.applied_at = _now()
                await session.commit()
                view = await workflow.resume(thread, decision, recorder.on_update, trace_metadata)
        elif view.status in WORKFLOW_TO_RUN_STATUS:
            pass  # workflow already finished (e.g. crash after finishing): just sync
        else:
            view = await workflow.retry(thread, recorder.on_update, trace_metadata)
    except Exception as exc:
        logger.exception("Campaign run %s failed", run.id)
        await session.rollback()
        run = await session.get(CampaignRun, run_id)
        run.status = RunStatus.FAILED
        run.error_message = f"{type(exc).__name__}: {str(exc)[:500]}"
        run.finished_at = _now()
        await session.commit()
        return run

    run = await session.get(CampaignRun, run_id)
    await session.refresh(run)  # the recorder may have updated it via its own session
    await _sync(session, run, view)
    await session.commit()
    return run
