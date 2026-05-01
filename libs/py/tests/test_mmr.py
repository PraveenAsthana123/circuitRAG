"""
Tests for documind_core.mmr — Maximal Marginal Relevance.

Covers:
- Empty input → empty output
- k > n still terminates with all available
- lambda=1.0 == pure top-K by relevance (degenerate to relevance)
- lambda=0.0 == pure diversity (relevance ignored after first pick)
- Mid lambda: similar items get demoted in favor of less-similar
- k=1 returns single most-relevant
- k <= 0 raises
- Bad lambda raises
- Mismatched matrix dimension raises
"""

from __future__ import annotations

import pytest

from documind_core.mmr import mmr


class TestMMRBasics:
    def test_empty_query_similarity(self) -> None:
        assert mmr([], [], k=5) == []

    def test_k_one(self) -> None:
        # 3 items; query similarity strictly increasing → pick last.
        result = mmr(
            query_similarity=[0.1, 0.5, 0.9],
            pairwise_similarity=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            k=1,
        )
        assert result == [2]

    def test_k_larger_than_n(self) -> None:
        # All 3 items returned in some sensible order.
        result = mmr(
            query_similarity=[0.1, 0.5, 0.9],
            pairwise_similarity=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            k=100,
        )
        assert sorted(result) == [0, 1, 2]


class TestMMRLambda:
    def test_lambda_one_pure_relevance(self) -> None:
        # lambda=1 → no diversity penalty → pure top-K by relevance.
        # Items 0 and 1 are duplicates (sim=1), but lambda=1 still
        # picks both since relevance dominates.
        result = mmr(
            query_similarity=[0.9, 0.85, 0.5],
            pairwise_similarity=[[1, 1, 0], [1, 1, 0], [0, 0, 1]],
            k=2,
            lambda_=1.0,
        )
        assert result == [0, 1]

    def test_lambda_balanced_picks_diverse(self) -> None:
        # lambda=0.5: items 0 and 1 are near-duplicates (sim=1.0).
        # Item 2 has lower relevance but high diversity.
        # Expected: pick 0 first (highest relevance), then 2 (more
        # diverse from 0), NOT 1 (which is a duplicate of 0).
        result = mmr(
            query_similarity=[0.9, 0.85, 0.5],
            pairwise_similarity=[[1, 1, 0], [1, 1, 0], [0, 0, 1]],
            k=2,
            lambda_=0.5,
        )
        assert result == [0, 2]

    def test_lambda_zero_pure_diversity(self) -> None:
        # lambda=0 → first pick is still highest-relevance (the
        # special-case at the top of mmr()), but subsequent picks
        # are pure diversity.
        result = mmr(
            query_similarity=[0.9, 0.5, 0.5],
            pairwise_similarity=[[1, 1, 0], [1, 1, 0], [0, 0, 1]],
            k=2,
            lambda_=0.0,
        )
        # First: 0 (highest relevance — base case).
        # Second: pure diversity from 0; item 2 has sim 0 to item 0
        # vs item 1 has sim 1 to item 0 → pick 2.
        assert result == [0, 2]


class TestMMRValidation:
    def test_k_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="k must be"):
            mmr([0.1], [[1.0]], k=0)

    def test_lambda_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="lambda_"):
            mmr([0.1], [[1.0]], k=1, lambda_=-0.1)

    def test_lambda_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="lambda_"):
            mmr([0.1], [[1.0]], k=1, lambda_=1.5)

    def test_pairwise_wrong_outer_size_raises(self) -> None:
        with pytest.raises(ValueError, match="pairwise_similarity rows"):
            mmr([0.1, 0.2], [[1.0, 0.0]], k=1)  # only 1 row, expected 2

    def test_pairwise_wrong_inner_size_raises(self) -> None:
        with pytest.raises(ValueError, match="row 0"):
            mmr([0.1, 0.2], [[1.0], [0.0, 1.0]], k=1)
