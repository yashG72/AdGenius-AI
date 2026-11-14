"""Embedding models (local, free, CPU) via FastEmbed.

Each chunk gets TWO vectors:
- dense  (jina-embeddings-v2-small-en, 512 floats): captures *meaning*, so
  "affordable" matches "budget-friendly".
- sparse (BM25): captures exact *keywords*, so product names / SKUs match precisely.
Phase 5 combines both ("hybrid search").

Models download once (~120 MB) into EMBEDDING_CACHE_DIR, then load from disk.
"""

import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]


@dataclass(frozen=True)
class Embeddings:
    dense: list[list[float]]
    sparse: list[SparseVector]


@dataclass(frozen=True)
class QueryEmbedding:
    dense: list[float]
    sparse: SparseVector


class Embedder(Protocol):
    @property
    def dense_dim(self) -> int: ...
    def embed_documents(self, texts: list[str]) -> Embeddings: ...
    def embed_query(self, text: str) -> QueryEmbedding: ...


class FastEmbedEmbedder:
    def __init__(self, dense_model: str, sparse_model: str, cache_dir: str, batch_size: int):
        # Imported lazily: loading ONNX runtime is slow and the API process doesn't need it.
        from fastembed import SparseTextEmbedding, TextEmbedding

        self._dense = TextEmbedding(dense_model, cache_dir=cache_dir)
        self._sparse = SparseTextEmbedding(sparse_model, cache_dir=cache_dir)
        self._batch_size = batch_size
        self._dim = len(next(iter(self._dense.embed(["dimension probe"]))))
        self._lock = threading.Lock()  # ONNX sessions are shared; serialize calls

    @property
    def dense_dim(self) -> int:
        return self._dim

    def embed_documents(self, texts: list[str]) -> Embeddings:
        with self._lock:
            dense = [v.tolist() for v in self._dense.embed(texts, batch_size=self._batch_size)]
            sparse = [
                SparseVector(indices=s.indices.tolist(), values=s.values.tolist())
                for s in self._sparse.embed(texts, batch_size=self._batch_size)
            ]
        return Embeddings(dense=dense, sparse=sparse)

    def embed_query(self, text: str) -> QueryEmbedding:
        # query_embed differs from embed for BM25: a query is a bag of terms, not a
        # document, so term-frequency/length normalisation is not applied.
        with self._lock:
            dense = next(iter(self._dense.query_embed(text))).tolist()
            sparse = next(iter(self._sparse.query_embed(text)))
        return QueryEmbedding(
            dense=dense,
            sparse=SparseVector(indices=sparse.indices.tolist(), values=sparse.values.tolist()),
        )


@lru_cache
def get_embedder() -> Embedder:
    """One embedder per process (models are loaded once, then reused)."""
    settings = get_settings()
    return FastEmbedEmbedder(
        dense_model=settings.dense_embedding_model,
        sparse_model=settings.sparse_embedding_model,
        cache_dir=str(settings.embedding_cache_dir),
        batch_size=settings.embedding_batch_size,
    )
