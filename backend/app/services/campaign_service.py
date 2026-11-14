"""Campaigns, runs, approvals and outputs (HTTP side).

Every read goes through a single query that joins the user's membership in the owning
organization, so a resource from another tenant is indistinguishable from a missing
one (404). Runs are versioned and immutable inputs are snapshotted at creation.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import brand_snapshot
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models import (
    AgentRun,
    Approval,
    ApprovalStatus,
    Brand,
    Campaign,
    CampaignOutput,
    CampaignRun,
    Membership,
    OutputType,
    RunStatus,
    User,
)
from app.schemas.campaign import CampaignCreate, CampaignUpdate


def _member_join(query: Select, org_column, user_id: uuid.UUID) -> Select:
    return query.join(
        Membership,
        (Membership.organization_id == org_column) & (Membership.user_id == user_id),
    )


# ---------- Campaigns ----------


async def get_campaign_for_user(
    session: AsyncSession, campaign_id: uuid.UUID, user_id: uuid.UUID
) -> Campaign:
    query = (
        select(Campaign)
        .join(Brand, Brand.id == Campaign.brand_id)
        .where(Campaign.id == campaign_id, Brand.deleted_at.is_(None))
    )
    campaign = await session.scalar(_member_join(query, Campaign.organization_id, user_id))
    if campaign is None:
        raise NotFoundError("Campaign not found.")
    return campaign


async def create_campaign(
    session: AsyncSession, user: User, brand: Brand, data: CampaignCreate
) -> Campaign:
    campaign = Campaign(
        organization_id=brand.organization_id,
        brand_id=brand.id,
        created_by_id=user.id,
        name=data.name,
        brief=data.brief.model_dump(mode="json"),
    )
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)
    return campaign


async def update_campaign(
    session: AsyncSession, campaign: Campaign, data: CampaignUpdate
) -> Campaign:
    if data.name is not None:
        campaign.name = data.name
    if data.brief is not None:
        campaign.brief = data.brief.model_dump(mode="json")
    await session.commit()
    await session.refresh(campaign)
    return campaign


async def list_campaigns(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    brand_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[Campaign], int]:
    query = (
        select(Campaign)
        .join(Brand, Brand.id == Campaign.brand_id)
        .where(Campaign.organization_id == organization_id, Brand.deleted_at.is_(None))
    )
    if brand_id is not None:
        query = query.where(Campaign.brand_id == brand_id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    campaigns = await session.scalars(
        query.order_by(Campaign.updated_at.desc(), Campaign.id).limit(limit).offset(offset)
    )
    return list(campaigns), total or 0


async def latest_runs(
    session: AsyncSession, campaign_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[CampaignRun, int]]:
    """Latest run and run count per campaign (one query each, not one per campaign)."""
    if not campaign_ids:
        return {}
    counts = dict(
        (
            await session.execute(
                select(CampaignRun.campaign_id, func.count())
                .where(CampaignRun.campaign_id.in_(campaign_ids))
                .group_by(CampaignRun.campaign_id)
            )
        ).all()
    )
    latest = await session.scalars(
        select(CampaignRun)
        .where(CampaignRun.campaign_id.in_(campaign_ids))
        .ext(distinct_on(CampaignRun.campaign_id))  # PostgreSQL DISTINCT ON: 1 row per campaign
        .order_by(CampaignRun.campaign_id, CampaignRun.version.desc())
    )
    return {run.campaign_id: (run, counts.get(run.campaign_id, 0)) for run in latest}


# ---------- Runs ----------


async def create_run(
    session: AsyncSession,
    campaign: Campaign,
    user: User,
    *,
    parent_run_id: uuid.UUID | None = None,
) -> CampaignRun:
    """New immutable version: snapshots the current brief and brand profile."""
    brand = await session.get(Brand, campaign.brand_id)
    active = await session.scalar(
        select(CampaignRun.id).where(
            CampaignRun.campaign_id == campaign.id,
            CampaignRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
        )
    )
    if active:
        raise ConflictError(
            "This campaign already has a run in progress.", details={"run_id": str(active)}
        )
    version = (
        await session.scalar(
            select(func.max(CampaignRun.version)).where(CampaignRun.campaign_id == campaign.id)
        )
        or 0
    ) + 1
    run = CampaignRun(
        campaign_id=campaign.id,
        organization_id=campaign.organization_id,
        version=version,
        parent_run_id=parent_run_id,
        triggered_by_id=user.id,
        status=RunStatus.QUEUED,
        brief_snapshot=campaign.brief,
        brand_snapshot=brand_snapshot(brand),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def get_run_for_user(
    session: AsyncSession, run_id: uuid.UUID, user_id: uuid.UUID
) -> CampaignRun:
    query = (
        select(CampaignRun)
        .join(Campaign, Campaign.id == CampaignRun.campaign_id)
        .join(Brand, Brand.id == Campaign.brand_id)
        .where(CampaignRun.id == run_id, Brand.deleted_at.is_(None))
    )
    run = await session.scalar(_member_join(query, CampaignRun.organization_id, user_id))
    if run is None:
        raise NotFoundError("Campaign run not found.")
    return run


async def list_runs(session: AsyncSession, campaign_id: uuid.UUID) -> list[CampaignRun]:
    return list(
        await session.scalars(
            select(CampaignRun)
            .where(CampaignRun.campaign_id == campaign_id)
            .order_by(CampaignRun.version.desc())
        )
    )


async def requeue_failed_run(session: AsyncSession, run: CampaignRun) -> CampaignRun:
    """Retry a failed (or never-dispatched) run from its last checkpoint."""
    if run.status not in (RunStatus.FAILED, RunStatus.QUEUED):
        raise ConflictError(f"Only failed or queued runs can be retried (status: {run.status}).")
    run.status = RunStatus.QUEUED
    run.error_message = None
    run.finished_at = None
    await session.commit()
    await session.refresh(run)
    return run


async def agent_runs(session: AsyncSession, run_id: uuid.UUID, after: int = 0) -> list[AgentRun]:
    return list(
        await session.scalars(
            select(AgentRun)
            .where(AgentRun.run_id == run_id, AgentRun.sequence > after)
            .order_by(AgentRun.sequence)
        )
    )


async def pending_approval(session: AsyncSession, run_id: uuid.UUID) -> Approval | None:
    return await session.scalar(
        select(Approval).where(Approval.run_id == run_id, Approval.status == ApprovalStatus.PENDING)
    )


# ---------- Approvals ----------


async def list_approvals(session: AsyncSession, run_id: uuid.UUID) -> list[Approval]:
    return list(
        await session.scalars(
            select(Approval).where(Approval.run_id == run_id).order_by(Approval.created_at)
        )
    )


async def get_approval_for_user(
    session: AsyncSession, approval_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
) -> Approval:
    query = select(Approval).where(Approval.id == approval_id)
    query = _member_join(query, Approval.organization_id, user_id)
    if lock:
        query = query.with_for_update(of=Approval)  # two reviewers clicking at once
    approval = await session.scalar(query)
    if approval is None:
        raise NotFoundError("Approval not found.")
    return approval


async def decide(
    session: AsyncSession,
    approval: Approval,
    user: User,
    *,
    approve: bool,
    concept_id: str | None,
    feedback: str | None,
) -> tuple[Approval, CampaignRun]:
    if approval.status is not ApprovalStatus.PENDING:
        raise ConflictError(f"This approval was already {approval.status.value}.")
    run = await session.get(CampaignRun, approval.run_id)
    if run.status is not RunStatus.AWAITING_APPROVAL:
        raise ConflictError(f"The run is not awaiting approval (status: {run.status.value}).")
    if approve:
        offered = {c["concept_id"] for c in approval.payload.get("concepts", [])}
        if concept_id not in offered:
            raise BadRequestError(
                f"Unknown concept_id. Choose one of: {', '.join(sorted(offered))}."
            )
        decision = {"action": "approve", "concept_id": concept_id, "feedback": feedback}
    else:
        decision = {"action": "reject", "concept_id": None, "feedback": feedback}

    approval.status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
    approval.decision = decision
    approval.decided_by_id = user.id
    approval.decided_at = datetime.now(UTC)
    run.status = RunStatus.QUEUED  # the worker picks up the decision next
    await session.commit()
    await session.refresh(approval)
    await session.refresh(run)
    return approval, run


# ---------- Outputs ----------


async def output_index(
    session: AsyncSession, run_id: uuid.UUID
) -> list[tuple[OutputType, int, int]]:
    rows = await session.execute(
        select(CampaignOutput.output_type, func.max(CampaignOutput.version), func.count())
        .where(CampaignOutput.run_id == run_id)
        .group_by(CampaignOutput.output_type)
    )
    return [(t, latest, count) for t, latest, count in rows.all()]


async def get_output(
    session: AsyncSession, run_id: uuid.UUID, output_type: OutputType, version: int | None
) -> tuple[CampaignOutput, int]:
    query = select(CampaignOutput).where(
        CampaignOutput.run_id == run_id, CampaignOutput.output_type == output_type
    )
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    if version is not None:
        query = query.where(CampaignOutput.version == version)
    output = await session.scalar(query.order_by(CampaignOutput.version.desc()).limit(1))
    if output is None:
        raise NotFoundError(f"No {output_type.value.replace('_', ' ')} for this run yet.")
    return output, total
