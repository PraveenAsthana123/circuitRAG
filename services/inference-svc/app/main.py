"""Inference service FastAPI application."""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from documind_core.config import get_settings
from documind_core.logging_config import setup_logging
from documind_core.auth import JWTAuthMiddleware, JWTVerifier
from documind_core.middleware import (
    CorrelationIdMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    SpanAttributeMiddleware,
    TenantContextMiddleware,
    register_exception_handlers,
)
from documind_core.observability import (
    instrument_asyncpg,
    instrument_fastapi,
    instrument_httpx,
    instrument_redis,
    obs_breaker,
    setup_observability,
)
from documind_core.rate_limiter import RateLimiter
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import InferenceSettings
from app.routers import router
from app.services import (
    GuardrailChecker,
    OllamaClient,
    PromptBuilder,
    RagInferenceService,
    RetrievalClient,
)

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings(InferenceSettings)
    setup_logging(service_name=settings.service_name, level=settings.log_level, json_format=settings.log_json)
    setup_observability(
        service_name=settings.service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        prometheus_port=settings.prometheus_port,
        environment=settings.env,
    )

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    retrieval = RetrievalClient(base_url=settings.retrieval_svc_url)
    ollama = OllamaClient(
        base_url=settings.ollama_url,
        model=settings.ollama_llm_model,
        timeout=settings.ollama_timeout_seconds,
    )
    prompts = PromptBuilder()
    guardrails = GuardrailChecker()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        import time as _time

        app.state.started_at_monotonic = _time.monotonic()
        # Expose the module-level observability breaker so the /detailed
        # health endpoint can report its state without another log scrape.
        app.state.obs_breaker = obs_breaker
        instrument_redis()
        instrument_httpx()
        # PG queries get their own spans inside the trace tree —
        # HITL draft save, audit row insert, draft lookup all become
        # visible under /api/v1/agent/ask instead of invisible gaps.
        instrument_asyncpg()
        app.state.rag_service = RagInferenceService(
            retrieval=retrieval,
            ollama=ollama,
            prompts=prompts,
            guardrails=guardrails,
            default_prompt=settings.prompt_version,
            max_new_tokens=settings.max_new_tokens,
            temperature=settings.temperature,
        )
        # Agent service (RAG + MCP). Configured to skip MCP wiring if the
        # URL is not set — services can run in "answer-only" mode without MCP.
        from app.services.agent import AgentService
        from documind_core.audit import AuditWriter
        from documind_core.db_client import DbClient
        from mcp import MCPClient, PostgresDraftStore

        # Postgres pool for durable draft persistence (governance.action_drafts)
        # and for the tamper-evident audit log (governance.audit_log).
        # We keep it optional: if PG is unreachable at boot, the MCPClient
        # falls back to an in-memory draft store so the service still starts.
        app.state.db_client = None
        draft_store = None
        audit_log = None
        try:
            db_client = DbClient(dsn=settings.postgres_dsn)
            await db_client.connect()
            app.state.db_client = db_client
            draft_store = PostgresDraftStore(db_client)
            audit_log = AuditWriter(db_client=db_client, service=settings.service_name)
            log.info("draft_store_ready backend=postgres audit_log_ready=true")
        except Exception as exc:  # noqa: BLE001 — PG optional; log + continue
            log.warning(
                "draft_store_fallback_inmemory reason=%s — drafts will not survive restart; audit disabled",
                exc,
            )

        mcp_url = os.getenv("DOCUMIND_MCP_HR_URL", "")
        if mcp_url:
            mcp_client = MCPClient(
                base_url=mcp_url,
                draft_store=draft_store,
                audit_log=audit_log,
            )
            app.state.mcp_client = mcp_client
            app.state.agent_service = AgentService(
                rag=app.state.rag_service,
                mcp=mcp_client,
                audit_log=audit_log,  # agent.scope_denied rows
            )
            log.info(
                "agent_service_ready mcp_url=%s draft_store=%s audit=%s",
                mcp_url,
                "postgres" if draft_store else "in_memory",
                "on" if audit_log else "off",
            )
        else:
            app.state.mcp_client = None
            app.state.agent_service = None
            log.info("agent_service_disabled reason=no_mcp_url")

        # Breaker metrics exporter — bridges non-CircuitBreaker breakers
        # (MCP client, OTel OCB) into the shared documind_circuit_breaker_state
        # gauge so Prometheus + Grafana see them as first-class series.
        app.state.breaker_metrics_exporter = None
        if app.state.mcp_client is not None or obs_breaker is not None:
            from app.workers.breaker_metrics import BreakerMetricsExporter

            exporter = BreakerMetricsExporter(
                mcp_client=app.state.mcp_client,
                obs_breaker=obs_breaker,
                interval_s=int(os.getenv("DOCUMIND_BREAKER_METRICS_INTERVAL_S", "5")),
            )
            await exporter.start()
            app.state.breaker_metrics_exporter = exporter

        # Draft replay worker — autonomous counterpart to the admin API.
        # Opt-in via env; requires a tenant list because the runtime role
        # is NOBYPASSRLS (can't enumerate tenants itself).
        app.state.draft_replay_worker = None
        if (
            app.state.mcp_client is not None
            and os.getenv("DOCUMIND_REPLAY_WORKER_ENABLED", "false").lower() == "true"
        ):
            from app.workers.draft_replay import DraftReplayWorker

            tenants_csv = os.getenv("DOCUMIND_REPLAY_WORKER_TENANTS", "").strip()
            tenants = [t.strip() for t in tenants_csv.split(",") if t.strip()]
            if tenants:
                worker = DraftReplayWorker(
                    mcp_client=app.state.mcp_client,
                    tenant_ids=tenants,
                    interval_s=int(os.getenv("DOCUMIND_REPLAY_WORKER_INTERVAL_S", "20")),
                    per_draft_backoff_s=int(os.getenv("DOCUMIND_REPLAY_WORKER_BACKOFF_S", "60")),
                )
                await worker.start()
                app.state.draft_replay_worker = worker
            else:
                log.warning(
                    "draft_replay_worker_disabled reason=no_tenants — set DOCUMIND_REPLAY_WORKER_TENANTS",
                )

        log.info("inference_service_ready model=%s", ollama.model)
        try:
            yield
        finally:
            if app.state.draft_replay_worker is not None:
                await app.state.draft_replay_worker.stop()
            if app.state.breaker_metrics_exporter is not None:
                await app.state.breaker_metrics_exporter.stop()
            await retrieval.aclose()
            await ollama.aclose()
            if app.state.mcp_client is not None:
                await app.state.mcp_client.close()
            if app.state.db_client is not None:
                await app.state.db_client.close()
            await redis_client.close()

    app = FastAPI(title="DocuMind — Inference Service", version="0.1.0", lifespan=lifespan)

    # JWT auth — opt-in via DOCUMIND_AUTH_REQUIRED. Even when "off" we
    # still parse tokens so endpoints that inspect roles work for
    # authenticated callers; it's the ``require_roles`` dep that does
    # the rejecting. Stash ``auth_required`` on app.state so routes can
    # branch on deployment posture (admin endpoints use this to decide
    # whether the scope check is load-bearing).
    auth_required = os.getenv("DOCUMIND_AUTH_REQUIRED", "false").lower() == "true"
    app.state.auth_required = auth_required
    # SpanAttributeMiddleware is added FIRST so it sits INNERMOST in the
    # Starlette chain and runs LAST on each request — by which time every
    # upstream middleware (CorrelationId, TenantContext, JWTAuth) has
    # populated request.state with authoritative values. Attributes like
    # documind.tenant_id then appear on the server span that Jaeger uses
    # as the trace root, so tag-filter searches by tenant work.
    app.add_middleware(SpanAttributeMiddleware)

    try:
        verifier = JWTVerifier(
            public_key_path=settings.jwt_public_key_path,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
        app.add_middleware(
            JWTAuthMiddleware, verifier=verifier, auth_required=auth_required,
        )
        log.info(
            "jwt_auth_ready required=%s key=%s issuer=%s",
            auth_required, settings.jwt_public_key_path, settings.jwt_issuer,
        )
    except FileNotFoundError as exc:
        if auth_required:
            raise  # can't enforce without the key — loud failure on boot
        log.warning("jwt_auth_disabled reason=%s — auth_required=false so continuing", exc)

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(redis_client),
        default_limit_per_min=settings.rate_limit_inference_per_min,
    )
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    instrument_fastapi(app)
    app.include_router(router)
    return app


app = create_app()
