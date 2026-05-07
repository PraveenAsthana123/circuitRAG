"""Health check endpoint — liveness + readiness (Design Area 49)."""

from __future__ import annotations

from documind_core.schemas import HealthResponse
from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe — returns 200 if the process is alive."""
    return HealthResponse(status="ok", service="ingestion-svc")


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Kubernetes-style alias."""
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(request: Request, response: Response) -> dict:
    """Readiness probe — gates traffic on real subsystem health.

    Currently probes:
      - outbox drain worker (if present): must report is_running()=True

    Status:
      - 200 + ``ready=true``  — all subsystems alive (or worker absent
                                because Kafka was down at boot — that
                                is "degraded" not "broken"; treat as
                                ready so the API tier still serves)
      - 503 + ``ready=false`` — worker exists but has crashed (silent
                                outbox backlog risk — exact failure mode
                                that produced 186 stale rows pre-fix)
    """
    worker = getattr(request.app.state, "outbox_worker", None)
    if worker is None:
        return {"ready": True, "outbox_worker": "absent"}
    is_running = worker.is_running()
    if not is_running:
        response.status_code = 503
        return {"ready": False, "outbox_worker": "crashed"}
    return {"ready": True, "outbox_worker": "running"}
