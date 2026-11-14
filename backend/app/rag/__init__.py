"""Retrieval-Augmented Generation engine.

query -> rewrite (LLM) -> embed -> hybrid search (dense + BM25, fused with RRF in Qdrant)
      -> live-document check (DB) -> rerank (cross-encoder) -> context assembly
      -> grounded generation (LLM) -> validated citations
"""
