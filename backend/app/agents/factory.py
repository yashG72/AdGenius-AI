"""Build real agent dependencies (Gemini, RAG, Tavily) for one workflow execution.

Why not reuse the API's cached clients? Each Celery task runs on its own fresh event
loop, and async clients (Redis, Qdrant, Gemini/httpx) are bound to the loop they were
created on - reusing a cached one from an earlier task fails. So every execution builds
its own clients here and closes them afterwards.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.deps import AgentDeps
from app.core.config import Settings
from app.ingestion.embeddings import get_embedder
from app.ingestion.vector_store import create_qdrant_client
from app.llm.client import GeminiLLM, LLMNotConfiguredError
from app.rag.reranker import get_reranker
from app.rag.retriever import HybridRetriever
from app.rag.service import RagService
from app.research.cache import get_search_cache
from app.research.competitor import CompetitorResearchService
from app.research.web_search import TavilySearchProvider, WebSearchService


@asynccontextmanager
async def live_agent_deps(session: AsyncSession, settings: Settings) -> AsyncIterator[AgentDeps]:
    """`session` is used only by the Brand Research agent's document search."""
    if settings.google_api_key is None or not settings.google_api_key.get_secret_value():
        raise LLMNotConfiguredError()
    llm = GeminiLLM(settings)
    qdrant = create_qdrant_client(settings)
    # Own Redis client: a Celery task runs on its own event loop (None = no Redis).
    redis_client = (
        redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=5)
        if settings.redis_url
        else None
    )
    try:
        knowledge = RagService(
            session=session,
            retriever=HybridRetriever(qdrant, settings.qdrant_collection, get_embedder()),
            reranker=get_reranker(),  # sync ONNX model: safe to share across loops
            llm=llm,
            settings=settings,
        )
        competitor = None
        tavily_key = settings.tavily_api_key.get_secret_value() if settings.tavily_api_key else ""
        if tavily_key:
            search = WebSearchService(
                provider=TavilySearchProvider(
                    tavily_key, settings.web_search_depth, settings.web_search_timeout_seconds
                ),
                cache=get_search_cache(redis_client),
                settings=settings,
            )
            competitor = CompetitorResearchService(search=search, llm=llm, settings=settings)
        yield AgentDeps(
            llm=llm, settings=settings, knowledge=knowledge, competitor_researcher=competitor
        )
    finally:
        await qdrant.close()
        if redis_client is not None:
            await redis_client.aclose()
