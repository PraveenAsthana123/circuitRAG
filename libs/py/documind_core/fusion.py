"""
Hybrid retrieval fusion — RRF + heap-based top-K (§16.5 of the
RAG playbook).

Why RRF (Reciprocal Rank Fusion):
- Vector retrieval and BM25 (and graph) return scores on different
  scales — a vector cosine of 0.78 isn't comparable to a BM25
  score of 11.3.
- Score normalization (min-max, z-score) is fragile across queries
  because the score distribution shifts.
- RRF uses RANK ONLY (not score), making it robust to scale
  differences. Each result's contribution is 1 / (k + rank) where
  k is a smoothing constant (default 60 from the canonical paper
  Cormack et al. 2009).

Companion `top_k` is the standard min-heap idiom for keeping the
K best items out of N — O(n log k) instead of O(n log n) for a
full sort. At N=1M and K=10 that's 7× less work.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Generic, TypeVar

__all__ = ["RankedItem", "reciprocal_rank_fusion", "top_k"]


T = TypeVar("T")


@dataclass(frozen=True)
class RankedItem(Generic[T]):
    """Item + its fused score. Frozen so it's safe as a cache key."""

    item: T
    score: float


def reciprocal_rank_fusion(
    rankings: Iterable[Iterable[T]],
    *,
    k: int = 60,
    weights: Iterable[float] | None = None,
) -> list[RankedItem[T]]:
    """Fuse multiple ranked lists into one.

    Each input list is treated as ranked best-first (rank 0 = best).
    The same item may appear in multiple lists; its scores from each
    are summed. Items appearing in NO list get score 0 — i.e. they
    don't appear in the output.

    Args:
        rankings: list-of-lists of items. Order within each inner
            list is the rank.
        k: smoothing constant (default 60 per Cormack et al.). A
            larger k de-emphasizes the difference between rank 0
            and rank 10; smaller k makes top-rank dominate.
        weights: optional per-list weight (e.g. trust vector
            retrieval more than BM25). If provided, must have the
            same length as `rankings`. Default: all 1.0.

    Returns:
        Items sorted by fused score, descending.

    Edge cases:
        - Empty input → empty output (no items, no score).
        - One empty list among several is fine — contributes nothing.
        - The SAME item via Python identity is treated as the same
          (uses dict lookup; items must be hashable).
    """
    rankings_list = [list(r) for r in rankings]
    if not rankings_list:
        return []

    if weights is None:
        weights_list = [1.0] * len(rankings_list)
    else:
        weights_list = list(weights)
        if len(weights_list) != len(rankings_list):
            raise ValueError(f"weights length ({len(weights_list)}) must match rankings length ({len(rankings_list)})")

    # Use a dict to accumulate scores by item; preserves insertion
    # order so we can break score ties deterministically by first-
    # appearance order (operators expect stable ordering).
    accumulator: dict[T, float] = {}
    for ranking, weight in zip(rankings_list, weights_list, strict=True):
        for rank, item in enumerate(ranking):
            score = weight / (k + rank)
            accumulator[item] = accumulator.get(item, 0.0) + score

    # Sort by score desc; items with equal score keep insertion order.
    # Python's sort is stable, so this works without an explicit tiebreak.
    ordered = sorted(accumulator.items(), key=lambda kv: -kv[1])
    return [RankedItem(item=item, score=score) for item, score in ordered]


def top_k(
    items: Iterable[T],
    k: int,
    *,
    score_fn: Callable[[T], float],
) -> list[T]:
    """Return the K items with the highest scores, in score-desc order.

    Uses a min-heap of size K — O(n log k) instead of O(n log n).

    Args:
        items: iterable of items to score.
        k: how many to keep. Must be >= 1.
        score_fn: callable returning the score for one item.

    Returns:
        Up to K items, sorted by score descending. If fewer than K
        items are provided, returns all of them sorted.

    Edge cases:
        - k <= 0 raises ValueError (silently returning [] would
          mask a config bug).
        - Empty items returns [].
        - score_fn is called exactly once per item.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")

    # heapq is a MIN-heap, so we push (score, idx, item). The min
    # element is the worst of our current top-K; we evict it when
    # a better item comes in. idx is a tiebreaker so heapq never
    # tries to compare two items directly (they may not implement
    # __lt__).
    heap: list[tuple[float, int, T]] = []
    for idx, item in enumerate(items):
        score = score_fn(item)
        if len(heap) < k:
            heapq.heappush(heap, (score, idx, item))
        elif score > heap[0][0]:
            # Better than our current worst — evict and replace.
            heapq.heapreplace(heap, (score, idx, item))

    # The heap holds the top-K but ordered worst-first; produce the
    # caller's expected best-first list.
    return [item for score, _idx, item in sorted(heap, key=lambda x: -x[0])]
