"""Agent orchestrator FastAPI service."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from documind_core.config import get_settings
from documind_core.db_client import DbClient
from documind_core.logging_config import setup_logging
from documind_core.middleware import CorrelationIdMiddleware, SecurityHeadersMiddleware, register_exception_handlers
from documind_core.observability import instrument_fastapi, instrument_httpx, setup_observability
from fastapi import FastAPI, HTTPException, Query

from mcp import MCPClient

from .core.config import AgentOrchestratorSettings
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
