"""Health check endpoint — liveness + readiness (Design Area 49)."""
from __future__ import annotations

from fastapi import APIRouter

from documind_core.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe — returns 200 if the process is alive."""
    return HealthResponse(status="ok", service="ingestion-svc")


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Kubernetes-style alias."""
    return {"status": "ok"}
