"""Deterministic (non-LLM) workflow steps: merge research, route revisions, finalize."""

from datetime import UTC, datetime

from langgraph.types import Command

from app.agents.context import research_digest
from app.agents.deps import AgentDeps, traced


def make_merge_research(deps: AgentDeps):
    @traced("merge_research")
    async def merge_research(state: dict) -> dict:
        digest = research_digest(state.get("brand_research"), state.get("competitor_research"))
        has_competitor = bool(state.get("competitor_research"))
        return {
            "research_digest": digest,
            "_summary": "brand research"
            + (" + competitor research" if has_competitor else " only (no competitor research)"),
        }

    return merge_research


def route_after_critic(deps: AgentDeps):
    def route(state: dict) -> str:
        if state["evaluation"]["passed"]:
            return "finalize"
        if state.get("revision_count", 0) >= deps.settings.agent_max_revisions:
            return "finalize"  # stop looping: preserve the result for human review
        return "revise"

    return route


def make_revise(deps: AgentDeps):
    """Send the Critic's issues to the production agent that must change.

    Script issues -> Scriptwriter (and the storyboard is then rebuilt from the new script).
    Storyboard-only issues -> straight to the Visual Director (script kept as is).
    """

    async def revise(state: dict) -> Command:
        evaluation = state["evaluation"]
        issues = evaluation["issues"]
        target = (
            "scriptwriter" if any(i["target"] == "script" for i in issues) else "visual_director"
        )
        iteration = state.get("revision_count", 0) + 1
        return Command(
            goto=target,
            update={
                "revision_count": iteration,
                "revision_feedback": issues,
                "revision_history": [
                    {
                        "iteration": iteration,
                        "overall_score": evaluation["overall_score"],
                        "issues": issues,
                        "routed_to": target,
                    }
                ],
                "events": [
                    {
                        "agent": "revise",
                        "status": "completed",
                        "started_at": datetime.now(UTC).isoformat(),
                        "duration_ms": 0.0,
                        "summary": f"revision {iteration}: {len(issues)} issues -> {target}",
                    }
                ],
            },
        )

    return revise


def make_finalize(deps: AgentDeps):
    @traced("finalize")
    async def finalize(state: dict) -> dict:
        evaluation = state.get("evaluation")
        if state.get("status") == "concepts_rejected":
            status = "concepts_rejected"
        elif evaluation and evaluation["passed"]:
            status = "approved"
        else:
            status = "needs_human_review"  # never silently approved
        concepts = state.get("concepts") or {}
        final = {
            "status": status,
            "research_report": {
                "brand": state.get("brand_research"),
                "brand_sources": state.get("brand_sources", []),
                "competitors": state.get("competitor_research"),
            },
            "creative_strategy": {
                **concepts,
                "selected_concept_id": state.get("selected_concept_id"),
            },
            "script": state.get("script"),
            "storyboard": state.get("storyboard"),
            "image_prompts": [
                {"scene_number": s["scene_number"], **s["image_prompt"]}
                for s in (state.get("storyboard") or {}).get("scenes", [])
            ],
            "evaluation": evaluation,
            "revision_history": state.get("revision_history", []),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        score = f", score {evaluation['overall_score']:.1f}" if evaluation else ""
        return {"status": status, "final": final, "_summary": f"{status}{score}"}

    return finalize
