"""Retrieval HTTP routes."""

from __future__ import annotations

import logging
from typing import Any

from documind_core.exceptions import ValidationError
from documind_core.schemas import HealthResponse
from fastapi import APIRouter, Depends, Query, Request

log = logging.getLogger(__name__)

from app.schemas import (
    BestConfigInfo,
    HealthBestConfigHistoryResponse,
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
    except Exception:  # noqa: BLE001,S110 — visibility must never crash
        pass  # noqa: S110 — intentional fail-safe (see comment above)

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


@router.get(
    "/api/v1/health/best-config-history",
    response_model=HealthBestConfigHistoryResponse,
    tags=["health"],
    summary="Promotion-gate audit trail summary (retrieval-svc projection)",
)
async def health_best_config_history(
    days: int = Query(
        7,
        ge=-1,
        le=365,
        description="Window in days; -1 means 'all rows'",
    ),
) -> HealthBestConfigHistoryResponse:
    """
    Symmetric to inference-svc /api/v1/health/best-config-history (commit 2741a93).
    Both services surface the SAME audit trail; the dashboard renders
    them side by side and verifies the two services agree on what's
    been promoted/rejected.

    Always returns 200. enabled+history_exists distinguish state.
    """
    from datetime import UTC, datetime

    observed_at = datetime.now(UTC).isoformat()
    enabled = False
    history_path = ".loop/best_config_history.jsonl"
    history_exists = False
    history_size_bytes = 0
    total = 0
    promoted = 0
    rejected = 0
    skipped = 0
    gates_failed_counts: dict[str, int] = {}
    latest_decision: dict[str, Any] | None = None
    earliest_ts = 0.0
    latest_ts = 0.0

    try:
        import sys

        sys.path.insert(0, "/mnt/deepa/rag/scripts")
        from best_config_history import (
            is_available,
            load_history,
            status,
            summarize,
        )

        st = status()
        enabled = bool(st.get("enabled_env", False))
        history_path = str(st.get("history_path", history_path))
        history_exists = bool(st.get("history_exists", False))
        history_size_bytes = int(st.get("history_size_bytes", 0))

        if is_available():
            rows = load_history()
            summary = summarize(rows, days=days)
            total = summary.total_attempts
            promoted = summary.promoted
            rejected = summary.rejected
            skipped = summary.skipped
            gates_failed_counts = dict(summary.gates_failed_counts)
            latest_decision = summary.latest_decision
            earliest_ts = summary.earliest_ts
            latest_ts = summary.latest_ts
    except Exception:  # noqa: BLE001,S110 — visibility never crashes
        pass  # noqa: S110 — intentional fail-safe (see comment above)

    return HealthBestConfigHistoryResponse(
        service="retrieval-svc",
        observed_at=observed_at,
        enabled=enabled,
        history_path=history_path,
        history_exists=history_exists,
        history_size_bytes=history_size_bytes,
        window_days=days,
        total_attempts=total,
        promoted=promoted,
        rejected=rejected,
        skipped=skipped,
        gates_failed_counts=gates_failed_counts,
        latest_decision=latest_decision,
        earliest_ts=earliest_ts,
        latest_ts=latest_ts,
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
    correlation_id = getattr(request.state, "correlation_id", "") or ""
    if not tenant_id:
        raise ValidationError("X-Tenant-ID header is required")
    response = await retriever.retrieve(tenant_id=tenant_id, request=body)
    # Per CLAUDE.md §47.7 expand-phase application: iter-53 wired the
    # lifespan; iter-54 wires the first retrieval-svc publish point.
    # query.retrieved.v1 surfaces hit-counts + breaker state for
    # downstream consumers (eval-svc, observability) without coupling
    # at HTTP-call level. Per §47 fail-safe: a Kafka blink does NOT
    # 5xx the user — they got their chunks; observability is best-effort.
    producer = getattr(request.app.state, "event_producer", None)
    if producer is not None:
        try:
            await producer.publish(
                topic="query.lifecycle",
                type="query.retrieved.v1",
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                key=tenant_id,
                data={
                    "query": (getattr(body, "query", "") or "")[:500],
                    "strategy": getattr(response, "strategy", "")
                    or getattr(body, "strategy", ""),
                    "retrieved_chunks": len(getattr(response, "chunks", []) or []),
                    "top_score": float(
                        getattr(response, "top_score", 0.0) or 0.0,
                    ),
                    "latency_ms": int(
                        getattr(response, "latency_ms", 0) or 0,
                    ),
                    "cached": bool(getattr(response, "cached", False)),
                    "breaker_state": getattr(response, "breaker_state", "")
                    or "",
                    "degraded": bool(getattr(response, "degraded", False)),
                },
            )
        except Exception as _exc:  # noqa: BLE001 — observability fail-safe
            log.warning("query_retrieved_publish_failed err=%s", _exc)
    return response
