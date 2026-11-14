"""Start, resume and inspect campaign workflow runs.

One LangGraph thread per campaign run (thread_id = the run's UUID). The checkpointer
stores every step under that thread, which is what makes runs pausable and resumable.
Phase 8 wraps this in Celery tasks and REST endpoints.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from app.agents.deps import AgentDeps
from app.agents.graph import build_graph
from app.agents.nodes.approval import ConceptDecision
from app.agents.schemas import CampaignBrief
from app.core.exceptions import BadRequestError, ConflictError


@dataclass
class RunView:
    thread_id: str
    status: str  # not_started | running | awaiting_concept_approval | approved | ...
    pending_approval: dict[str, Any] | None
    values: dict[str, Any] = field(default_factory=dict)
    next_steps: tuple[str, ...] = ()


# Called after every node finishes: (node_name, partial_state_update).
OnUpdate = Callable[[str, dict[str, Any]], Awaitable[None]]


class CampaignWorkflow:
    def __init__(self, deps: AgentDeps, checkpointer: BaseCheckpointSaver) -> None:
        self.graph = build_graph(deps).compile(checkpointer=checkpointer)

    @staticmethod
    def _config(thread_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 100,
            "run_name": "campaign_workflow",  # shows up in LangSmith traces
            "tags": ["adgenius", "campaign"],
            "metadata": {"thread_id": thread_id, **(metadata or {})},
        }

    async def view(self, thread_id: str) -> RunView:
        snapshot = await self.graph.aget_state(self._config(thread_id))
        if not snapshot.values:
            return RunView(thread_id, "not_started", None)
        interrupts = [i.value for task in snapshot.tasks for i in task.interrupts]
        status = "awaiting_concept_approval" if interrupts else snapshot.values.get("status")
        if status == "awaiting_concept_approval" and not interrupts:
            status = "running"  # concepts made, interrupt not reached yet
        return RunView(
            thread_id=thread_id,
            status=status or "running",
            pending_approval=interrupts[0] if interrupts else None,
            values=dict(snapshot.values),
            next_steps=tuple(snapshot.next),
        )

    async def _drive(self, graph_input: Any, config: dict[str, Any], on_update: OnUpdate | None):
        """Run the graph, reporting each node's update as soon as it completes.

        stream_mode="updates" yields {node_name: update} per finished node - this is
        what lets the worker persist progress live instead of only at the very end.
        """
        async for chunk in self.graph.astream(graph_input, config, stream_mode="updates"):
            if on_update is None:
                continue
            for node, update in chunk.items():
                if node != "__interrupt__" and isinstance(update, dict):
                    await on_update(node, update)

    async def start(
        self,
        thread_id: str,
        brief: CampaignBrief,
        brand: dict[str, Any],
        on_update: OnUpdate | None = None,
    ) -> RunView:
        """Run from the beginning until the concept-approval pause (or the end)."""
        if (await self.view(thread_id)).status != "not_started":
            raise ConflictError("This run has already been started.")  # idempotency
        initial = {
            "brief": brief.model_dump(mode="json"),
            "brand": brand,
            "events": [],
            "revision_history": [],
        }
        config = self._config(thread_id, {"brand_id": brand["id"], "campaign": brief.campaign_name})
        await self._drive(initial, config, on_update)
        return await self.view(thread_id)

    async def resume(
        self, thread_id: str, decision: ConceptDecision, on_update: OnUpdate | None = None
    ) -> RunView:
        """Continue a run paused at concept approval with the client's decision."""
        current = await self.view(thread_id)
        if current.status != "awaiting_concept_approval" or not current.pending_approval:
            raise ConflictError(f"Run is not awaiting approval (status: {current.status}).")
        valid = {c["concept_id"] for c in current.pending_approval["concepts"]}
        if decision.action == "approve" and decision.concept_id not in valid:
            raise BadRequestError(f"Unknown concept_id. Choose one of: {', '.join(sorted(valid))}.")
        await self._drive(Command(resume=decision.model_dump()), self._config(thread_id), on_update)
        return await self.view(thread_id)

    async def retry(self, thread_id: str, on_update: OnUpdate | None = None) -> RunView:
        """Re-run from the last checkpoint after a failure (e.g. LLM outage)."""
        await self._drive(None, self._config(thread_id), on_update)
        return await self.view(thread_id)
