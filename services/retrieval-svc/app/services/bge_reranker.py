"""BGE cross-encoder reranker — Stage-1 adapter (per CLAUDE.md §56).

Stage-1 contract: ship an opt-in adapter that's lazy-imported and feature-
flag-gated. NOT wired into the request path until Stage-2 lands a drill
proving it improves precision on the empirical RAG-test queries that
slipped past min_score (per docs/architecture/rag-deep-test-2026-05-04.md).

Why BGE on top of RRF: RRF is an unsupervised rank-fusion. It can elevate
chunks that share keywords with the query but aren't semantically the
answer. A cross-encoder rerank stage scores (query, chunk) pairs jointly
and re-orders the RRF top-N. Empirical evidence in BGE paper: 5-15%
NDCG@10 improvement over RRF-alone on MTEB.

Operator opt-in:
    BGE_RERANKER_ENABLED=1
    BGE_RERANKER_MODEL=BAAI/bge-reranker-v2-m3   # default

Composes with:
    services/retrieval-svc/app/services/reranker.py — RRF (Stage-0)
    docs/architecture/compression-tools-audit-2026-05-04.md — table row #15
    docs/architecture/rag-deep-test-2026-05-04.md — empirical gap
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

BGE_RERANKER_ENABLED = os.getenv("BGE_RERANKER_ENABLED", "").strip() == "1"
BGE_RERANKER_MODEL = os.getenv("BGE_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")


class BGERerankerDisabled(RuntimeError):
    """Raised when rerank is called but BGE_RERANKER_ENABLED is not set."""


def is_available() -> bool:
    """Return True only when the operator has opted in via env flag.

    Default-deny: §56 6-gate pattern requires Stage-1 adapters to be
    feature-flag-gated. Operator MUST set BGE_RERANKER_ENABLED=1
    AND have FlagEmbedding installed for is_available() to return True.
    """
    if not BGE_RERANKER_ENABLED:
        return False
    try:
        import FlagEmbedding  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def status() -> dict[str, Any]:
    """Return operator-readable status surface."""
    return {
        "stage": 1,
        "enabled_env": BGE_RERANKER_ENABLED,
        "model": BGE_RERANKER_MODEL,
        "available": is_available(),
        "wiring_status": (
            "stage-1 adapter; optional hot-path use is mediated by "
            "bge_reranker_protected + HybridRetriever flags"
        ),
        "next_stage": (
            "Tune/evaluate through the protected hot path; do not call "
            "this adapter directly from retrieval requests"
        ),
    }


def rerank(
    query: str,
    chunks: list[dict[str, Any]],
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """Re-rank chunks by BGE cross-encoder relevance to query.

    Args:
        query: the user query string
        chunks: list of dicts with at least a 'text' key (or 'content')
        top_k: if set, return only the top-k after reranking; default = all

    Returns:
        chunks list re-ordered by BGE relevance score (highest first).
        Each chunk dict gets a 'bge_score' key added.

    Raises:
        BGERerankerDisabled: if BGE_RERANKER_ENABLED is not set or
            FlagEmbedding is not installed. Caller should fall back to
            the input chunk order.
    """
    if not is_available():
        raise BGERerankerDisabled(
            "BGE rerank disabled. Set BGE_RERANKER_ENABLED=1 and "
            "ensure FlagEmbedding is installed."
        )

    # Lazy import — keeps cold-start fast for callers who don't use this
    from FlagEmbedding import FlagReranker  # noqa: PLC0415

    # Cache the model per process; loading is ~3s on cold start
    if not hasattr(rerank, "_model"):
        log.info("loading BGE reranker model=%s", BGE_RERANKER_MODEL)
        rerank._model = FlagReranker(BGE_RERANKER_MODEL, use_fp16=True)  # type: ignore[attr-defined]

    if not chunks:
        return []

    pairs = [(query, c.get("text") or c.get("content") or "") for c in chunks]
    scores = rerank._model.compute_score(pairs)  # type: ignore[attr-defined]

    # Attach scores + sort high-to-low
    enriched = [{**c, "bge_score": float(s)} for c, s in zip(chunks, scores, strict=True)]
    enriched.sort(key=lambda c: c["bge_score"], reverse=True)

    if top_k is not None:
        enriched = enriched[:top_k]

    log.info(
        "bge_rerank reranked=%d top_score=%.3f",
        len(enriched),
        enriched[0]["bge_score"] if enriched else 0.0,
    )
    return enriched
