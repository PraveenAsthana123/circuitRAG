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
