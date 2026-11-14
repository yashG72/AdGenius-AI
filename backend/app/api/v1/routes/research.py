"""Live competitor & market research for a brand.

Runs synchronously but within a strict budget (WEB_RESEARCH_MAX_QUERIES searches, cached
for 24 h). In phase 7 the Competitor Intelligence Agent runs the same service inside the
background worker as part of a campaign run.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import CurrentUserDep, DbSessionDep, SettingsDep
from app.llm.client import LLMNotConfiguredError, get_llm
from app.research.competitor import (
    BrandResearchContext,
    CompetitorReport,
    CompetitorResearchService,
)
from app.research.web_search import WebSearchNotConfiguredError, get_web_search_service
from app.services import brand_service

router = APIRouter(prefix="/brands/{brand_id}/research", tags=["research"])


class CompetitorResearchRequest(BaseModel):
    focus: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = Field(
        default=None, description="Optional angle, e.g. 'Instagram campaigns aimed at students'."
    )
    max_queries: int | None = Field(default=None, ge=1, le=15)


def get_competitor_research_service(settings: SettingsDep) -> CompetitorResearchService:
    search = get_web_search_service()
    if search is None:
        raise WebSearchNotConfiguredError()
    llm = get_llm()
    if llm is None:
        raise LLMNotConfiguredError()
    return CompetitorResearchService(search=search, llm=llm, settings=settings)


ResearchDep = Annotated[CompetitorResearchService, Depends(get_competitor_research_service)]


@router.post(
    "/competitors",
    response_model=CompetitorReport,
    summary="Research competitors and market trends on the live web (cited)",
)
async def research_competitors(
    brand_id: uuid.UUID,
    data: CompetitorResearchRequest,
    user: CurrentUserDep,
    session: DbSessionDep,
    service: ResearchDep,
) -> CompetitorReport:
    brand, _ = await brand_service.get_brand_for_user(session, brand_id, user.id)
    context = BrandResearchContext(
        brand_name=brand.name,
        industry=brand.industry,
        description=brand.description,
        product=brand.product_information,
        target_audience=brand.target_audience,
        positioning=brand.positioning,
        known_competitors=tuple(c["name"] for c in brand.competitors if c.get("name")),
        focus=data.focus,
    )
    return await service.research(context, max_queries=data.max_queries)
