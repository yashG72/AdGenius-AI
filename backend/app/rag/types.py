"""Internal data types passed between RAG steps."""

import uuid
from dataclasses import dataclass, field, replace
from typing import Literal

SearchMode = Literal["hybrid", "dense", "sparse"]


@dataclass(frozen=True)
class RetrievalScope:
    """WHERE a search may look. Built server-side from verified membership - never from
    raw client input - so it is the single guarantee of tenant isolation."""

    organization_id: uuid.UUID
    brand_id: uuid.UUID | None = None
    document_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievedChunk:
    point_id: str
    document_id: uuid.UUID
    original_filename: str
    document_type: str
    source_page: int | None
    chunk_index: int
    text: str
    fusion_score: float  # RRF score from hybrid search (rank-based, not comparable across queries)
    rerank_score: float | None = None  # cross-encoder relevance (higher = more relevant)

    def with_rerank_score(self, score: float) -> "RetrievedChunk":
        return replace(self, rerank_score=score)


@dataclass(frozen=True)
class Source:
    """A chunk placed in the LLM context, numbered for citation as [number]."""

    number: int
    chunk: RetrievedChunk


@dataclass
class SearchResult:
    queries: list[str]
    chunks: list[RetrievedChunk]
    timings_ms: dict[str, float] = field(default_factory=dict)


@dataclass
class AnswerResult:
    answer: str
    found: bool
    citations: list[Source]
    queries: list[str]
    timings_ms: dict[str, float] = field(default_factory=dict)
