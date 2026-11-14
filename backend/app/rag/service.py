"""RagService: the one entry point for retrieval and grounded answers.

Used by the knowledge API now and by the Brand Research Agent in phase 7.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.llm.client import LLMNotConfiguredError, StructuredLLM
from app.models import BrandDocument, DocumentStatus
from app.rag.context import select_sources
from app.rag.generator import generate_answer
from app.rag.query_rewriter import plan_queries
from app.rag.reranker import Reranker
from app.rag.retriever import HybridRetriever
from app.rag.types import AnswerResult, RetrievalScope, RetrievedChunk, SearchMode, SearchResult

logger = logging.getLogger(__name__)

NOT_FOUND_ANSWER = "I couldn't find this in the brand's documents."


@contextmanager
def _timed(timings: dict[str, float], name: str) -> Iterator[None]:
    started = time.perf_counter()
    yield
    timings[name] = round((time.perf_counter() - started) * 1000, 1)


class RagService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        retriever: HybridRetriever,
        reranker: Reranker | None,
        llm: StructuredLLM | None,
        settings: Settings,
    ) -> None:
        self.session = session
        self.retriever = retriever
        self.reranker = reranker
        self.llm = llm
        self.settings = settings

    async def _only_live_documents(
        self, scope: RetrievalScope, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """Drop chunks whose document was deleted but whose vectors aren't cleaned up yet.

        Deletion is asynchronous (the worker removes vectors later), so for a short window
        a deleted document's chunks still exist in Qdrant. The database is the source of
        truth: only chunks of currently INDEXED documents in this organization pass.
        """
        if not chunks:
            return chunks
        live = set(
            await self.session.scalars(
                select(BrandDocument.id).where(
                    BrandDocument.id.in_({c.document_id for c in chunks}),
                    BrandDocument.organization_id == scope.organization_id,
                    BrandDocument.status == DocumentStatus.INDEXED,
                )
            )
        )
        return [c for c in chunks if c.document_id in live]

    async def search(
        self,
        scope: RetrievalScope,
        query: str,
        *,
        top_k: int | None = None,
        rewrite: bool = True,
        rerank: bool = True,
        mode: SearchMode = "hybrid",
    ) -> SearchResult:
        s = self.settings
        timings: dict[str, float] = {}

        with _timed(timings, "rewrite"):
            use_rewrite = rewrite and s.rag_query_rewrite_enabled
            queries = await plan_queries(
                self.llm if use_rewrite else None, query, s.rag_max_query_variants
            )
        with _timed(timings, "retrieve"):
            candidates = await self.retriever.retrieve(
                scope,
                queries,
                limit=s.rag_rerank_candidates,
                per_search=s.rag_candidates_per_search,
                mode=mode,
            )
            candidates = await self._only_live_documents(scope, candidates)
        if rerank and self.reranker is not None and candidates:
            with _timed(timings, "rerank"):
                # Rerank against the ORIGINAL question: it is what the user actually asked.
                scores = await asyncio.to_thread(
                    self.reranker.score, query, [c.text for c in candidates]
                )
                candidates = sorted(
                    (c.with_rerank_score(sc) for c, sc in zip(candidates, scores, strict=True)),
                    key=lambda c: c.rerank_score,
                    reverse=True,
                )
        return SearchResult(
            queries=queries, chunks=candidates[: top_k or s.rag_top_k], timings_ms=timings
        )

    async def answer(self, scope: RetrievalScope, question: str) -> AnswerResult:
        if self.llm is None:
            raise LLMNotConfiguredError()
        s = self.settings
        result = await self.search(scope, question, top_k=s.rag_rerank_candidates)
        sources = select_sources(
            result.chunks, max_chunks=s.rag_context_chunks, token_budget=s.rag_context_token_budget
        )
        if not sources:  # nothing relevant: don't spend an LLM call or invite guessing
            return AnswerResult(NOT_FOUND_ANSWER, False, [], result.queries, result.timings_ms)

        timings = dict(result.timings_ms)
        with _timed(timings, "generate"):
            generated, cited = await generate_answer(self.llm, question, sources)
        return AnswerResult(
            answer=generated.answer,
            found=generated.found,
            citations=cited,
            queries=result.queries,
            timings_ms=timings,
        )


def scope_for_brand(
    organization_id: uuid.UUID, brand_id: uuid.UUID, document_types: list[str] | None = None
) -> RetrievalScope:
    return RetrievalScope(
        organization_id=organization_id,
        brand_id=brand_id,
        document_types=tuple(document_types or ()),
    )
