"""Everything the agents need from the outside world, injected when the graph is built.

Agents never import services directly; they get them from `AgentDeps`. Tests pass
fakes; the worker passes real Gemini / RAG / Tavily services.
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.config import Settings
from app.llm.client import StructuredLLM
from app.rag.types import RetrievalScope, SearchResult
from app.research.competitor import BrandResearchContext, CompetitorReport


class AgentOutputError(Exception):
    """The model returned structurally valid but unusable output (retryable)."""


class BrandKnowledge(Protocol):
    """The slice of RagService the Brand Research Agent uses."""

    async def search(
        self,
        scope: RetrievalScope,
        query: str,
        *,
        top_k: int | None = None,
        rewrite: bool = True,
        rerank: bool = True,
        mode: str = "hybrid",
    ) -> SearchResult: ...


class CompetitorResearcher(Protocol):
    async def research(
        self, ctx: BrandResearchContext, *, max_queries: int | None = None
    ) -> CompetitorReport: ...


@dataclass
class AgentDeps:
    llm: StructuredLLM
    settings: Settings
    knowledge: BrandKnowledge | None = None  # None => no document knowledge base
    competitor_researcher: CompetitorResearcher | None = None  # None => web research off


NodeFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def traced(agent: str) -> Callable[[NodeFn], NodeFn]:
    """Wrap a node so every run appends an AgentEvent (the execution trace).

    A node may put "_status" / "_summary" in its update to describe what happened.
    Failures are re-raised so LangGraph's retry policy (and then the run) handle them.
    """

    def decorate(fn: NodeFn) -> NodeFn:
        async def node(state: dict[str, Any]) -> dict[str, Any]:
            started_at = datetime.now(UTC).isoformat()
            started = time.perf_counter()
            update = await fn(state)
            event = {
                "agent": agent,
                "status": update.pop("_status", "completed"),
                "started_at": started_at,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "summary": update.pop("_summary", ""),
            }
            update["events"] = [event]
            return update

        node.__name__ = fn.__name__
        return node

    return decorate
