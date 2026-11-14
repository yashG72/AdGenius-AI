"""Cross-encoder reranking (local, free).

Embedding search compares a query vector with chunk vectors computed *separately*.
A cross-encoder instead reads the query and the chunk *together* and outputs a relevance
score - much more accurate, but too slow to run over a whole collection. So we use it
only on the ~20 candidates from hybrid search ("retrieve wide, rerank narrow").
"""

import threading
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings


class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class FastEmbedReranker:
    def __init__(self, model: str, cache_dir: str) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._model = TextCrossEncoder(model, cache_dir=cache_dir)
        self._lock = threading.Lock()

    def score(self, query: str, texts: list[str]) -> list[float]:
        with self._lock:
            return [float(s) for s in self._model.rerank(query, texts, batch_size=8)]


@lru_cache
def get_reranker() -> Reranker | None:
    settings = get_settings()
    if not settings.rag_rerank_enabled:
        return None
    return FastEmbedReranker(settings.reranker_model, str(settings.embedding_cache_dir))
