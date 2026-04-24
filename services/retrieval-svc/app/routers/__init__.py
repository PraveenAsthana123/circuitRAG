"""Retrieval HTTP routes."""
from __future__ import annotations

from documind_core.exceptions import ValidationError
from documind_core.schemas import HealthResponse
from fastapi import APIRouter, Depends, Request

from app.schemas import RetrieveRequest, RetrieveResponse
from app.services import HybridRetriever

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="retrieval-svc")


def _retriever(request: Request) -> HybridRetriever:
    svc = getattr(request.app.state, "retriever", None)
    if svc is None:
        raise RuntimeError("retriever not initialized")
    return svc


@router.post("/api/v1/retrieve", response_model=RetrieveResponse, tags=["retrieval"])
async def retrieve(
    body: RetrieveRequest,
    request: Request,
    retriever: HybridRetriever = Depends(_retriever),
) -> RetrieveResponse:
    tenant_id = getattr(request.state, "tenant_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")
    return await retriever.retrieve(tenant_id=tenant_id, request=body)
