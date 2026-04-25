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


# ---------------------------------------------------------------------------
# Prompt registry visibility — surfaces governance.prompts active rows
# to the operator UI. Closes the trust-scorecard gap "prompt/model/
# retrieval registry visibility" — operators need to know which prompt
# version + model + tuning is live RIGHT NOW, not just "what's in code."
# ---------------------------------------------------------------------------
class PromptInfo(BaseModel):
    """A single active prompt row — the operator-facing projection
    of governance.prompts. Template body is NOT exposed: the
    dashboard polls every 5s and dumping ~1KB of template per row
    per refresh is wasteful, and full-template inspection belongs
    on the governance UI, not the operator dashboard."""

    name: str
    version: str
    model: str | None = Field(
        default=None,
        description="Model targeted by this prompt (e.g. 'llama3.1:8b')",
    )
    temperature: float | None = None
    max_tokens: int | None = None
    status: str = Field(description="lifecycle state — 'active' here")


class HealthPromptsResponse(BaseModel):
    """Active prompt registry as seen by the operator dashboard.
    Returns 200 even when the DB is unreachable; ``db_reachable=false``
    + empty ``prompts`` lets the UI render '(registry unavailable)'
    rather than mystifying the operator with a 500."""

    service: str = "inference-svc"
    observed_at: str = Field(description="ISO 8601 timestamp at sample time")
    db_reachable: bool = Field(
        description=(
            "True when governance.prompts was successfully queried. "
            "False on connection failure, missing table, or DbClient "
            "not configured (governance-svc unwired)."
        ),
    )
    prompts: list[PromptInfo] = Field(
        default_factory=list,
        description="Rows where status='active', sorted by (name, version desc)",
    )


# ---------------------------------------------------------------------------
# Trace link — given a correlation_id, project the linked audit rows +
# draft rows so an operator can reconstruct one request end-to-end
# without code archaeology. Closes:
#   * mcp-agent-gap-review.md §2.3 (trace → draft → audit linkage)
#   * production-trust-quality-and-readiness.md §2 ("Can I trace one
#     request end-to-end?")
#   * tech-lead-audit-checklist.md §7 ("no easy way to follow
#     trace → draft → replay → audit")
# ---------------------------------------------------------------------------
class TraceLinkAuditRow(BaseModel):
    """Operator-facing projection of governance.audit_log."""

    id: str = Field(description="Audit row UUID")
    timestamp: str = Field(description="ISO 8601, when the audit row landed")
    tenant_id: str | None
    actor_id: str | None
    actor_type: str
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    fail_closed_failed: bool = Field(
        default=False,
        description=(
            "True when audit details.fail_closed_failed was set — i.e. "
            "the audit-write failure was tolerated under fail_closed=False. "
            "Surfaced because the audit row IS the canonical record; "
            "operators investigating a fail_closed event need to see it."
        ),
    )


class TraceLinkDraftRow(BaseModel):
    """Operator-facing projection of governance.action_drafts."""

    draft_id: str
    tenant_id: str | None
    tool: str
    status: str
    reason: str
    created_at: str
    replayed_at: str | None = None


class TraceLinkResponse(BaseModel):
    """All governance state we hold for a single correlation_id —
    audit rows + draft rows. The Jaeger trace URL is a hint, not a
    fetched payload (the trace lives in Jaeger, not our DB)."""

    correlation_id: str
    observed_at: str = Field(description="ISO 8601 timestamp at sample time")
    db_reachable: bool
    audit_rows: list[TraceLinkAuditRow] = Field(default_factory=list)
    draft_rows: list[TraceLinkDraftRow] = Field(default_factory=list)
    jaeger_url: str | None = Field(
        default=None,
        description=(
            "When DOCUMIND_JAEGER_URL is set, a deep-link to the trace "
            "in Jaeger. Operators jump from this dashboard to the full "
            "trace tree; the dashboard doesn't try to render spans itself."
        ),
    )


# ---------------------------------------------------------------------------
# Upstream health — cross-service reachability view from inference-svc's
# perspective. Closes the gap "no single cross-service view" surfaced in
# the gRPC/microservices reference docs and the audit checklist §2.
# Honest scoping: inference-svc only polls what IT depends on (retrieval,
# ollama, registered MCP namespaces, governance DB). Other services own
# their own equivalents.
# ---------------------------------------------------------------------------
class UpstreamHealthRow(BaseModel):
    """One row per upstream dependency. ``reachable=True`` means the
    probe succeeded; ``latency_ms`` is the wall-clock for that probe.
    On failure ``error`` carries a short string the operator can act
    on without reading code."""

    name: str = Field(
        description=(
            "Stable identifier — 'retrieval-svc', 'ollama', "
            "'mcp_hr', 'mcp_itsm', 'governance-db', etc."
        ),
    )
    kind: str = Field(
        description=(
            "Dependency kind — 'http_service', 'mcp', 'llm', 'db', "
            "'kafka'. Operators alert on different kinds differently."
        ),
    )
    url: str = Field(
        description=(
            "URL or endpoint hint. For 'db' kind the host:port string."
        ),
    )
    reachable: bool
    latency_ms: float | None = Field(
        default=None,
        description="Probe latency in ms. None when probe never started.",
    )
    status: str | None = Field(
        default=None,
        description="HTTP status code or 'connected' for db/llm probes.",
    )
    version: str | None = Field(
        default=None,
        description="Service version string when the /health response carried one.",
    )
    error: str | None = Field(
        default=None,
        description=(
            "Short error label when reachable=False. e.g. 'timeout', "
            "'connect_refused', 'http_500'. Stack traces stay in logs."
        ),
    )


class HealthUpstreamsResponse(BaseModel):
    """Inference-svc's view of its own upstreams — health probes
    done in parallel with a tight timeout so the dashboard stays
    responsive even when one upstream is wedged."""

    service: str = "inference-svc"
    observed_at: str = Field(description="ISO 8601 timestamp at sample time")
    upstreams: list[UpstreamHealthRow] = Field(default_factory=list)
