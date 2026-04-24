"""Inference HTTP routes."""
from __future__ import annotations

from documind_core.exceptions import ValidationError
from documind_core.schemas import HealthResponse
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.schemas import (
    AgentAskRequest,
    AgentAskResponse,
    AskRequest,
    AskResponse,
    DraftListResponse,
    DraftResolveResponse,
    DraftSummary,
)
from app.services import RagInferenceService
from app.services.agent import AgentService

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="inference-svc")


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
    return await svc.ask(
        tenant_id=tenant_id, correlation_id=correlation_id, request=body,
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
    result = await client.resolve_draft(draft_id, tenant_id=tenant_id)
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
