"""Retrieval metric unit tests (hand-computed expected values)."""

import math

import pytest

from app.rag.evaluation import evaluate, hit_at_k, ndcg_at_k, recall_at_k, reciprocal_rank

RANKED = ["a", "b", "c", "d"]


def test_hit_and_recall() -> None:
    assert hit_at_k(RANKED, {"c"}, k=2) == 0.0
    assert hit_at_k(RANKED, {"c"}, k=3) == 1.0
    assert recall_at_k(RANKED, {"b", "d", "z"}, k=4) == pytest.approx(2 / 3)


def test_reciprocal_rank() -> None:
    assert reciprocal_rank(RANKED, {"c", "d"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(RANKED, {"z"}) == 0.0


def test_ndcg() -> None:
    assert ndcg_at_k(RANKED, {"a"}, k=4) == 1.0  # perfect: only relevant item ranked first
    expected = (1 / math.log2(3)) / 1.0  # relevant item at rank 2, ideal at rank 1
    assert ndcg_at_k(RANKED, {"b"}, k=4) == pytest.approx(expected)


def test_evaluate_averages() -> None:
    scores = evaluate([(RANKED, {"a"}), (RANKED, {"z"})], k=3)

    assert scores.hit == 0.5 and scores.mrr == 0.5
