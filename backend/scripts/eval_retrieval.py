"""Retrieval evaluation: compare search configurations on a labelled dataset.

Run from backend/ (Qdrant must be running; uses the real embedding/reranker models):

    python -m scripts.eval_retrieval                      # chunk sizes 800 and 200
    python -m scripts.eval_retrieval --chunk-sizes 800 400 --verbose

Dataset: evals/retrieval/corpus/*.txt (documents) and evals/retrieval/cases.json
(queries, each with phrases that identify the passage that answers it). A chunk is
"relevant" to a query if it contains one of its phrases.

Each run indexes the corpus into a throwaway Qdrant collection (deleted afterwards),
so it never touches real brand data.
"""

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.ingestion.chunking import chunk_pages
from app.ingestion.embeddings import get_embedder
from app.ingestion.extractors import PageText
from app.ingestion.vector_store import ChunkMetadata, VectorStore, create_qdrant_client, point_id
from app.llm.client import get_llm
from app.rag.evaluation import evaluate, hit_at_k
from app.rag.query_rewriter import plan_queries
from app.rag.reranker import FastEmbedReranker
from app.rag.retriever import HybridRetriever
from app.rag.types import RetrievalScope, SearchMode

EVAL_DIR = Path(__file__).resolve().parents[1] / "evals" / "retrieval"
_NS = uuid.UUID("0f6c9a52-3d1e-4c8a-9b7f-2a4e6d8c1b3e")
K = 5


@dataclass(frozen=True)
class Config:
    name: str
    mode: SearchMode
    rerank: bool = False
    rewrite: bool = False


CONFIGS = [
    Config("dense only", "dense"),
    Config("sparse (BM25) only", "sparse"),
    Config("hybrid (RRF)", "hybrid"),
    Config("hybrid + rerank", "hybrid", rerank=True),
    Config("hybrid + rewrite", "hybrid", rewrite=True),
    Config("hybrid + rewrite + rerank", "hybrid", rerank=True, rewrite=True),
]


async def build_index(store: VectorStore, embedder, chunk_size: int, overlap: int):
    # Fixed IDs => identical point IDs every run => RRF ties break the same way (reproducible).
    scope = RetrievalScope(
        organization_id=uuid.uuid5(_NS, "org"), brand_id=uuid.uuid5(_NS, "brand")
    )
    await store.ensure_collection(embedder.dense_dim)
    texts: dict[str, str] = {}
    for path in sorted((EVAL_DIR / "corpus").glob("*.txt")):
        document_id = uuid.uuid5(_NS, path.name)
        chunks = chunk_pages(
            [PageText(None, path.read_text(encoding="utf-8"))], chunk_size, overlap
        )
        embeddings = embedder.embed_documents([c.text for c in chunks])
        meta = ChunkMetadata(scope.organization_id, scope.brand_id, document_id, "other", path.name)
        await store.upsert_chunks(meta, chunks, embeddings)
        texts.update({point_id(document_id, c.index): c.text for c in chunks})
    return scope, texts


async def run(chunk_sizes: list[int], verbose: bool, reranker_model: str | None) -> None:
    settings = get_settings()
    cases = json.loads((EVAL_DIR / "cases.json").read_text(encoding="utf-8"))
    embedder = get_embedder()
    reranker_model = reranker_model or settings.reranker_model
    print(f"reranker: {reranker_model}")
    reranker = FastEmbedReranker(reranker_model, str(settings.embedding_cache_dir))
    llm = get_llm()
    configs = [c for c in CONFIGS if not c.rewrite or llm is not None]
    if llm is None:
        print("(GOOGLE_API_KEY not set: skipping the query-rewrite configuration)")

    client = create_qdrant_client(settings)
    for chunk_size in chunk_sizes:
        overlap = min(settings.chunk_overlap_tokens, chunk_size // 5)
        collection = f"eval_{uuid.uuid4().hex[:8]}"
        store = VectorStore(client, collection)
        try:
            scope, texts = await build_index(store, embedder, chunk_size, overlap)
            retriever = HybridRetriever(client, collection, embedder)
            print(
                f"\n=== chunk size {chunk_size} tokens, overlap {overlap} "
                f"-> {len(texts)} chunks, {len(cases)} queries ==="
            )
            print(
                f"{'configuration':28} {'hit@1':>6} {'hit@5':>6} {'rec@5':>6} "
                f"{'MRR':>6} {'nDCG@5':>7} {'ms/q':>7}"
            )

            for config in configs:
                pairs, misses, elapsed = [], [], 0.0
                for case in cases:
                    phrases = [p.lower() for p in case["relevant"]]
                    relevant = {
                        pid for pid, t in texts.items() if any(p in t.lower() for p in phrases)
                    }
                    if not relevant:
                        print(f"  ! no chunk contains the phrases for: {case['query']}")
                        continue
                    started = time.perf_counter()
                    queries = await plan_queries(
                        llm if config.rewrite else None,
                        case["query"],
                        settings.rag_max_query_variants,
                    )
                    chunks = await retriever.retrieve(
                        scope,
                        queries,
                        limit=settings.rag_rerank_candidates,
                        per_search=settings.rag_candidates_per_search,
                        mode=config.mode,
                    )
                    if config.rerank and chunks:
                        scores = reranker.score(case["query"], [c.text for c in chunks])
                        chunks = [
                            c
                            for _, c in sorted(
                                zip(scores, chunks, strict=True),
                                key=lambda pair: pair[0],
                                reverse=True,
                            )
                        ]
                    elapsed += time.perf_counter() - started
                    ranked = [c.point_id for c in chunks]
                    pairs.append((ranked, relevant))
                    if not hit_at_k(ranked, relevant, 1):
                        misses.append(case["query"])

                at_k = evaluate(pairs, k=K)
                at_1 = evaluate(pairs, k=1)
                print(
                    f"{config.name:28} {at_1.hit:6.2f} {at_k.hit:6.2f} {at_k.recall:6.2f} "
                    f"{at_k.mrr:6.2f} {at_k.ndcg:7.2f} {elapsed / len(pairs) * 1000:7.0f}"
                )
                if verbose and misses:
                    for query in misses:
                        print(f"    not ranked #1: {query}")
        finally:
            await client.delete_collection(collection)
    await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--chunk-sizes", type=int, nargs="+", default=[800, 200])
    parser.add_argument("--verbose", action="store_true", help="list queries not ranked #1")
    parser.add_argument(
        "--reranker", help="cross-encoder model to evaluate (default: RERANKER_MODEL)"
    )
    args = parser.parse_args()
    asyncio.run(run(args.chunk_sizes, args.verbose, args.reranker))


if __name__ == "__main__":
    main()
