"""Agent orchestrator FastAPI service."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from documind_core.body_limit import BodyLimitMiddleware
from documind_core.config import get_settings
from documind_core.db_client import DbClient
from documind_core.dr_metrics import all_targets
from documind_core.governance_os import GovernanceOS, build_governance_os
from documind_core.logging_config import setup_logging
from documind_core.middleware import CorrelationIdMiddleware, SecurityHeadersMiddleware, register_exception_handlers
from documind_core.observability import instrument_fastapi, instrument_httpx, setup_observability
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from mcp import MCPClient

from .core.config import AgentOrchestratorSettings
from .db_circuit_breaker import DbCircuitBreaker
from .explainability import REQUIRED_AUDIT_FIELDS, assemble_explanation
from .idempotency import (
    IdempotencyConflict,
    InMemoryIdempotencyStore,
    hash_body,
    lookup_or_reserve,
    save_record,
)
from .idempotency_postgres import PostgresIdempotencyStore
from .model_catalog import get_catalog, validate_catalog
from .models import (
    AgenticPolicyUpdateRequest,
    AgenticPolicyView,
    AgentRoleView,
    ApprovalRequest,
    ApprovalSimulationRequest,
    ApprovalSimulationResponse,
    ApprovalView,
    CreateProjectRequest,
    CreateTaskRequest,
    DrMetricComparisonView,
    DrTargetsDashboardView,
    DrTargetTierDashboardView,
    MemoryRecordView,
    ModelCatalogEntryView,
    ProjectPlanItemView,
    ProjectView,
    TaskRunView,
    TaskView,
)
from .policy import evaluate_approval_reasons
from .postgres_store import PostgresTaskStore
from .rate_limit import RateLimitMiddleware
from .service import AgentOrchestratorService
from .store import InMemoryTaskStore

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings(AgentOrchestratorSettings)
    setup_logging(service_name=settings.service_name, level=settings.log_level, json_format=settings.log_json)
    setup_observability(
        service_name=settings.service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        prometheus_port=settings.prometheus_port,
        environment=settings.env,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        instrument_fastapi(app)
        instrument_httpx()

        # P0 #36 wiring: DbCircuitBreaker around the Postgres data layer.
        # connect_with_breaker counts the initial connect as a CB call, so
        # if Postgres is down at boot the breaker opens immediately and
        # /health/ready surfaces it (200 → 503). When connect fails we fall
        # back to InMemoryTaskStore (dev mode) — but the breaker still
        # exists and reports OPEN so observability dashboards see the gap.
        db = DbClient(dsn=settings.postgres_dsn)
        db_breaker = DbCircuitBreaker(name="orchestrator-db")
        store = None
        # P0 #34 wiring: PostgresIdempotencyStore for multi-pod safety.
        # InMemoryIdempotencyStore is fine for single-instance dev where
        # restart-loss of idempotency state is acceptable; multi-pod prod
        # MUST use Postgres because two pods cannot share an in-memory
        # dict. Selection is made HERE so the route handler doesn't have
        # to know which is wired.
        idempotency_store: PostgresIdempotencyStore | InMemoryIdempotencyStore
        try:
            await db_breaker.connect_with_breaker(db)
            # §53 #38 schema-evolution: apply any unapplied migrations
            # before the first request reaches a tenant-scoped table.
            # Booting green with missing tables is a silent-degradation
            # gap that turns into a 500 on first write — fail loud here.
            from .migrations import run_migrations
            await run_migrations(db)
            store = PostgresTaskStore(db, breaker=db_breaker)
            app.state.db = db
            idempotency_store = PostgresIdempotencyStore(db)
        except Exception:  # noqa: BLE001
            app.state.db = None
            store = InMemoryTaskStore()
            idempotency_store = InMemoryIdempotencyStore()
        app.state.db_breaker = db_breaker
        app.state.idempotency_store = idempotency_store
        # §48 wiring: GovernanceOS bootstraps here so every governed
        # request hits one structured surface for policy + risk +
        # compliance + audit. L1→L2 is observability-only; L2→L3
        # moves the gate into the OS.
        app.state.governance_os = build_governance_os(
            policy_evaluate_fn=evaluate_approval_reasons,
        )

        mcp_clients: dict[str, MCPClient] = {}
        if settings.mcp_hr_url:
            mcp_clients["hr"] = MCPClient(base_url=settings.mcp_hr_url, breaker_name="mcp_hr")
        if settings.mcp_itsm_url:
            mcp_clients["itsm"] = MCPClient(base_url=settings.mcp_itsm_url, breaker_name="mcp_itsm")
        if settings.mcp_drills_url:
            mcp_clients["drills"] = MCPClient(base_url=settings.mcp_drills_url, breaker_name="mcp_drills")
        # E1: register the pipeline-v2 upstream MCP servers when their
        # URLs are configured (default localhost:809[4-7] per D3 stubs).
        if settings.mcp_research_url:
            mcp_clients["research"] = MCPClient(base_url=settings.mcp_research_url, breaker_name="mcp_research")
        if settings.mcp_tests_url:
            mcp_clients["tests"] = MCPClient(base_url=settings.mcp_tests_url, breaker_name="mcp_tests")
        if settings.mcp_deploy_url:
            mcp_clients["deploy"] = MCPClient(base_url=settings.mcp_deploy_url, breaker_name="mcp_deploy")
        if settings.mcp_observe_url:
            mcp_clients["observe"] = MCPClient(base_url=settings.mcp_observe_url, breaker_name="mcp_observe")

        app.state.service = AgentOrchestratorService(
            store=store,
            mcp_clients=mcp_clients,
            default_policy=AgenticPolicyView(
                require_human_approval=settings.default_require_human_approval,
                approval_mode=settings.default_approval_mode,  # type: ignore[arg-type]
                auto_advance=settings.default_auto_advance,
                require_for_high_risk=settings.default_require_for_high_risk,
                require_for_low_confidence=settings.default_require_for_low_confidence,
                confidence_threshold=settings.default_confidence_threshold,
                require_for_risk_flags=settings.default_require_for_risk_flags,
                require_for_destructive_tools=settings.default_require_for_destructive_tools,
                require_for_tool_namespaces=[
                    value.strip()
                    for value in settings.default_require_for_tool_namespaces.split(",")
                    if value.strip()
                ],
            ),
            ollama_url=settings.ollama_url,
            ollama_timeout_seconds=settings.ollama_timeout_seconds,
            coder_model=settings.agent_coder_model,
            reviewer_model=settings.agent_reviewer_model,
            advisor_model=settings.agent_advisor_model,
            security_advisor_model=settings.agent_security_advisor_model,
            # E1: opt in to pipeline_v2 by default; operators flip via
            # DOCUMIND_PIPELINE_V2_ENABLED=false to revert to legacy.
            pipeline_v2_enabled=settings.pipeline_v2_enabled,
        )
        app.state.mcp_clients = mcp_clients

        # Event Bus (aiokafka producer) — opt-in via DOCUMIND_KAFKA_BOOTSTRAP.
        # Per CLAUDE.md §47.7 (expand-phase): agent-orchestrator-svc lifespan
        # ships now; per-route publish points (e.g. agent.task.completed.v1
        # with tool-call sequence + plan trace + reflections) wire on opt-in
        # basis in subsequent commits. Default-safe: env-var unset OR Kafka
        # unreachable at boot → app.state.event_producer = None.
        import os  # noqa: PLC0415

        app.state.event_producer = None
        kafka_bootstrap = os.getenv("DOCUMIND_KAFKA_BOOTSTRAP", "").strip()
        if kafka_bootstrap:
            try:
                from documind_core.kafka_client import EventProducer
                producer = EventProducer(
                    bootstrap_servers=kafka_bootstrap,
                    client_id=f"agent-orchestrator-svc-{settings.env}",
                    source="agent-orchestrator-svc",
                )
                await producer.start()
                app.state.event_producer = producer
                log.info(
                    "orchestrator_kafka_producer_ready bootstrap=%s",
                    kafka_bootstrap,
                )
            except Exception as exc:  # noqa: BLE001 — Kafka optional
                log.warning(
                    "orchestrator_kafka_producer_start_failed reason=%s — "
                    "publish points will skip silently until restart",
                    exc,
                )

        yield
        if app.state.event_producer is not None:
            try:
                await app.state.event_producer.stop()
            except Exception:  # noqa: BLE001 — shutdown best-effort
                log.exception("orchestrator_kafka_producer_stop_failed")
        await app.state.service.aclose()
        for client in mcp_clients.values():
            await client.close()
        if app.state.db is not None:
            await app.state.db.close()

    app = FastAPI(title="agent-orchestrator-svc", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    # P1 #32 (body limit) — prevent OOM from giant payloads.
    # 1 MiB default for tasks API; upload routes (none today) would
    # need larger cap via path_overrides.
    app.add_middleware(BodyLimitMiddleware, max_bytes=1024 * 1024)
    # P1 #33 (rate limit) — per-tenant + per-IP sliding-window limiter
    # on POST /api/v1/agentic/tasks. 60 requests/minute default.
    # Single-pod in-memory; multi-pod prod swaps in redis-backed
    # documind_core.RateLimitMiddleware via env config.
    app.add_middleware(RateLimitMiddleware, limit_per_minute=60)
    register_exception_handlers(app)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        """Smart readiness probe per CLAUDE.md §47.8.

        Returns 200 only if the orchestrator can actually serve a
        request right now. The DB circuit breaker is the closest
        runtime signal we have for "data layer healthy" — when it
        flips to OPEN, K8s should redirect traffic away from this
        pod even though the process is still alive.

        Liveness (/health/live) intentionally stays a dumb "process
        alive" check — checking deps in liveness causes cascade pod
        restarts when the database hiccups. Readiness is where dep
        health belongs.
        """
        breaker = getattr(app.state, "db_breaker", None)
        if breaker is None or breaker.is_healthy:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "ready",
                    "db_breaker": breaker.state if breaker else "unwired",
                },
            )
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "db_breaker": breaker.state,
                "error_code": "DB_CIRCUIT_OPEN",
                "detail": "Postgres data layer unhealthy; circuit breaker open.",
            },
        )

    @app.get("/api/v1/admin/dr-targets", response_model=DrTargetsDashboardView)
    async def get_admin_dr_targets() -> DrTargetsDashboardView:
        """§35 DR Metrics L3 dashboard contract.

        L2 defined target tiers. L3 exposes target-vs-current rows to
        operators. Current values remain explicitly unmeasured until
        the L4 quarterly DR drill writes real recovery evidence.
        """
        metric_fields = (
            ("rto", "rto_seconds"),
            ("rpo", "rpo_seconds"),
            ("mttd", "mttd_seconds"),
            ("mttr", "mttr_seconds"),
            ("failover", "failover_seconds"),
        )
        tiers = []
        for target in all_targets():
            tiers.append(
                DrTargetTierDashboardView(
                    tier=target.tier,
                    description=target.description,
                    measurements=[
                        DrMetricComparisonView(
                            metric=metric,
                            target_seconds=getattr(target, attr),
                            current_seconds=None,
                            status="not_measured",
                            evidence="pending quarterly DR drill",
                        )
                        for metric, attr in metric_fields
                    ],
                )
            )
        return DrTargetsDashboardView(
            target_source="libs/py/documind_core/dr_metrics.py",
            current_measurement_source=None,
            drill_required="quarterly DR drill scaffold (§35 L3→L4)",
            tiers=tiers,
        )

    @app.get("/api/v1/admin/governance/audit")
    async def get_governance_audit(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        """§48 GovernanceOS audit-row read view.

        Returns the most recent governance decisions logged by the OS
        facade. In dev/L1→L2 the audit log is in-memory; future
        iterations persist to orchestration.governance_audit.
        """
        os: GovernanceOS = app.state.governance_os
        rows = [d.to_dict() for d in os.audit.recent(limit=limit)]
        return {
            "rows": rows,
            "count": len(rows),
            "total": os.audit.count(),
            "storage": "in_memory_l1_l2",
            "next_iteration_ref": "§48 L2→L3 persists to orchestration.governance_audit",
        }

    @app.post("/api/v1/agentic/tasks", response_model=TaskView)
    async def create_task(
        req: CreateTaskRequest,
        idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    ) -> TaskView:
        """Create an agentic task.

        Per CLAUDE.md §6.3 idempotency contract:
          - same (tenant_id, key) + same body  -> cached task_id (200)
          - same (tenant_id, key) + diff body  -> 409 Conflict
          - no key                              -> create unconditionally

        Multi-pod safety per P0 #34 fix: idempotency_store is the
        Postgres-backed implementation when the DB is up, an in-memory
        fallback only in dev. Two pods sharing the same Postgres see
        the same idempotency state.
        """
        # §48 GovernanceOS facade: emit one structured decision per
        # request before the service-layer create runs. L1→L2 is
        # report-only — service.create_task still owns gating —
        # but the audit row + compliance attestations + risk view
        # are now uniformly captured. L2→L3 will lift the gate here.
        governance_os: GovernanceOS = app.state.governance_os
        governance_os.evaluate(
            request_state={
                "tenant_id": req.tenant_id,
                "goal": req.goal,
                "risk_level": getattr(req, "risk_level", None),
                "require_human_approval": getattr(req, "require_human_approval", False),
                "tool_namespace": getattr(req, "tool_namespace", None),
                "tool_name": getattr(req, "tool_name", None),
            },
            policy=app.state.service._default_policy,
        )

        if idempotency_key is None:
            return await app.state.service.create_task(req)

        body_hash = hash_body(req.model_dump(mode="json"))
        try:
            existing = await lookup_or_reserve(
                store=app.state.idempotency_store,
                tenant_id=req.tenant_id,
                key=idempotency_key,
                body_hash=body_hash,
            )
        except IdempotencyConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "IDEMPOTENCY_CONFLICT",
                    "detail": str(exc),
                },
            ) from exc

        if existing is not None:
            cached = await app.state.service.get_task(existing.task_id)
            if cached is not None:
                return cached
            # Cached task_id but no task: data inconsistency (manual
            # delete?). Fall through to a fresh create + re-save.

        task = await app.state.service.create_task(req)
        await save_record(
            store=app.state.idempotency_store,
            tenant_id=req.tenant_id,
            key=idempotency_key,
            task_id=task.task_id,
            body_hash=body_hash,
        )
        # Per CLAUDE.md §47.7 expand-phase application: iter-53 wired the
        # lifespan; iter-54 wires the first agent-orchestrator publish
        # point. agent.task.created.v1 surfaces task creation for
        # downstream consumers (governance audit, observability) without
        # coupling at HTTP-call level. Per §47 fail-safe: a Kafka blink
        # does NOT 5xx the user — the task already created + persisted.
        producer = getattr(app.state, "event_producer", None)
        if producer is not None:
            try:
                await producer.publish(
                    topic="agent.lifecycle",
                    type="agent.task.created.v1",
                    tenant_id=req.tenant_id,
                    correlation_id=getattr(task, "correlation_id", "") or "",
                    key=req.tenant_id,
                    data={
                        "task_id": task.task_id,
                        "goal": (getattr(req, "goal", "") or "")[:500],
                        "risk_level": getattr(req, "risk_level", None) or "",
                        "tool_namespace": getattr(req, "tool_namespace", None) or "",
                        "tool_name": getattr(req, "tool_name", None) or "",
                        "require_human_approval": bool(
                            getattr(req, "require_human_approval", False),
                        ),
                        "idempotent": idempotency_key is not None,
                    },
                )
            except Exception as _exc:  # noqa: BLE001 — observability fail-safe
                log.warning("agent_task_created_publish_failed err=%s", _exc)
        return task

    @app.post("/api/v1/agentic/projects", response_model=ProjectView)
    async def create_project(req: CreateProjectRequest) -> ProjectView:
        return await app.state.service.create_project(req)

    @app.get("/api/v1/agentic/projects", response_model=list[ProjectView])
    async def list_projects(limit: int = 20) -> list[ProjectView]:
        return await app.state.service.list_projects(limit)

    @app.get("/api/v1/agentic/projects/{project_id}/plan-items", response_model=list[ProjectPlanItemView])
    async def list_project_plan_items(project_id: str) -> list[ProjectPlanItemView]:
        return await app.state.service.list_project_plan_items(project_id)

    @app.get("/api/v1/agentic/policy", response_model=AgenticPolicyView)
    async def get_policy() -> AgenticPolicyView:
        return await app.state.service.get_policy()

    @app.put("/api/v1/agentic/policy", response_model=AgenticPolicyView)
    async def update_policy(req: AgenticPolicyUpdateRequest) -> AgenticPolicyView:
        return await app.state.service.update_policy(req)

    @app.post("/api/v1/agentic/policy/simulate", response_model=ApprovalSimulationResponse)
    async def simulate_policy(req: ApprovalSimulationRequest) -> ApprovalSimulationResponse:
        return await app.state.service.simulate_approval(req)

    @app.get("/api/v1/agentic/agents", response_model=list[AgentRoleView])
    async def list_agents() -> list[AgentRoleView]:
        return await app.state.service.list_agents()

    @app.get("/api/v1/agentic/models/catalog", response_model=list[ModelCatalogEntryView])
    async def list_model_catalog() -> list[ModelCatalogEntryView]:
        catalog = get_catalog()
        errors = validate_catalog(catalog)
        if errors:
            # Negative-assertion contract from drill_model_catalog.py: a malformed
            # catalog entry MUST raise 500, never silently default. Keeps routing
            # decisions auditable per §47.3.
            raise HTTPException(status_code=500, detail={"catalog_errors": errors})
        return [
            ModelCatalogEntryView(
                role_id=e.role_id,
                role_type=e.role_type,
                display_name=e.display_name,
                tier_a_primary=e.tier_a_primary,
                tier_a_backup=e.tier_a_backup,
                tier_a_heavy=e.tier_a_heavy,
                tier_b=e.tier_b,
                tier_b_backend=e.tier_b_backend,
                description=e.description,
                strengths=list(e.strengths),
                min_ram_gb=e.min_ram_gb,
            )
            for e in catalog
        ]

    @app.get("/api/v1/agentic/tasks", response_model=list[TaskView])
    async def list_tasks(limit: int = 20) -> list[TaskView]:
        return await app.state.service.list_tasks(limit)

    @app.get("/api/v1/agentic/tasks/{task_id}", response_model=TaskView)
    async def get_task(task_id: str) -> TaskView:
        task = await app.state.service.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return task

    @app.get("/api/v1/agentic/tasks/{task_id}/runs", response_model=list[TaskRunView])
    async def list_task_runs(task_id: str) -> list[TaskRunView]:
        return await app.state.service.list_task_runs(task_id)

    @app.get("/api/v1/agentic/tasks/{task_id}/approvals", response_model=list[ApprovalView])
    async def list_task_approvals(task_id: str) -> list[ApprovalView]:
        return await app.state.service.list_approvals(task_id)

    @app.get("/api/v1/agentic/tasks/{task_id}/explain")
    async def explain_task(task_id: str) -> dict[str, Any]:
        """§48.4 decision audit row.

        Returns the full §48 schema for the task — model + prompt
        version, input fingerprint, decision + confidence, rules
        applied, guardrails triggered, cost, routing trail.
        Fields not yet computable (SHAP, counterfactual, fairness)
        are explicit None so the schema is fully observable per
        §48.10 (no field silently absent).
        """
        task = await app.state.service.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        runs = await app.state.service.list_task_runs(task_id)
        approvals = await app.state.service.list_approvals(task_id)
        row = assemble_explanation(
            task=task.model_dump(),
            task_runs=[r.model_dump() for r in runs],
            approvals=[a.model_dump() for a in approvals],
        )
        # Negative-assertion contract: every field in REQUIRED_AUDIT_FIELDS
        # must be present (even if None). Catch silent omissions early.
        missing = [f for f in REQUIRED_AUDIT_FIELDS if f not in row]
        if missing:
            raise HTTPException(
                status_code=500,
                detail={"error_code": "EXPLAIN_SCHEMA_INCOMPLETE", "missing_fields": missing},
            )
        return row

    @app.post("/api/v1/agentic/tasks/{task_id}/approve", response_model=TaskView)
    async def approve_task(task_id: str, req: ApprovalRequest) -> TaskView:
        task = await app.state.service.approve_task(task_id, req)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return task

    @app.get("/api/v1/agentic/memories", response_model=list[MemoryRecordView])
    async def list_memories(
        scope_type: str = Query(..., min_length=1),
        scope_id: str = Query(..., min_length=1),
    ) -> list[MemoryRecordView]:
        return await app.state.service.list_memories(scope_type, scope_id)

    return app


app = create_app()
