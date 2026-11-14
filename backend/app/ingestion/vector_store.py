"""Qdrant access for document chunks.

One collection holds every organization's chunks. Isolation comes from the payload:
every point carries organization_id / brand_id / document_id, and EVERY search must
filter on organization_id (phase 5 enforces this in one place). organization_id is
indexed with `is_tenant=True`, which tells Qdrant to physically group each tenant's
data - fast filtered search, no cross-tenant scanning.

Point IDs are deterministic (uuid5 of document_id + chunk index), so re-running an
ingestion overwrites the same points instead of creating duplicates (idempotency).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, models

from app.core.config import Settings, get_settings
from app.ingestion.chunking import Chunk
from app.ingestion.embeddings import Embeddings

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"
_POINT_NAMESPACE = uuid.UUID("6f1c2a4e-8a59-4d1e-9a51-3c0b7e2f5d10")


@dataclass(frozen=True)
class ChunkMetadata:
    organization_id: uuid.UUID
    brand_id: uuid.UUID
    document_id: uuid.UUID
    document_type: str
    original_filename: str


def point_id(document_id: uuid.UUID, chunk_index: int) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{document_id}:{chunk_index}"))


def create_qdrant_client(settings: Settings) -> AsyncQdrantClient:
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    return AsyncQdrantClient(url=settings.qdrant_url, api_key=api_key, timeout=30)


@lru_cache
def get_qdrant_client() -> AsyncQdrantClient:
    """Shared client for the API process (connection reuse); closed on app shutdown."""
    return create_qdrant_client(get_settings())


class VectorStore:
    def __init__(self, client: AsyncQdrantClient, collection: str) -> None:
        self.client = client
        self.collection = collection

    async def ensure_collection(self, dense_dim: int) -> None:
        if await self.client.collection_exists(self.collection):
            return
        await self.client.create_collection(
            self.collection,
            vectors_config={
                DENSE_VECTOR: models.VectorParams(size=dense_dim, distance=models.Distance.COSINE)
            },
            # IDF modifier: Qdrant computes BM25's inverse-document-frequency weighting.
            sparse_vectors_config={
                SPARSE_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
        await self.client.create_payload_index(
            self.collection,
            "organization_id",
            field_schema=models.KeywordIndexParams(
                type=models.KeywordIndexType.KEYWORD, is_tenant=True
            ),
        )
        for field in ("brand_id", "document_id", "document_type"):
            await self.client.create_payload_index(
                self.collection, field, field_schema=models.PayloadSchemaType.KEYWORD
            )

    async def upsert_chunks(
        self, meta: ChunkMetadata, chunks: Sequence[Chunk], embeddings: Embeddings
    ) -> None:
        points = [
            models.PointStruct(
                id=point_id(meta.document_id, chunk.index),
                vector={
                    DENSE_VECTOR: dense,
                    SPARSE_VECTOR: models.SparseVector(
                        indices=sparse.indices, values=sparse.values
                    ),
                },
                payload={
                    "organization_id": str(meta.organization_id),
                    "brand_id": str(meta.brand_id),
                    "document_id": str(meta.document_id),
                    "document_type": meta.document_type,
                    "original_filename": meta.original_filename,
                    "chunk_index": chunk.index,
                    "source_page": chunk.page,
                    "token_count": chunk.token_count,
                    "text": chunk.text,
                },
            )
            for chunk, dense, sparse in zip(
                chunks, embeddings.dense, embeddings.sparse, strict=True
            )
        ]
        for start in range(0, len(points), 128):  # bounded request size
            await self.client.upsert(self.collection, points=points[start : start + 128])

    async def _delete_where(self, field: str, value: uuid.UUID) -> None:
        if not await self.client.collection_exists(self.collection):
            return
        await self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(key=field, match=models.MatchValue(value=str(value)))
                    ]
                )
            ),
        )

    async def delete_document(self, document_id: uuid.UUID) -> None:
        await self._delete_where("document_id", document_id)

    async def delete_brand(self, brand_id: uuid.UUID) -> None:
        await self._delete_where("brand_id", brand_id)

    async def count_for_document(self, document_id: uuid.UUID) -> int:
        if not await self.client.collection_exists(self.collection):
            return 0
        result = await self.client.count(
            self.collection,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=str(document_id))
                    )
                ]
            ),
            exact=True,
        )
        return result.count
