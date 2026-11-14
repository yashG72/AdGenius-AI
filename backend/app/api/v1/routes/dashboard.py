"""Organization dashboard: totals, quality, recent campaigns, agent activity, documents."""

from fastapi import APIRouter

from app.api.deps import DbSessionDep, OrgMemberDep
from app.schemas.analytics import Dashboard
from app.schemas.campaign import CampaignRead, RunSummary
from app.services import analytics_service, campaign_service

router = APIRouter(tags=["dashboard"])


@router.get("/organizations/{organization_id}/dashboard", response_model=Dashboard)
async def dashboard(membership: OrgMemberDep, session: DbSessionDep) -> Dashboard:
    data = await analytics_service.organization_dashboard(session, membership.organization_id)
    campaigns, _ = await campaign_service.list_campaigns(
        session, membership.organization_id, brand_id=None, limit=5, offset=0
    )
    runs = await campaign_service.latest_runs(session, [c.id for c in campaigns])
    recent = []
    for campaign in campaigns:
        item = CampaignRead.model_validate(campaign)
        if campaign.id in runs:
            item.latest_run = RunSummary.model_validate(runs[campaign.id][0])
            item.run_count = runs[campaign.id][1]
        recent.append(item)
    return Dashboard(**data, recent_campaigns=recent)
