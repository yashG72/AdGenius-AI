"""Human-in-the-loop concept approval.

`interrupt()` pauses the graph: LangGraph saves a checkpoint and the run returns with
the concepts as the interrupt payload. The run stays paused (even across restarts)
until someone resumes it with a decision:

    {"action": "approve", "concept_id": "C2", "feedback": "optional notes"}
    {"action": "reject", "feedback": "make it funnier, less product-focused"}

On resume the node re-runs from the top and interrupt() returns that decision.
"""

from datetime import UTC, datetime
from typing import Literal

from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field, model_validator

from app.agents.deps import AgentDeps


class ConceptDecision(BaseModel):
    action: Literal["approve", "reject"]
    concept_id: str | None = None
    feedback: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _check(self) -> "ConceptDecision":
        if self.action == "approve" and not self.concept_id:
            raise ValueError("concept_id is required to approve")
        if self.action == "reject" and not (self.feedback or "").strip():
            raise ValueError("feedback is required when rejecting concepts")
        return self


def _event(summary: str) -> dict:
    return {
        "agent": "concept_approval",
        "status": "completed",
        "started_at": datetime.now(UTC).isoformat(),
        "duration_ms": 0.0,
        "summary": summary,
    }


def make_concept_approval(deps: AgentDeps):
    async def concept_approval(state: dict) -> Command:
        concepts = state["concepts"]
        raw = interrupt(
            {
                "type": "concept_approval",
                "round": state.get("concept_round", 1),
                "concepts": concepts["concepts"],
                "recommended_concept_id": concepts["recommended_concept_id"],
                "recommendation_reasoning": concepts["recommendation_reasoning"],
            }
        )
        decision = ConceptDecision.model_validate(raw)  # runner validated it already
        valid_ids = {c["concept_id"] for c in concepts["concepts"]}

        if decision.action == "approve" and decision.concept_id in valid_ids:
            return Command(
                goto="scriptwriter",
                update={
                    "selected_concept_id": decision.concept_id,
                    "concept_feedback": decision.feedback,
                    "status": "running",
                    "events": [_event(f"approved {decision.concept_id}")],
                },
            )
        if decision.action == "reject":
            if state.get("concept_round", 1) >= deps.settings.agent_max_concept_rounds:
                return Command(
                    goto="finalize",
                    update={
                        "status": "concepts_rejected",
                        "concept_feedback": decision.feedback,
                        "events": [_event("rejected; concept round limit reached")],
                    },
                )
            return Command(
                goto="creative_strategist",
                update={
                    "concept_feedback": decision.feedback,
                    "status": "running",
                    "events": [_event(f"rejected: {decision.feedback[:120]}")],
                },
            )
        # Unknown concept id slipped through: ask again rather than guess.
        return Command(goto="concept_approval", update={"events": [_event("invalid decision")]})

    return concept_approval
