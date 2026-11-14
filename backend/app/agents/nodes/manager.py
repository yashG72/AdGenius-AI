"""AGENT 1 - Campaign Manager (orchestrator).

Understands and validates the brief, then writes an execution plan for the specialists:
which questions Brand Research must answer, what Competitor Intelligence should focus
on, and whether competitor research runs at all. It never writes campaign content.
Routing itself is deterministic graph code, not an LLM decision.
"""

import logging

from app.agents.context import render_brand_profile, render_brief
from app.agents.deps import AgentDeps, traced
from app.agents.schemas import CampaignBrief, ExecutionPlan

logger = logging.getLogger(__name__)

SYSTEM = """You are the Campaign Manager at a creative advertising agency. You do NOT \
create the campaign. You turn a client brief into an execution plan for specialist \
agents (brand researcher, competitor analyst, creative strategist, scriptwriter, visual \
director, critic).

Write:
- a short summary of what must be produced,
- the hard constraints (duration, platform, format, language, restrictions),
- 3-8 specific questions the brand researcher must answer from the client's own documents,
- what the competitor/market research should focus on,
- measurable success criteria for the final campaign."""

DEFAULT_QUESTIONS = [
    "What products and specifications are relevant to this campaign?",
    "Who is the target audience and what do they care about?",
    "What is the brand's personality and tone of voice?",
    "How is the brand positioned and what are its key messages?",
    "Which claims, words or topics are prohibited in advertising?",
    "What are the visual identity rules (colours, logo, imagery)?",
    "What worked and what failed in past campaigns?",
]

# Platform -> formats that suit it natively (used only for advisory warnings).
NATIVE_FORMATS = {
    "instagram": {"9:16", "4:5", "1:1"},
    "tiktok": {"9:16"},
    "youtube": {"16:9", "9:16"},
    "tv": {"16:9"},
    "linkedin": {"1:1", "16:9", "4:5"},
}


def brief_warnings(brief: CampaignBrief) -> list[str]:
    warnings = []
    native = NATIVE_FORMATS.get(brief.platform)
    if native and brief.video_format not in native:
        warnings.append(
            f"{brief.video_format} is not a native format for {brief.platform} "
            f"(usual: {', '.join(sorted(native))})."
        )
    if brief.platform in ("tiktok", "instagram") and brief.duration_seconds > 90:
        warnings.append(f"{brief.duration_seconds}s is long for short-form {brief.platform} video.")
    return warnings


def make_campaign_manager(deps: AgentDeps):
    @traced("campaign_manager")
    async def campaign_manager(state: dict) -> dict:
        brief = CampaignBrief.model_validate(state["brief"])
        warnings = brief_warnings(brief)
        try:
            plan = await deps.llm.generate(
                ExecutionPlan,
                system=SYSTEM,
                user=f"{render_brief(state['brief'])}\n\n{render_brand_profile(state['brand'])}",
            )
        except Exception as exc:  # planning is helpful, not essential: fall back
            logger.warning("Campaign Manager planning failed, using default plan: %s", exc)
            plan = ExecutionPlan(campaign_summary=brief.objective, key_constraints=[])
        if not plan.brand_research_questions:
            plan.brand_research_questions = DEFAULT_QUESTIONS
        plan.brand_research_questions = plan.brand_research_questions[:8]

        competitor_enabled = brief.competitor_research and deps.competitor_researcher is not None
        reason = (
            "disabled in brief"
            if not brief.competitor_research
            else "web research not configured"
            if deps.competitor_researcher is None
            else ""
        )
        return {
            "plan": {
                **plan.model_dump(),
                "warnings": warnings,
                "competitor_research_enabled": competitor_enabled,
                "competitor_skip_reason": reason,
            },
            "status": "running",
            "revision_count": 0,
            "concept_round": 0,
            "_summary": f"{len(plan.brand_research_questions)} research questions; "
            f"competitor research {'on' if competitor_enabled else 'off (' + reason + ')'}"
            + (f"; warnings: {warnings}" if warnings else ""),
        }

    return campaign_manager
