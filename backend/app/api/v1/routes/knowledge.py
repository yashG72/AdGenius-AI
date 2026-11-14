"""Brand knowledge-base search and question answering.

The retrieval scope (organization + brand) is derived from the brand the caller is
verified to have access to - the client can never choose which organization to search.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUserDep, DbSessionDep, SettingsDep
from app.ingestion.embeddings import get_embedder
from app.ingestion.vector_store import get_qdrant_client
from app.llm.client import get_llm
from app.rag.reranker import get_reranker
from app.rag.retriever import HybridRetriever
from app.rag.service import RagService, scope_for_brand
from app.schemas.knowledge import (
    AskRequest,
    AskResponse,
    ChunkHit,
    Citation,
    SearchRequest,
    SearchResponse,
)
from app.services import brand_service

router = APIRouter(prefix="/brands/{brand_id}/knowledge", tags=["knowledge"])


def get_rag_service(session: DbSessionDep, settings: SettingsDep) -> RagService:
    return RagService(
        session=session,
        retriever=HybridRetriever(get_qdrant_client(), settings.qdrant_collection, get_embedder()),
        reranker=get_reranker(),
        llm=get_llm(),
        settings=settings,
    )


RagDep = Annotated[RagService, Depends(get_rag_service)]


@router.post("/search", response_model=SearchResponse, summary="Hybrid search over brand documents")
async def search(
    brand_id: uuid.UUID,
    data: SearchRequest,
    user: CurrentUserDep,
    session: DbSessionDep,
    rag: RagDep,
) -> SearchResponse:
    brand, _ = await brand_service.get_brand_for_user(session, brand_id, user.id)
    scope = scope_for_brand(brand.organization_id, brand.id, [t.value for t in data.document_types])
    result = await rag.search(
        scope,
        data.query,
        top_k=data.top_k,
        rewrite=data.rewrite,
        rerank=data.rerank,
        mode=data.mode,
    )
    return SearchResponse(
        queries=result.queries,
        results=[ChunkHit.build(c) for c in result.chunks],
        timings_ms=result.timings_ms,
    )


@router.post("/ask", response_model=AskResponse, summary="Answer a question with citations")
async def ask(
    brand_id: uuid.UUID,
    data: AskRequest,
    user: CurrentUserDep,
    session: DbSessionDep,
    rag: RagDep,
) -> AskResponse:
    brand, _ = await brand_service.get_brand_for_user(session, brand_id, user.id)
    scope = scope_for_brand(brand.organization_id, brand.id, [t.value for t in data.document_types])
    result = await rag.answer(scope, data.question)
    return AskResponse(
        answer=result.answer,
        found=result.found,
        citations=[Citation.build(s) for s in result.citations],
        queries=result.queries,
        timings_ms=result.timings_ms,
    )
