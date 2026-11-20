"""Embedding models (local, free, CPU) via FastEmbed.

Each chunk gets TWO vectors:
- dense  (jina-embeddings-v2-small-en, 512 floats): captures *meaning*, so
  "affordable" matches "budget-friendly".
- sparse (BM25): captures exact *keywords*, so product names / SKUs match precisely.
Phase 5 combines both ("hybrid search").

Models download once (~120 MB) into EMBEDDING_CACHE_DIR, then load from disk.

EMBEDDING_PROVIDER=gemini swaps the local dense model for the Gemini embedding API
(for small hosting plans); BM25 stays local either way.
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


class GeminiEmbedder:
    """Dense vectors from the Gemini embedding API; sparse BM25 still computed locally.

    Used on small hosts (e.g. a 512 MB free server) where loading a neural embedding
    model into memory isn't possible. BM25 needs no neural model - just a tokenizer and
    stemmer - so it stays local and free.

    Gemini distinguishes documents from queries (`task_type`), which improves retrieval.
    Free-tier rate limits are low, so 429 / transient errors are retried with backoff.
    """

    _MAX_BATCH = 100  # texts per embed_content request (API limit)

    def __init__(
        self,
        api_key: str,
        model: str,
        dim: int,
        sparse_model: str,
        cache_dir: str,
        batch_size: int,
        max_attempts: int = 4,
    ) -> None:
        from fastembed import SparseTextEmbedding
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._dim = dim
        self._sparse = SparseTextEmbedding(sparse_model, cache_dir=cache_dir)
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._lock = threading.Lock()

    @property
    def dense_dim(self) -> int:
        return self._dim

    def _dense(self, texts: list[str], task_type: str) -> list[list[float]]:
        import time

        from google.genai import errors, types

        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self._dim)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._MAX_BATCH):
            batch = texts[start : start + self._MAX_BATCH]
            for attempt in range(1, self._max_attempts + 1):
                try:
                    response = self._client.models.embed_content(
                        model=self._model, contents=batch, config=config
                    )
                    break
                except errors.APIError as exc:
                    retryable = exc.code in (429, 500, 502, 503, 504)
                    if not retryable or attempt == self._max_attempts:
                        raise
                    time.sleep(2**attempt)  # 2, 4, 8 s - free tier allows ~100 requests/min
            vectors.extend(list(e.values) for e in response.embeddings)
        return vectors

    def embed_documents(self, texts: list[str]) -> Embeddings:
        dense = self._dense(texts, "RETRIEVAL_DOCUMENT")
        with self._lock:
            sparse = [
                SparseVector(indices=s.indices.tolist(), values=s.values.tolist())
                for s in self._sparse.embed(texts, batch_size=self._batch_size)
            ]
        return Embeddings(dense=dense, sparse=sparse)

    def embed_query(self, text: str) -> QueryEmbedding:
        dense = self._dense([text], "RETRIEVAL_QUERY")[0]
        with self._lock:
            sparse = next(iter(self._sparse.query_embed(text)))
        return QueryEmbedding(
            dense=dense,
            sparse=SparseVector(indices=sparse.indices.tolist(), values=sparse.values.tolist()),
        )


@lru_cache
def get_embedder() -> Embedder:
    """One embedder per process (models are loaded once, then reused)."""
    settings = get_settings()
    if settings.embedding_provider == "gemini":
        if settings.google_api_key is None:
            raise RuntimeError("EMBEDDING_PROVIDER=gemini requires GOOGLE_API_KEY.")
        return GeminiEmbedder(
            api_key=settings.google_api_key.get_secret_value(),
            model=settings.gemini_embedding_model,
            dim=settings.gemini_embedding_dim,
            sparse_model=settings.sparse_embedding_model,
            cache_dir=str(settings.embedding_cache_dir),
            batch_size=settings.embedding_batch_size,
        )
    return FastEmbedEmbedder(
        dense_model=settings.dense_embedding_model,
        sparse_model=settings.sparse_embedding_model,
        cache_dir=str(settings.embedding_cache_dir),
        batch_size=settings.embedding_batch_size,
    )
