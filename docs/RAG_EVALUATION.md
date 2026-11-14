# RAG Retrieval Evaluation

How we choose retrieval settings: measure them, don't guess.

## Method

- **Dataset:** [`backend/evals/retrieval/`](../backend/evals/retrieval/) — 7 fictional MANO
  brand documents (guidelines, visual identity, legal, products, personas, past campaigns,
  strategy) and 18 labelled questions. Each question lists phrases that identify the
  passage that answers it; a chunk is *relevant* if it contains one of them.
- Questions deliberately mix **exact-keyword** lookups (`MNO-330-LM`, hex codes) with
  **paraphrased** ones ("Can we say MANO helps students study better?" where the document
  says "must not imply that MANO improves exam performance").
- **Metrics** (`app/rag/evaluation.py`): hit@1, hit@5, recall@5, MRR, nDCG@5.
- **Run it:** `python -m scripts.eval_retrieval [--chunk-sizes 800 200] [--reranker MODEL] [--verbose]`
  (from `backend/`, Qdrant running). It indexes into a throwaway collection.

## Results (2026-11-15, local models, CPU)

Chunk size 800 / overlap 120 (7 chunks):

| Configuration | hit@1 | hit@5 | recall@5 | MRR | nDCG@5 | ms/query |
|---|---:|---:|---:|---:|---:|---:|
| dense only (jina-v2-small) | 0.83 | 1.00 | 1.00 | 0.92 | 0.94 | ~17 |
| sparse only (BM25) | 0.89 | 1.00 | 0.97 | 0.94 | 0.94 | ~16 |
| **hybrid (RRF)** | **0.89–0.94** | 1.00 | 0.97 | 0.94–0.97 | 0.94–0.96 | **~17** |
| hybrid + rerank (MiniLM-L-12) | 0.89 | 1.00 | 1.00 | 0.94 | 0.96 | ~600 |

Chunk size 200 / overlap 40 (13 chunks): hybrid 0.83–0.89 hit@1; dense only drops to 0.72.

Rerankers compared (hybrid → rerank, hit@1 at 800 / 200 tokens, added latency):

| Reranker | hit@1 (800) | hit@1 (200) | added latency |
|---|---:|---:|---:|
| Xenova/ms-marco-MiniLM-L-12-v2 | 0.89 | 0.89 | ~0.6 s |
| BAAI/bge-reranker-base | 0.83 | 0.83 | ~1.7–2.7 s |
| jinaai/jina-reranker-v1-turbo-en | 0.78 | 0.72 | ~0.4 s |
| jinaai/jina-reranker-v1-tiny-en | 0.72 | 0.78 | ~0.3 s |

## Decisions

1. **Hybrid search is the default.** It matches or beats either signal alone: BM25 rescues
   exact identifiers, dense rescues paraphrases, and RRF fuses them at no extra latency.
2. **800-token chunks are kept.** Smaller chunks lowered hit@1 for every configuration on
   this corpus (each passage loses surrounding context).
3. **Reranking is off by default** (`RAG_RERANK_ENABLED=false`). No cross-encoder improved
   ranking here, and all add 0.3–2.7 s per query. MiniLM-L-12 is the configured model if
   enabled; it reads only the first 512 tokens of each chunk.

## Caveats

- 18 questions is small: one question = 0.056 of hit@1. Treat differences under ~0.1 as
  noise. Re-run with real client documents and more questions before production.
- Qdrant breaks exact RRF score ties non-deterministically, so hybrid hit@1 varies by one
  question between runs (0.89 ↔ 0.94).
- Query rewriting (Gemini) is evaluated automatically once `GOOGLE_API_KEY` is set.
