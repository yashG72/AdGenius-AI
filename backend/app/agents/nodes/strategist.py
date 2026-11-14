"""AGENT 4 - Creative Strategist.

Turns the brief + merged research into N distinct campaign concepts and recommends one.
If the client rejected the previous concepts, their feedback and the rejected titles
are included so the new round goes in a genuinely different direction.
"""

from app.agents.context import render_brief
from app.agents.deps import AgentDeps, AgentOutputError, traced
from app.agents.schemas import ConceptSet

SYSTEM = """You are the Creative Strategist at an award-winning advertising agency.

From the brief and the research, develop exactly {n} DISTINCT campaign concepts - \
different creative angles, emotions and storytelling approaches, not variations of one \
idea. Each concept needs a scroll-stopping opening hook suited to the platform, a clear \
key message, a unique selling proposition grounded in the research, a call to action, \
and reasoning that ties it to the brand, audience and competitive landscape.

Respect every prohibited claim and restriction in the research. Recommend the strongest \
concept and explain why."""


def make_strategist(deps: AgentDeps):
    @traced("creative_strategist")
    async def creative_strategist(state: dict) -> dict:
        n = int(state["brief"].get("num_concepts", 3))
        user = f"{render_brief(state['brief'])}\n\n{state['research_digest']}"
        previous = state.get("concepts")
        if previous and state.get("concept_feedback"):
            titles = "; ".join(c["title"] for c in previous["concepts"])
            user += (
                f"\n\n<client_feedback>\nThe client REJECTED these concepts: {titles}.\n"
                f"Their feedback: {state['concept_feedback']}\n"
                "Create new concepts that address this feedback.\n</client_feedback>"
            )

        result = await deps.llm.generate(ConceptSet, system=SYSTEM.format(n=n), user=user)
        if len(result.concepts) < n:
            raise AgentOutputError(f"expected {n} concepts, got {len(result.concepts)}")

        # Stable ids C1..Cn regardless of what the model called them.
        concepts = result.concepts[:n]
        old_to_new = {c.concept_id: f"C{i}" for i, c in enumerate(concepts, start=1)}
        for concept in concepts:
            concept.concept_id = old_to_new[concept.concept_id]
        result.concepts = concepts
        result.recommended_concept_id = old_to_new.get(result.recommended_concept_id, "C1")

        round_number = state.get("concept_round", 0) + 1
        return {
            "concepts": result.model_dump(),
            "concept_round": round_number,
            "selected_concept_id": None,
            "status": "awaiting_concept_approval",
            "_summary": f"round {round_number}: {len(concepts)} concepts "
            f"({', '.join(c.title for c in concepts)}); recommends "
            f"{result.recommended_concept_id}",
        }

    return creative_strategist
