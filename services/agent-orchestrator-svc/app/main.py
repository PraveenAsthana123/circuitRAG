"""Agent orchestrator FastAPI service."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from documind_core.config import get_settings
from documind_core.db_client import DbClient
from documind_core.logging_config import setup_logging
from documind_core.body_limit import BodyLimitMiddleware
from documind_core.middleware import CorrelationIdMiddleware, SecurityHeadersMiddleware, register_exception_handlers
from documind_core.observability import instrument_fastapi, instrument_httpx, setup_observability
from fastapi import FastAPI, HTTPException, Query

from mcp import MCPClient

from .core.config import AgentOrchestratorSettings
from .explainability import REQUIRED_AUDIT_FIELDS, assemble_explanation
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
    MemoryRecordView,
    ModelCatalogEntryView,
    ProjectPlanItemView,
    ProjectView,
    TaskRunView,
    TaskView,
)
from .postgres_store import PostgresTaskStore
from .service import AgentOrchestratorService
from .store import InMemoryTaskStore


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

        db = DbClient(dsn=settings.postgres_dsn)
        store = None
        try:
            await db.connect()
            store = PostgresTaskStore(db)
            app.state.db = db
        except Exception:  # noqa: BLE001
            app.state.db = None
            store = InMemoryTaskStore()

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
        yield
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
    register_exception_handlers(app)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.post("/api/v1/agentic/tasks", response_model=TaskView)
    async def create_task(req: CreateTaskRequest) -> TaskView:
        return await app.state.service.create_task(req)

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
