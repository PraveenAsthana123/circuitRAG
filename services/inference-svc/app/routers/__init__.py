"""Inference HTTP routes."""
from __future__ import annotations

from documind_core.exceptions import ValidationError
from documind_core.schemas import HealthResponse
from fastapi import APIRouter, Depends, Query, Request

from app.schemas import AskRequest, AskResponse
from app.services import RagInferenceService

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
