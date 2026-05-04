"""Retrieval request/response schemas (Design Area 34 — Retrieval Schema)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=100)
    filters: dict[str, Any] = Field(default_factory=dict)
    strategy: str = Field(default="hybrid", description="vector | graph | hybrid")
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
