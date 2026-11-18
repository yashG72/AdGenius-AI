"""AGENT 3 - Competitor Intelligence Agent (live web research).

Runs the Phase 6 research service (Tavily + evidence-grounded synthesis). Competitor
research enriches the campaign but is not essential, so failures DEGRADE the run
(recorded in the trace) instead of failing it.
"""

import logging

from app.agents.deps import AgentDeps, traced
from app.research.competitor import BrandResearchContext

logger = logging.getLogger(__name__)


def make_competitor_analyst(deps: AgentDeps):
    @traced("competitor_research")
    async def competitor_research(state: dict) -> dict:
        plan = state["plan"]
        if not plan.get("competitor_research_enabled"):
            return {
                "competitor_research": None,
                "_status": "skipped",
                "_summary": f"skipped: {plan.get('competitor_skip_reason') or 'not enabled'}",
            }

        brand, brief = state["brand"], state["brief"]
        # Built ONLY from the brief, never from the Campaign Manager's LLM-written focus:
        # the focus is part of the research-plan cache key, and LLM wording changes on
        # every run, so it made every regeneration re-plan and re-spend ~6 search credits.
        focus = " ".join(
            part
            for part in [
                brief.get("competitor_focus"),
                f"{brief.get('platform')} advertising for {brief.get('target_audience')}",
            ]
            if part
        )[:500]
        context = BrandResearchContext(
            brand_name=brand["name"],
            industry=brand.get("industry"),
            description=brand.get("description"),
            product=brief.get("product_description") or brand.get("product_information"),
            target_audience=brief.get("target_audience") or brand.get("target_audience"),
            positioning=brand.get("positioning"),
            known_competitors=tuple(
                c["name"] for c in brand.get("competitors") or [] if c.get("name")
            ),
            focus=focus,
        )
        try:
            report = await deps.competitor_researcher.research(context)
        except Exception as exc:
            logger.warning("Competitor research failed; continuing without it: %s", exc)
            return {
                "competitor_research": None,
                "_status": "failed",
                "_summary": f"failed ({type(exc).__name__}); continuing without web research",
            }
        return {
            "competitor_research": report.model_dump(mode="json"),
            "_summary": f"{len(report.competitors)} competitors, {len(report.market_trends)} "
            f"trends, {len(report.sources)} sources ({report.search_calls} web searches)",
        }

    return competitor_research
