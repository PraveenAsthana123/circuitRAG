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


class DraftRejectRequest(BaseModel):
    """Operator-supplied rationale for rejecting a pending draft."""

    reason: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "Free-form reason. Required — an unexplained rejection is an "
            "audit gap, not a feature."
        ),
    )


class DraftRejectResponse(BaseModel):
    """Outcome of a draft rejection. Terminal — no replay attempt was made."""

    draft_id: str
    ok: bool
    status: str | None = Field(
        default=None, description="'rejected' on success",
    )
    reason: str | None = Field(
        default=None, description="Echoed back for client correlation",
    )
    error: dict[str, Any] | None = None


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


# ---------------------------------------------------------------------------
# Per-tool stats — surfaces the MCP /metrics primitives (calls, latency,
# scope denials) as a structured response so the operator dashboard can
# render a "per-tool monitoring" panel without scraping Prometheus itself.
# Closes Phase-1 #2 from docs/architecture/mcp-agent-gap-review.md.
# ---------------------------------------------------------------------------
class ToolLatencyStats(BaseModel):
    """Histogram aggregate. None when no calls observed yet."""

    count: int = 0
    sum_seconds: float = 0.0
    avg_seconds: float | None = Field(
        default=None,
        description=(
            "sum / count, or None when count==0 — caller renders '—'. "
            "p95 not exposed: deriving p95 from prom-client buckets is "
            "lossy. Real p95 alerts go through Prometheus directly."
        ),
    )


class ToolStats(BaseModel):
    """Per-tool aggregate. One row per (namespace, tool) seen on the
    MCP /metrics endpoint."""

    namespace: str = Field(description="MCP namespace, e.g. 'mcp_hr'")
    tool: str = Field(description="Tool name, e.g. 'hr.leave_request'")
    calls: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "outcome → count. outcome ∈ {ok, error, replay, "
            "in_progress, conflict, http_<status>, ...}"
        ),
    )
    latency: ToolLatencyStats = Field(default_factory=ToolLatencyStats)
    denials: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "reason → count. reason ∈ {NOT_AUTHENTICATED, INVALID_TOKEN, "
            "INSUFFICIENT_SCOPE, UNKNOWN}."
        ),
    )


class HealthToolsResponse(BaseModel):
    """Per-tool aggregation of MCP /metrics across every registered
    namespace. Returns 200 when at least one MCP server was reachable;
    namespaces that failed scrape are listed in ``unreachable`` so the
    UI can surface them as stale rather than missing."""

    service: str = "inference-svc"
    observed_at: str = Field(description="ISO 8601 timestamp at sample time")
    tools: list[ToolStats] = Field(
        default_factory=list,
        description="One entry per (namespace, tool) seen across MCP /metrics",
    )
    unreachable: list[str] = Field(
        default_factory=list,
        description=(
            "Namespaces whose /metrics scrape failed — operator sees "
            "'(stale)' rather than thinking the tools were never called."
        ),
    )
