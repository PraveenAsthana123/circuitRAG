"""
Reciprocal Rank Fusion (RRF) reranker.

RRF combines ranked lists from multiple search backends without needing a
dedicated cross-encoder model. Each candidate gets a score based on its rank
in each list:

    score(d) = sum over lists L of 1 / (k + rank_L(d))

where ``k`` is a smoothing constant (60 is the paper's default and works
well across domains).

Why RRF over a learned reranker?
--------------------------------
* Zero model to host — ~1ms per query.
* No training data needed — parameter-free.
* Robust: performs within a few % of learned rerankers in most domains.

For higher-stakes retrieval, we'd chain RRF → cross-encoder. That's a
simple pipeline (rerank the RRF top-N with a heavier model) and drops
in here.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

log = logging.getLogger(__name__)


class ReciprocalRankFusion:
    def __init__(self, *, k: int = 60) -> None:
        self._k = k

    def fuse(
        self,
        *ranked_lists: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Combine multiple ranked lists into one. ``chunk_id`` is the join key."""
        scores: dict[str, float] = defaultdict(float)
        first_seen: dict[str, dict[str, Any]] = {}

        for ranked in ranked_lists:
            for rank, hit in enumerate(ranked):
                cid = str(hit.get("chunk_id") or "")
                if not cid:
                    continue
                scores[cid] += 1.0 / (self._k + rank + 1)
                # Keep the first entry we saw; it'll have the original source tag.
                if cid not in first_seen:
                    first_seen[cid] = hit.copy()

        # Attach fused score and sort
        fused = []
        for cid, score in scores.items():
            hit = first_seen[cid]
            hit["score"] = score
            hit["source"] = "hybrid"
            fused.append(hit)
        fused.sort(key=lambda h: h["score"], reverse=True)

        log.info(
            "rrf_fused inputs=%d candidates=%d returned=%d",
            len(ranked_lists), len(fused), min(top_k, len(fused)),
        )
        return fused[:top_k]
