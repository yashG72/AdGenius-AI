"""Hybrid retrieval in Qdrant.

For every query variant we run two searches - dense (meaning) and sparse/BM25 (exact
keywords) - and Qdrant fuses ALL result lists server-side with Reciprocal Rank Fusion:

    score(chunk) = sum over lists of 1 / (60 + rank_in_list)

RRF uses ranks, not raw scores, so dense cosine similarities and BM25 scores (which live
on completely different scales) can be combined fairly. One network round trip total.

Tenant isolation: the scope filter is applied inside every individual search AND to the
fused result. There is no code path that searches without an organization filter.
"""

import asyncio
import uuid

from qdrant_client import AsyncQdrantClient, models

from app.ingestion.embeddings import Embedder
from app.ingestion.vector_store import DENSE_VECTOR, SPARSE_VECTOR
from app.rag.types import RetrievalScope, RetrievedChunk, SearchMode


def scope_filter(scope: RetrievalScope) -> models.Filter:
    must: list[models.Condition] = [
        models.FieldCondition(
            key="organization_id", match=models.MatchValue(value=str(scope.organization_id))
        )
    ]
    if scope.brand_id is not None:
        must.append(
            models.FieldCondition(
                key="brand_id", match=models.MatchValue(value=str(scope.brand_id))
            )
        )
    if scope.document_types:
        must.append(
            models.FieldCondition(
                key="document_type", match=models.MatchAny(any=list(scope.document_types))
            )
        )
    return models.Filter(must=must)


class HybridRetriever:
    def __init__(self, client: AsyncQdrantClient, collection: str, embedder: Embedder) -> None:
        self.client = client
        self.collection = collection
        self.embedder = embedder

    async def retrieve(
        self,
        scope: RetrievalScope,
        queries: list[str],
        *,
        limit: int,
        per_search: int,
        mode: SearchMode = "hybrid",
    ) -> list[RetrievedChunk]:
        if not queries or not await self.client.collection_exists(self.collection):
            return []

        flt = scope_filter(scope)
        embeddings = await asyncio.gather(
            *(asyncio.to_thread(self.embedder.embed_query, q) for q in queries)
        )
        prefetch: list[models.Prefetch] = []
        for emb in embeddings:
            if mode in ("hybrid", "dense"):
                prefetch.append(
                    models.Prefetch(
                        query=emb.dense, using=DENSE_VECTOR, limit=per_search, filter=flt
                    )
                )
            # A query made only of stopwords has no BM25 terms, so skip its sparse search.
            if mode in ("hybrid", "sparse") and emb.sparse.indices:
                prefetch.append(
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=emb.sparse.indices, values=emb.sparse.values
                        ),
                        using=SPARSE_VECTOR,
                        limit=per_search,
                        filter=flt,
                    )
                )
        if not prefetch:
            return []

        response = await self.client.query_points(
            self.collection,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=flt,  # belt and braces
            limit=limit,
            with_payload=True,
        )
        return [_to_chunk(point) for point in response.points]


def _to_chunk(point: models.ScoredPoint) -> RetrievedChunk:
    payload = point.payload or {}
    return RetrievedChunk(
        point_id=str(point.id),
        document_id=uuid.UUID(payload["document_id"]),
        original_filename=payload.get("original_filename", ""),
        document_type=payload.get("document_type", "other"),
        source_page=payload.get("source_page"),
        chunk_index=payload.get("chunk_index", 0),
        text=payload.get("text", ""),
        fusion_score=point.score,
    )
