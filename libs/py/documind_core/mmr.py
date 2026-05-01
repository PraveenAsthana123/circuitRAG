"""
MMR — Maximal Marginal Relevance (§16.6 post-retrieval diversification).

Why MMR:
- Top-K by relevance alone often returns N near-duplicate chunks
  ("policy" returns 5 paraphrases of the same paragraph).
- The LLM generation step gets less unique evidence, more wasted
  context window, and the user sees less diverse coverage.
- MMR balances **relevance** vs **novelty**: at each step pick the
  candidate that maximizes
      lambda * sim(query, candidate) - (1-lambda) * max sim(candidate, already_selected)

DSA (§16.6 of the playbook): greedy + similarity matrix. O(K * N)
which is fine for typical K=10, N=100. For larger N, switch to
Cluster-MMR or DPP.

Lambda interpretation:
- lambda=1.0 → pure relevance (degenerates to top-K).
- lambda=0.5 → balanced (typical default in literature).
- lambda=0.0 → pure diversity (ignore relevance).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

__all__ = ["mmr"]


T = TypeVar("T")


def mmr(
    query_similarity: Sequence[float],
    pairwise_similarity: Sequence[Sequence[float]],
    *,
    k: int,
    lambda_: float = 0.5,
) -> list[int]:
    """Return indices of the top-K most-relevant-but-diverse items.

    Args:
        query_similarity: sim(query, item_i) for each item — higher
            means more relevant.
        pairwise_similarity: pairwise_similarity[i][j] = sim(i, j).
            Must be square; the diagonal is ignored. Symmetric is
            recommended (callers using cosine satisfy this).
        k: number to return. If k >= len(items), MMR still gives
            a sensible diverse ordering of all items.
        lambda_: relevance vs diversity weight in [0.0, 1.0].

    Returns:
        Indices in selection order — earlier = chosen first.

    Raises:
        ValueError on k < 1, malformed pairwise matrix, or
        lambda_ outside [0, 1].
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    if not 0.0 <= lambda_ <= 1.0:
        raise ValueError(f"lambda_ must be in [0, 1], got {lambda_}")

    n = len(query_similarity)
    if n == 0:
        return []
    if len(pairwise_similarity) != n:
        raise ValueError(f"pairwise_similarity rows ({len(pairwise_similarity)}) must equal n ({n})")
    for i, row in enumerate(pairwise_similarity):
        if len(row) != n:
            raise ValueError(f"pairwise_similarity row {i} has length {len(row)}, expected {n}")

    selected: list[int] = []
    remaining = set(range(n))

    # First pick: pure top-relevance (no "already selected" yet).
    first = max(remaining, key=lambda i: query_similarity[i])
    selected.append(first)
    remaining.remove(first)

    while len(selected) < min(k, n):
        # For each candidate, compute MMR score:
        #   lambda * relevance - (1-lambda) * max_sim_to_selected
        best_idx = -1
        best_score = float("-inf")
        for cand in remaining:
            relevance = query_similarity[cand]
            max_sim = max(pairwise_similarity[cand][s] for s in selected)
            score = lambda_ * relevance - (1.0 - lambda_) * max_sim
            if score > best_score:
                best_score = score
                best_idx = cand
        if best_idx == -1:
            break  # defensive — shouldn't happen
        selected.append(best_idx)
        remaining.remove(best_idx)

    return selected
