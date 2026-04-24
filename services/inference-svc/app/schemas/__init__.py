"""Inference request/response schemas (Design Area 33 — Output Contract)."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    model: str | None = Field(default=None, description="Override the tenant default model")
    strategy: str = Field(default="hybrid")


class Citation(BaseModel):
    chunk_id: UUID
    document_id: UUID
    page_number: int
    snippet: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    model: str
    prompt_version: str
    tokens_prompt: int
    tokens_completion: int
    confidence: float = Field(ge=0.0, le=1.0)
    correlation_id: str = ""
    debug: dict[str, Any] | None = None
