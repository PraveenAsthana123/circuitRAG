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
        description=(
            "answer | action | action_declined | action_denied_scope | "
            "action_unavailable"
        ),
    )


# ---------------------------------------------------------------------------
# HITL admin API — list + resolve persisted MCP drafts
# ---------------------------------------------------------------------------
class DraftSummary(BaseModel):
    """One row from ``governance.action_drafts`` (pending or recent)."""

    draft_id: str = Field(description='Human-visible token, e.g. "DRAFT-AB12CD34EF"')
    tool: str
    arguments: dict[str, Any]
    tenant_id: str | None = None
    correlation_id: str | None = None
    reason: str = Field(description='Why the original call degraded: "cb_open" | "ConnectError" | "http_5xx"')
    status: str = Field(description="pending | replayed | rejected")
    created_at: float = Field(description="Unix epoch seconds")
    replayed_at: float | None = None
    replay_result: dict[str, Any] | None = None


class DraftListResponse(BaseModel):
    drafts: list[DraftSummary]
    tenant_id: str | None = None
    status_filter: str


class DraftResolveResponse(BaseModel):
    """Outcome of a replay attempt. Mirrors :class:`AgentAction`."""

    draft_id: str
    ok: bool
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    degraded: bool = Field(default=False, description="True if MCP is still down and the replay persisted a NEW draft")
    new_draft_id: str | None = Field(default=None, description="Populated if the replay itself degraded")
    idempotent_replay: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Detailed health — exposes internal breaker + readiness state to operators
# ---------------------------------------------------------------------------
class BreakerState(BaseModel):
    """A single circuit breaker's external state."""

    name: str = Field(description="Stable identifier, e.g. 'mcp_hr'")
    state: str = Field(description="closed | open | half_open")
    failures: int | None = Field(
        default=None,
        description="Current failure counter (None if the breaker doesn't expose it)",
    )
    # Exposed so observers (drills, dashboards) can compute "when can
    # this breaker re-probe?" without baking the timeout into client
    # code. None when the breaker doesn't expose it (legacy paths).
    recovery_timeout_s: float | None = Field(
        default=None,
        description="Seconds the breaker waits in OPEN before allowing a probe.",
    )


class HealthDetailedResponse(BaseModel):
    """
    Operator-facing health report. Returns 200 when the service is
    reachable; fields expose degradation (e.g. mcp_hr=open) without
    changing the HTTP status. Callers decide what to alert on.
    """

    service: str
    uptime_s: float
    observed_at: str = Field(description="ISO 8601 timestamp at sample time")
    breakers: list[BreakerState] = Field(default_factory=list)
    readiness: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Lifecycle-bound flags: draft_store, audit_log, auth, "
            "agent_service — each 'on' | 'off' | a backend name."
        ),
    )
