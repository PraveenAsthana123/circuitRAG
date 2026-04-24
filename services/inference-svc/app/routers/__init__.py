"""Inference HTTP routes."""
from __future__ import annotations

from documind_core.auth import require_roles, required_role_for_tool
from documind_core.exceptions import ValidationError
from documind_core.schemas import HealthResponse
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.schemas import (
    AgentAskRequest,
    AgentAskResponse,
    AskRequest,
    AskResponse,
    BreakerState,
    DraftListResponse,
    DraftResolveResponse,
    DraftSummary,
    HealthDetailedResponse,
)
from app.services import RagInferenceService
from app.services.agent import AgentService

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="inference-svc")


@router.get(
    "/api/v1/health/detailed",
    response_model=HealthDetailedResponse,
    tags=["health"],
    summary="Operator-facing detail: breaker states + readiness flags",
)
async def health_detailed(request: Request) -> HealthDetailedResponse:
    import time
    from datetime import UTC, datetime

    state = request.app.state
    started_at = getattr(state, "started_at_monotonic", None)
    uptime = (time.monotonic() - started_at) if started_at is not None else 0.0

    breakers: list[BreakerState] = []
    # Every registered MCP namespace gets its own breaker row so the
    # dashboard sees them independently. Stable name scheme:
    # ``mcp_<namespace>`` (mcp_hr, mcp_itsm, ...). Matches the
    # Prometheus exporter's label naming so /detailed and /metrics
    # agree on identifiers.
    mcp_clients = getattr(state, "mcp_clients", None) or {}
    for namespace in sorted(mcp_clients):
        client = mcp_clients[namespace]
        failures = None
        inner = getattr(client, "_breaker", None)
        if inner is not None:
            failures = getattr(inner, "_failures", None)
        breakers.append(
            BreakerState(
                name=f"mcp_{namespace}",
                state=client.cb_state,
                failures=failures,
            ),
        )
    # Observability CB lives inside the OTel exporter wrapper; exposed
    # on app.state when the lifespan hands us the reference (opt-in so
    # services that don't use setup_observability don't explode here).
    ocb = getattr(state, "obs_breaker", None)
    if ocb is not None:
        breakers.append(BreakerState(name=ocb.name, state=ocb.state.value))

    readiness = {
        "draft_store": (
            "postgres" if getattr(state, "db_client", None) is not None else "in_memory"
        ),
        "audit_log": "on" if getattr(state, "db_client", None) is not None else "off",
        "auth": "required" if getattr(state, "auth_required", False) else "optional",
        "agent_service": (
            "on" if getattr(state, "agent_service", None) is not None else "off"
        ),
        "draft_replay_worker": (
            "on" if getattr(state, "draft_replay_worker", None) is not None else "off"
        ),
    }

    return HealthDetailedResponse(
        service="inference-svc",
        uptime_s=round(uptime, 3),
        observed_at=datetime.now(UTC).isoformat(),
        breakers=breakers,
        readiness=readiness,
    )


def _service(request: Request) -> RagInferenceService:
    svc = getattr(request.app.state, "rag_service", None)
    if svc is None:
        raise RuntimeError("rag_service not initialized")
    return svc


@router.post("/api/v1/ask", response_model=AskResponse, tags=["inference"])
async def ask(
    body: AskRequest,
    request: Request,
    debug: bool = Query(False, description="Include debug info in the response"),
    svc: RagInferenceService = Depends(_service),
) -> AskResponse:
    tenant_id = getattr(request.state, "tenant_id", "") or ""
    correlation_id = getattr(request.state, "correlation_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")
    return await svc.ask(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        request=body,
        include_debug=debug,
    )


def _agent_service(request: Request) -> AgentService:
    svc = getattr(request.app.state, "agent_service", None)
    if svc is None:
        raise RuntimeError(
            "agent_service disabled — set DOCUMIND_MCP_HR_URL to enable the agent path"
        )
    return svc


