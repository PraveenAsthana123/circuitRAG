"""
Tests for documind_core.fusion — RRF + heap top-K.

Covers:
- Empty input → empty output
- Single ranking returns identical order
- Two rankings with overlap: items in both rank higher than
  items in only one (the whole RRF point)
- k smoothing parameter behavior (large k flattens, small k
  emphasizes top rank)
- Per-list weights honored
- Mismatched weights raises ValueError (catches config bug
  rather than silently weighting some lists)
- top_k: heap maintains correct top-K, evictions work, K=1, K>n
- top_k: NEGATIVE k <= 0 raises (no silent empty-list)
- top_k: tiebreak is stable (same-score items keep input order)
"""

from __future__ import annotations

import pytest

from documind_core.fusion import RankedItem, reciprocal_rank_fusion, top_k


class TestRRFBasics:
    def test_empty_input(self) -> None:
        assert reciprocal_rank_fusion([]) == []

    def test_single_ranking_preserves_order(self) -> None:
        result = reciprocal_rank_fusion([["a", "b", "c"]])
        assert [r.item for r in result] == ["a", "b", "c"]
        # Scores strictly decreasing.
        assert all(result[i].score > result[i + 1].score for i in range(len(result) - 1))

    def test_overlap_boosts_score(self) -> None:
        # The whole RRF value-add: items in BOTH lists rank higher
        # than items in only one.
        result = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])
        items = [r.item for r in result]
        # `b` is in both → highest score
        assert items[0] == "b"

    def test_empty_list_among_others_is_no_op(self) -> None:
        result = reciprocal_rank_fusion([["a", "b"], []])
        assert [r.item for r in result] == ["a", "b"]


class TestRRFSmoothing:
    def test_large_k_flattens(self) -> None:
        # With k=1000, score = 1/(1000+rank) — top-rank advantage
        # is small. With k=1, top rank = 1/2, second = 1/3.
        flat = reciprocal_rank_fusion([list(range(10))], k=1000)
        sharp = reciprocal_rank_fusion([list(range(10))], k=1)
        # Score gap between rank-0 and rank-1 is much bigger with k=1.
        flat_gap = flat[0].score - flat[1].score
        sharp_gap = sharp[0].score - sharp[1].score
        assert sharp_gap > flat_gap


class TestRRFWeights:
    def test_weight_amplifies_list(self) -> None:
        # Heavy weight on first list → its rank-0 should beat the
        # other list's rank-0 even though both are tied otherwise.
        result = reciprocal_rank_fusion(
            [["a"], ["b"]],
            weights=[10.0, 1.0],
        )
        assert result[0].item == "a"

    def test_mismatched_weights_raises(self) -> None:
        # NEGATIVE: silently truncating/padding weights would mask
        # a config bug.
        with pytest.raises(ValueError, match="weights length"):
            reciprocal_rank_fusion(
                [["a"], ["b"]],
                weights=[1.0],
            )

    def test_zero_weight_excludes_list(self) -> None:
        # Weight 0 = item gets 0 score from this list. If the only
        # source is a zero-weighted list, the item still appears
        # (with score 0) — implementation choice; document it.
        result = reciprocal_rank_fusion([["only-here"]], weights=[0.0])
        assert result[0].score == 0.0


class TestTopK:
    def test_basic(self) -> None:
        items = [(1, "a"), (5, "b"), (3, "c"), (2, "d")]
        out = top_k(items, k=2, score_fn=lambda x: x[0])
        # Top-2 by score = (5, "b"), (3, "c").
        assert [x[1] for x in out] == ["b", "c"]

    def test_k_larger_than_n_returns_all(self) -> None:
        items = [(1, "a"), (2, "b")]
        out = top_k(items, k=10, score_fn=lambda x: x[0])
        assert len(out) == 2

    def test_empty_input(self) -> None:
        assert top_k([], k=5, score_fn=lambda _: 1.0) == []

    def test_k_one(self) -> None:
        items = [3, 1, 4, 1, 5, 9, 2, 6]
        out = top_k(items, k=1, score_fn=float)
        assert out == [9]

    def test_k_zero_raises(self) -> None:
        # NEGATIVE: k=0 silently returning [] would mask a config
        # bug (e.g. "limit" param defaulted to 0 from env).
        with pytest.raises(ValueError, match="k must be"):
            top_k([1, 2, 3], k=0, score_fn=float)

    def test_k_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="k must be"):
            top_k([1, 2, 3], k=-1, score_fn=float)

    def test_score_fn_called_once_per_item(self) -> None:
        # Performance contract: the most expensive part is usually
        # score_fn. It MUST NOT be invoked twice per item.
        calls = []

        def score(x: int) -> float:
            calls.append(x)
            return float(x)

        top_k(range(100), k=10, score_fn=score)
        assert len(calls) == 100
        assert sorted(calls) == list(range(100))

    def test_tied_scores_dont_compare_items(self) -> None:
        # Items may not implement __lt__ (e.g. dicts). The heap MUST
        # break ties on idx, never fall through to the item.
        # Without the idx tiebreaker, this would raise TypeError.
        items = [{"x": 1}, {"x": 2}, {"x": 1}]
        out = top_k(items, k=2, score_fn=lambda d: d["x"])
        # Best is x=2; second is one of the x=1's (which one is
        # idx-stable).
        assert out[0] == {"x": 2}
        assert out[1] == {"x": 1}


class TestRankedItem:
    def test_frozen(self) -> None:
        r = RankedItem(item="x", score=1.0)
        with pytest.raises((AttributeError, Exception)):
            r.score = 2.0  # type: ignore[misc]
