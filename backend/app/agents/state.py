"""The typed state shared by all agent nodes.

Each node returns a *partial* update; LangGraph merges it into the state. Fields
annotated with `operator.add` are append-only logs (events, revision history): parallel
nodes can both append without overwriting each other.

Values are plain JSON-compatible dicts (Pydantic models are dumped before storing), so
every checkpoint serialises cleanly to PostgreSQL.
"""

import operator
from typing import Annotated, Any, Literal, TypedDict

RunStatus = Literal[
    "running",
    "awaiting_concept_approval",
    "approved",  # passed the Critic
    "needs_human_review",  # still below threshold after max revisions
    "concepts_rejected",  # client rejected concepts more times than allowed
]


class AgentEvent(TypedDict, total=False):
    agent: str
    status: Literal["completed", "skipped", "failed"]
    started_at: str
    duration_ms: float
    summary: str


class RevisionRecord(TypedDict):
    iteration: int
    overall_score: float
    issues: list[dict[str, Any]]
    routed_to: str


class CampaignState(TypedDict, total=False):
    # ----- inputs (set once by the runner) -----
    brief: dict[str, Any]
    brand: dict[str, Any]  # trusted snapshot of the brand profile from PostgreSQL

    # ----- Campaign Manager -----
    plan: dict[str, Any]

    # ----- research (parallel branches) -----
    brand_research: dict[str, Any] | None
    brand_sources: list[dict[str, Any]]
    competitor_research: dict[str, Any] | None
    research_digest: str

    # ----- strategy & human approval -----
    concepts: dict[str, Any]
    concept_round: int
    concept_feedback: str | None
    selected_concept_id: str | None

    # ----- production -----
    script: dict[str, Any] | None
    storyboard: dict[str, Any] | None

    # ----- quality loop -----
    evaluation: dict[str, Any] | None
    revision_count: int
    revision_feedback: list[dict[str, Any]]
    revision_history: Annotated[list[RevisionRecord], operator.add]

    # ----- outcome & trace -----
    status: RunStatus
    final: dict[str, Any] | None
    events: Annotated[list[AgentEvent], operator.add]
