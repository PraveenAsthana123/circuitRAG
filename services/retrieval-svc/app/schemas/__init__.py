"""Retrieval request/response schemas (Design Area 34 — Retrieval Schema)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=100)
    filters: dict[str, Any] = Field(default_factory=dict)
    strategy: str = Field(
        default="hybrid",
        description=(
            "vector | graph | hybrid | vectorless — Stage-1: 'vectorless' "
            "suppresses vector+graph backends and returns the (currently "
            "empty) ElasticSearcher BM25 result set. Stage-2 wires the "
            "actual ES search call once the indexing pipeline lands. Per "
            "/admin/vectorless-elasticsearch and "
            "drill_vectorless_strategy_dispatch.py."
        ),
    )
    include_sources: tuple[str, ...] = Field(default=("vector", "graph"))
    # Per docs/architecture/rag-deep-test-2026-05-04.md — empirical RAG
    # test surfaced that retrieval returns top-K even with zero-match
    # corpus. min_score sets a hard floor below which chunks are
    # rejected. Default 0.0 preserves prior behavior; callers can pass
    # min_score=0.3 (typical hybrid floor) to enforce quality.
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Hard similarity floor. Chunks scoring below this value are "
            "rejected even if they're in the top-K. Use 0.0 to preserve "
            "legacy unfiltered behavior; 0.3 typical for hybrid score; "
            "0.5+ for high-precision applications."
        ),
    )


class RetrievedChunk(BaseModel):
    chunk_id: UUID
    document_id: UUID
    text: str
    score: float = Field(ge=0.0)
    source: str = Field(description="vector | graph | metadata")
    page_number: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrieveResponse(BaseModel):
    chunks: list[RetrievedChunk]
    latency_ms: float
    strategy: str
    cached: bool
    # ``degraded`` is True when at least one requested backend failed
    # (timeout, exception, dependency unreachable). The response still
    # contains whatever the surviving backends returned — but callers
    # downstream of retrieval (the agent path, the RAG answer path)
    # can use this signal to skip caching derived results, lower
    # confidence on the answer, or surface "partial results" in the UI.
    # Default False keeps existing callers compatible — the field is
    # additive and only becomes True when something actually failed.
    degraded: bool = Field(
        default=False,
        description=(
            "True when at least one retrieval backend (vector, graph) "
            "failed and the response is built from the remainder. "
            "False when all requested backends succeeded."
        ),
    )


# ---------------------------------------------------------------------------
# best_config registry visibility — symmetric to inference-svc HealthBestConfig
# Response (commit 01729e0). Operators see what BestConfig the retriever
# would seed defaults from RIGHT NOW. Per §38 governance + §47 fail-safe.
# ---------------------------------------------------------------------------
class BestConfigInfo(BaseModel):
    """Effective BestConfig as seen by the retriever."""

    min_score: float = Field(description="Empirically-best similarity floor")
    top_k: int = Field(description="Empirically-best retrieval top_k")
    rerank_enabled: bool
    rerank_top_k: int = Field(default=10)
    chunking_strategy: str = Field(default="recursive_paragraph_sentence")
    pass_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    promoted_at_ts: float = Field(default=0.0)
    eval_set_size: int = Field(default=0)


class HealthBestConfigResponse(BaseModel):
    """Live BestConfig visibility for retrieval-svc operators.

    enabled+loaded fields distinguish:
      * disabled (no env flag)
      * enabled but file missing/malformed (legacy fallback)
      * enabled and loaded (config block populated)

    Always 200 — visibility never crashes the dashboard.
    """

    service: str = "retrieval-svc"
    observed_at: str
    enabled: bool
    loaded: bool
    config_path: str
    config_exists: bool
    config_size_bytes: int = 0
    ttl_s: float
    cache_age_s: float = 0.0
    fallback_defaults: dict[str, Any] = Field(default_factory=dict)
    config: BestConfigInfo | None = None
    next_stage: str = ""


# ---------------------------------------------------------------------------
# Audit-trail history projection — symmetric to inference-svc's
# HealthBestConfigHistoryResponse (commit 2741a93).
# ---------------------------------------------------------------------------
class HealthBestConfigHistoryResponse(BaseModel):
    """Aggregate view of the .loop/best_config_history.jsonl audit
    trail as seen by retrieval-svc."""

    service: str = "retrieval-svc"
    observed_at: str
    enabled: bool
    history_path: str
    history_exists: bool
    history_size_bytes: int = 0
    window_days: int = 7
    total_attempts: int = 0
    promoted: int = 0
    rejected: int = 0
    skipped: int = 0
    gates_failed_counts: dict[str, int] = Field(default_factory=dict)
    latest_decision: dict[str, Any] | None = None
    earliest_ts: float = 0.0
    latest_ts: float = 0.0
