"""Campaign endpoints: create/edit campaigns and launch versioned generation runs."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.api.deps import CurrentUserDep, DbSessionDep, OrgMemberDep
from app.api.rate_limits import CAMPAIGN_RUNS, limit_by_user
from app.models import Campaign
from app.schemas.campaign import (
    CampaignCreate,
    CampaignRead,
    CampaignUpdate,
    RunSummary,
)
from app.schemas.common import ListResponse, PageResponse
from app.services import brand_service, campaign_service
from app.worker import dispatch

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


async def _read(session, campaign: Campaign) -> CampaignRead:
    latest = (await campaign_service.latest_runs(session, [campaign.id])).get(campaign.id)
    data = CampaignRead.model_validate(campaign)
    if latest:
        data.latest_run, data.run_count = RunSummary.model_validate(latest[0]), latest[1]
    return data


@router.post("", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    data: CampaignCreate, user: CurrentUserDep, session: DbSessionDep
) -> CampaignRead:
    brand, _ = await brand_service.get_brand_for_user(session, data.brand_id, user.id)
    campaign = await campaign_service.create_campaign(session, user, brand, data)
    return await _read(session, campaign)


@router.get("", response_model=PageResponse[CampaignRead])
async def list_campaigns(
    membership: OrgMemberDep,  # requires ?organization_id=
    session: DbSessionDep,
    brand_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PageResponse[CampaignRead]:
    campaigns, total = await campaign_service.list_campaigns(
        session, membership.organization_id, brand_id=brand_id, limit=limit, offset=offset
    )
    runs = await campaign_service.latest_runs(session, [c.id for c in campaigns])
    items = []
    for campaign in campaigns:
        item = CampaignRead.model_validate(campaign)
        if campaign.id in runs:
            run, count = runs[campaign.id]
            item.latest_run, item.run_count = RunSummary.model_validate(run), count
        items.append(item)
    return PageResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{campaign_id}", response_model=CampaignRead)
async def get_campaign(
    campaign_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep
) -> CampaignRead:
    campaign = await campaign_service.get_campaign_for_user(session, campaign_id, user.id)
    return await _read(session, campaign)


@router.patch("/{campaign_id}", response_model=CampaignRead)
async def update_campaign(
    campaign_id: uuid.UUID, data: CampaignUpdate, user: CurrentUserDep, session: DbSessionDep
) -> CampaignRead:
    campaign = await campaign_service.get_campaign_for_user(session, campaign_id, user.id)
    campaign = await campaign_service.update_campaign(session, campaign, data)
    return await _read(session, campaign)


@router.post(
    "/{campaign_id}/generate",
    response_model=RunSummary,
    dependencies=[Depends(limit_by_user(CAMPAIGN_RUNS))],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a new versioned generation run (runs in the background worker)",
)
async def generate(
    campaign_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSessionDep,
    background: BackgroundTasks,
) -> RunSummary:
    campaign = await campaign_service.get_campaign_for_user(session, campaign_id, user.id)
    run = await campaign_service.create_run(session, campaign, user)
    background.add_task(dispatch.enqueue_campaign_run, run.id)
    return RunSummary.model_validate(run)


@router.get("/{campaign_id}/runs", response_model=ListResponse[RunSummary])
async def list_runs(
    campaign_id: uuid.UUID, user: CurrentUserDep, session: DbSessionDep
) -> ListResponse[RunSummary]:
    await campaign_service.get_campaign_for_user(session, campaign_id, user.id)
    runs = await campaign_service.list_runs(session, campaign_id)
    return ListResponse(items=[RunSummary.model_validate(r) for r in runs])