@router.post("/api/v1/agent/ask", response_model=AgentAskResponse, tags=["agent"])
async def agent_ask(
    body: AgentAskRequest,
    request: Request,
    svc: AgentService = Depends(_agent_service),
) -> AgentAskResponse:
    tenant_id = getattr(request.state, "tenant_id", "") or ""
    correlation_id = getattr(request.state, "correlation_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")
    # Forward the caller's verified JWT to MCP so the server can
    # enforce per-tool scopes defence-in-depth. Also pass through
    # roles + auth_required so the agent can pre-check scope before
    # spending MCP bandwidth on requests it knows will 403.
    auth_token = getattr(request.state, "raw_token", "") or None
    roles = list(getattr(request.state, "roles", []) or [])
    auth_required = bool(getattr(request.app.state, "auth_required", False))
    # Idempotency-Key — when a client retries (network hiccups mid-flight)
    # the same key lets MCP replay its cached response instead of
    # executing a second tool call. Case-insensitive lookup because HTTP.
    idempotency_key = (
        request.headers.get("Idempotency-Key")
        or request.headers.get("X-Idempotency-Key")
    )
    return await svc.ask(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        request=body,
        auth_token=auth_token,
        roles=roles,
        auth_required=auth_required,
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------------------
# HITL admin — list + resolve persisted drafts from governance.action_drafts
# ---------------------------------------------------------------------------
def _mcp_client(request: Request):
    """Dep: the MCPClient attached in the lifespan. 503 if agent disabled."""
    client = getattr(request.app.state, "mcp_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="agent_service disabled — set DOCUMIND_MCP_HR_URL to enable the HITL path",
        )
    return client


def _record_to_summary(record) -> DraftSummary:
    return DraftSummary(
        draft_id=record.draft_id,
        tool=record.tool,
        arguments=record.arguments,
        tenant_id=record.tenant_id,
        correlation_id=record.correlation_id,
        reason=record.reason,
        status=record.status,
        created_at=record.created_at,
        replayed_at=record.replayed_at,
        replay_result=record.replay_result,
    )


@router.get(
    "/api/v1/drafts",
    response_model=DraftListResponse,
    tags=["hitl"],
    summary="List pending MCP action drafts for the current tenant",
)
async def list_drafts(
    request: Request,
    status: str = Query(
        "pending",
        description="Only 'pending' is supported today; exposed for forward-compat.",
    ),
    client = Depends(_mcp_client),
) -> DraftListResponse:
    tenant_id = getattr(request.state, "tenant_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")
    if status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"unsupported status filter: {status!r} (only 'pending' today)",
        )
    records = await client.list_pending_drafts(tenant_id)
    return DraftListResponse(
        drafts=[_record_to_summary(r) for r in records],
        tenant_id=tenant_id,
        status_filter=status,
    )


@router.post(
    "/api/v1/drafts/{draft_id}/resolve",
    response_model=DraftResolveResponse,
    tags=["hitl"],
    summary="Replay a pending MCP draft — uses draft_id as the idempotency key",
)
async def resolve_draft(
    draft_id: str,
    request: Request,
    client = Depends(_mcp_client),
) -> DraftResolveResponse:
    tenant_id = getattr(request.state, "tenant_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")

    # Two-phase scope check to avoid info leaks:
    #   (a) authenticate first — so an unauthenticated caller can't
    #       enumerate draft_ids by observing 404 vs 401 responses;
    #   (b) load the draft, derive the required role from the tool
    #       namespace, enforce *that* specific role.
    # When auth is disabled entirely, phase (a) is a no-op and phase
    # (b) short-circuits. Enable ``DOCUMIND_AUTH_REQUIRED`` to gate.
    auth_required = getattr(request.app.state, "auth_required", False)
    if auth_required:
        # (a) must be authenticated — 401 before any draft lookup.
        require_roles()(request)
        # (b) load + check tool-derived role.
        record = await client.get_draft(draft_id, tenant_id=tenant_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "DRAFT_NOT_FOUND", "draft_id": draft_id},
            )
        role = required_role_for_tool(record.tool)
        require_roles(role)(request)

    auth_token = getattr(request.state, "raw_token", "") or None
    result = await client.resolve_draft(
        draft_id, tenant_id=tenant_id, auth_token=auth_token,
    )
    # Error envelope from DraftStore: DRAFT_NOT_FOUND | DRAFT_NOT_PENDING
    if not result.ok and result.error and result.error.get("code") == "DRAFT_NOT_FOUND":
        raise HTTPException(status_code=404, detail=result.error)
    if not result.ok and result.error and result.error.get("code") == "DRAFT_NOT_PENDING":
        raise HTTPException(status_code=409, detail=result.error)
    return DraftResolveResponse(
        draft_id=draft_id,
        ok=result.ok,
        result=result.data,
        error=result.error,
        degraded=result.degraded,
        new_draft_id=result.draft_id if result.degraded else None,
        idempotent_replay=result.idempotent_replay,
    )
