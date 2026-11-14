"""The campaign workflow graph (LangGraph).

    START -> campaign_manager -> brand_research ----------\
                              -> competitor_research ------> merge_research
          -> creative_strategist -> concept_approval (human interrupt)
                 ^------- reject ---------|
          -> scriptwriter -> visual_director -> critic
                 critic --pass / limit--> finalize -> END
                 critic --fail--> revise --> scriptwriter | visual_director

All transitions are fixed in code ("supervisor-controlled"); agents never message each
other freely. brand_research and competitor_research run IN PARALLEL (same superstep)
and merge_research runs once both are done.

LLM-backed nodes get a retry policy: transient model failures and unusable outputs are
retried with exponential backoff before the run is considered failed.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app.agents.deps import AgentDeps, AgentOutputError
from app.agents.nodes.approval import make_concept_approval
from app.agents.nodes.brand_researcher import make_brand_researcher
from app.agents.nodes.competitor_analyst import make_competitor_analyst
from app.agents.nodes.critic import make_critic
from app.agents.nodes.flow import (
    make_finalize,
    make_merge_research,
    make_revise,
    route_after_critic,
)
from app.agents.nodes.manager import make_campaign_manager
from app.agents.nodes.production import make_scriptwriter, make_visual_director
from app.agents.nodes.strategist import make_strategist
from app.agents.state import CampaignState
from app.llm.client import LLMError


def build_graph(deps: AgentDeps) -> StateGraph:
    retry = RetryPolicy(
        max_attempts=deps.settings.agent_max_attempts,
        initial_interval=deps.settings.agent_retry_initial_seconds,
        retry_on=(LLMError, AgentOutputError),
    )
    g = StateGraph(CampaignState)

    g.add_node("campaign_manager", make_campaign_manager(deps))
    g.add_node("brand_research", make_brand_researcher(deps), retry_policy=retry)
    g.add_node("competitor_research", make_competitor_analyst(deps))
    g.add_node("merge_research", make_merge_research(deps))
    g.add_node("creative_strategist", make_strategist(deps), retry_policy=retry)
    g.add_node(
        "concept_approval",
        make_concept_approval(deps),
        destinations=("scriptwriter", "creative_strategist", "finalize", "concept_approval"),
    )
    g.add_node("scriptwriter", make_scriptwriter(deps), retry_policy=retry)
    g.add_node("visual_director", make_visual_director(deps), retry_policy=retry)
    g.add_node("critic", make_critic(deps), retry_policy=retry)
    g.add_node("revise", make_revise(deps), destinations=("scriptwriter", "visual_director"))
    g.add_node("finalize", make_finalize(deps))

    g.add_edge(START, "campaign_manager")
    # Fan-out: both research branches run in parallel...
    g.add_edge("campaign_manager", "brand_research")
    g.add_edge("campaign_manager", "competitor_research")
    # ...and fan-in: merge waits for both.
    g.add_edge(["brand_research", "competitor_research"], "merge_research")
    g.add_edge("merge_research", "creative_strategist")
    g.add_edge("creative_strategist", "concept_approval")
    # concept_approval routes itself via Command (approve / reject / limit reached).
    g.add_edge("scriptwriter", "visual_director")
    g.add_edge("visual_director", "critic")
    g.add_conditional_edges("critic", route_after_critic(deps), ["finalize", "revise"])
    # revise routes itself via Command to the agent that must change.
    g.add_edge("finalize", END)
    return g
