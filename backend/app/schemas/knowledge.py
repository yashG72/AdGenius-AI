"""Knowledge-base search / question-answering API schemas."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models import DocumentType
from app.rag.types import RetrievedChunk, Source

QueryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class SearchRequest(BaseModel):
    query: QueryText
    top_k: int | None = Field(default=None, ge=1, le=20)
    document_types: list[DocumentType] = Field(default_factory=list)
    rewrite: bool = Field(default=True, description="Expand the query with an LLM (if set up).")
    rerank: bool = Field(default=True, description="Rerank candidates with a cross-encoder.")
    mode: Literal["hybrid", "dense", "sparse"] = "hybrid"


class AskRequest(BaseModel):
    question: QueryText
    document_types: list[DocumentType] = Field(default_factory=list)


class ChunkHit(BaseModel):
    document_id: uuid.UUID
    original_filename: str
    document_type: str
    source_page: int | None
    chunk_index: int
    text: str
    fusion_score: float
    rerank_score: float | None

    @classmethod
    def build(cls, chunk: RetrievedChunk) -> "ChunkHit":
        return cls(
            document_id=chunk.document_id,
            original_filename=chunk.original_filename,
            document_type=chunk.document_type,
            source_page=chunk.source_page,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            fusion_score=chunk.fusion_score,
            rerank_score=chunk.rerank_score,
        )


class SearchResponse(BaseModel):
    queries: list[str] = Field(description="Queries actually searched (original + rewrites).")
    results: list[ChunkHit]
    timings_ms: dict[str, float]


class Citation(BaseModel):
    source: int = Field(description="The [n] number used in the answer text.")
    document_id: uuid.UUID
    original_filename: str
    source_page: int | None
    chunk_index: int
    excerpt: str

    @classmethod
    def build(cls, source: Source) -> "Citation":
        chunk = source.chunk
        excerpt = chunk.text if len(chunk.text) <= 300 else chunk.text[:297] + "..."
        return cls(
            source=source.number,
            document_id=chunk.document_id,
            original_filename=chunk.original_filename,
            source_page=chunk.source_page,
            chunk_index=chunk.chunk_index,
            excerpt=excerpt,
        )


class AskResponse(BaseModel):
    answer: str
    found: bool
    citations: list[Citation]
    queries: list[str]
    timings_ms: dict[str, float]
