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


class AgentAction(BaseModel):
    """Result of an agent flow that touched an MCP tool."""
    tool: str = Field(description="Tool name, e.g. hr.leave_request")
    ok: bool = Field(description="True if the tool succeeded")
    result: dict[str, Any] | None = Field(default=None, description="Tool result payload")
    error: dict[str, Any] | None = Field(default=None, description="Error envelope if ok=false")
    degraded: bool = Field(default=False, description="True if CB OPEN → draft persisted")
    draft_id: str | None = Field(default=None, description="Draft ID if degraded")
    idempotent_replay: bool = Field(default=False)


class AgentAskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    model: str | None = Field(default=None)
    strategy: str = Field(default="hybrid")
    # Agent-specific: user context for action binding
    employee_id: str | None = Field(
        default=None,
        description="Required if the query resolves to an HR write action",
    )
    allow_actions: bool = Field(
        default=True,
        description="If false, the agent returns answer-only even when an action matches.",
    )


class AgentAskResponse(AskResponse):
    action: AgentAction | None = Field(
        default=None,
        description="Populated when the agent invoked an MCP tool.",
    )
    intent: str = Field(
        default="answer",
        description="answer | action | action_declined",
    )
