"""Retrieval evaluation metrics.

Each test case has a query and the set of chunks that are RELEVANT to it. Given the
ranked list a configuration returned, we measure:

- hit@k      did at least one relevant chunk appear in the top k?        (1 or 0)
- recall@k   what fraction of all relevant chunks appeared in the top k?
- MRR        1 / rank of the first relevant chunk (1.0 = always ranked first)
- nDCG@k     rewards relevant chunks ranked higher (1.0 = perfect ordering)

Averaging these over a dataset turns "does retrieval feel good?" into numbers that can
be compared across settings (chunk size, hybrid vs dense, reranking on/off, ...).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass


def hit_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    return 1.0 if any(item in relevant for item in ranked[:k]) else 0.0


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float:
    for position, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / position
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    dcg = sum(
        1.0 / math.log2(position + 1)
        for position, item in enumerate(ranked[:k], start=1)
        if item in relevant
    )
    ideal = sum(1.0 / math.log2(position + 1) for position in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


@dataclass(frozen=True)
class Scores:
    hit: float
    recall: float
    mrr: float
    ndcg: float


def evaluate(results: Sequence[tuple[Sequence[str], set[str]]], k: int) -> Scores:
    """Average metrics over (ranked_ids, relevant_ids) pairs."""
    n = len(results) or 1
    return Scores(
        hit=sum(hit_at_k(r, rel, k) for r, rel in results) / n,
        recall=sum(recall_at_k(r, rel, k) for r, rel in results) / n,
        mrr=sum(reciprocal_rank(r, rel) for r, rel in results) / n,
        ndcg=sum(ndcg_at_k(r, rel, k) for r, rel in results) / n,
    )
