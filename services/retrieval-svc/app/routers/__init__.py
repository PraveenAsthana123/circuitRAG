"""Retrieval HTTP routes."""

from __future__ import annotations

from documind_core.exceptions import ValidationError
from documind_core.schemas import HealthResponse
from fastapi import APIRouter, Depends, Request

from app.schemas import (
    BestConfigInfo,
    HealthBestConfigResponse,
    RetrieveRequest,
    RetrieveResponse,
)
from app.services import HybridRetriever

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="retrieval-svc")


@router.get(
    "/api/v1/health/best-config",
    response_model=HealthBestConfigResponse,
    tags=["health"],
    summary="Live best_config registry — what HybridRetriever would seed RIGHT NOW",
)
async def health_best_config() -> HealthBestConfigResponse:
    """
    Symmetric to inference-svc /api/v1/health/best-config (commit 01729e0).
    Surfaces what min_score / top_k / rerank flag the retriever would
    seed when the caller didn't override.

    Always returns 200. enabled+loaded fields tell the UI the state.
    Per CLAUDE.md §47 fail-safe: NEVER raises on loader-import error.
    """
    from datetime import UTC, datetime

    observed_at = datetime.now(UTC).isoformat()
    config: BestConfigInfo | None = None
    enabled = False
    loaded = False
    config_path = ".loop/best_config.json"
    config_exists = False
    config_size_bytes = 0
    ttl_s = 300.0
    cache_age_s = 0.0
    fallback_defaults: dict = {}
    next_stage = ""

    try:
        import sys

        sys.path.insert(0, "/mnt/deepa/rag/scripts")
        from best_config_loader import (
            is_available,
            load_best_config,
            status,
        )

        st = status()
        enabled = bool(st.get("enabled_env", False))
        config_path = str(st.get("config_path", config_path))
        config_exists = bool(st.get("config_exists", False))
        config_size_bytes = int(st.get("config_size_bytes", 0))
        ttl_s = float(st.get("ttl_s", 300.0))
        cache_age_s = float(st.get("cache_age_s", 0.0))
        fallback_defaults = dict(st.get("fallback_defaults", {}))
        next_stage = str(st.get("next_stage", ""))

        if is_available():
            cfg = load_best_config()
            if cfg is not None:
                loaded = True
                config = BestConfigInfo(
                    min_score=cfg.min_score,
                    top_k=cfg.top_k,
                    rerank_enabled=cfg.rerank_enabled,
                    rerank_top_k=cfg.rerank_top_k,
                    chunking_strategy=cfg.chunking_strategy,
                    pass_rate=cfg.pass_rate,
                    promoted_at_ts=cfg.promoted_at_ts,
                    eval_set_size=cfg.eval_set_size,
                )
    except Exception:  # noqa: BLE001 — visibility must never crash
        pass

    return HealthBestConfigResponse(
        service="retrieval-svc",
        observed_at=observed_at,
        enabled=enabled,
        loaded=loaded,
        config_path=config_path,
        config_exists=config_exists,
        config_size_bytes=config_size_bytes,
        ttl_s=ttl_s,
        cache_age_s=cache_age_s,
        fallback_defaults=fallback_defaults,
        config=config,
        next_stage=next_stage,
    )


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
