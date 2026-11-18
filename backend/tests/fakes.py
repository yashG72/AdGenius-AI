"""Deterministic stand-ins for ML models and the LLM, so tests are fast and offline."""

import hashlib
import re
from collections.abc import Callable

from pydantic import BaseModel

from app.ingestion.embeddings import Embeddings, QueryEmbedding, SparseVector

_WORD = re.compile(r"[a-z0-9#]+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _sparse(text: str) -> SparseVector:
    """Bag-of-words sparse vector: one dimension per (hashed) word, like a tiny BM25."""
    ids = sorted({int(hashlib.md5(w.encode()).hexdigest(), 16) % 100_000 for w in _words(text)})
    return SparseVector(indices=ids, values=[1.0] * len(ids))


class FakeEmbedder:
    """Dense vectors are hash noise (meaningless on purpose); sparse vectors are real
    word overlap - so keyword search works and tests can reason about rankings."""

    dense_dim = 8

    def _dense(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [b / 255 + 0.01 for b in digest[: self.dense_dim]]

    def embed_documents(self, texts: list[str]) -> Embeddings:
        return Embeddings(dense=[self._dense(t) for t in texts], sparse=[_sparse(t) for t in texts])

    def embed_query(self, text: str) -> QueryEmbedding:
        return QueryEmbedding(dense=self._dense(text), sparse=_sparse(text))


class FakeReranker:
    """Scores by the fraction of query words present in the text."""

    def score(self, query: str, texts: list[str]) -> list[float]:
        q = set(_words(query))
        return [len(q & set(_words(t))) / (len(q) or 1) for t in texts]


class FakeSearchProvider:
    """Returns scripted raw results per query (default: one generic result); records calls.
    A scripted Exception is raised instead (to simulate provider failures)."""

    name = "fake"

    def __init__(self, scripted: dict[str, object] | None = None) -> None:
        self.scripted = scripted or {}
        self.calls: list[str] = []
        self.options: dict[str, object] = {}  # query -> SearchOptions it was called with

    async def search(self, query: str, options) -> list[dict]:
        self.calls.append(query)
        self.options[query] = options
        response = self.scripted.get(query)
        if isinstance(response, Exception):
            raise response
        if response is None:
            slug = "-".join(query.lower().split())
            response = [
                {
                    "url": f"https://example.com/{slug}",
                    "title": query.title(),
                    "content": f"Article about {query}.",
                    "score": 0.5,
                }
            ]
        return response


class FakeLLM:
    """Returns scripted responses per schema. A response may be a model instance, a
    callable(system, user) -> instance, or an Exception to raise."""

    def __init__(self, responses: dict[type[BaseModel], object]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, str]] = []

    async def generate(self, schema, *, system: str, user: str):
        self.calls.append((schema.__name__, system, user))
        response = self.responses[schema]
        if isinstance(response, Exception):
            raise response
        if isinstance(response, Callable):
            response = response(system, user)
        # A real LLM returns a NEW object per call. Agents may adjust the object they get
        # (e.g. drop invalid citations), so never hand out a shared instance.
        return response.model_copy(deep=True) if isinstance(response, BaseModel) else response
