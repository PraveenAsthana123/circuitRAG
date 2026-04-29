from __future__ import annotations

from datetime import datetime
import uuid

from mcp import MCPClient

from .agent_registry import build_agent_specs
from .agents import ManagerAgent, ReviewerAgent, SecurityAdvisor, WorkerAgent
from .langgraph_flow import build_graph
from .models import (
    AgentRoleView,
    AgenticPolicyUpdateRequest,
    AgenticPolicyView,
    ApprovalRequest,
    ApprovalSimulationRequest,
    ApprovalSimulationResponse,
    CreateProjectRequest,
    CreateTaskRequest,
    ProjectPlanItem,
    ProjectView,
    TaskView,
)
from .ollama_client import OllamaGenerateClient
from .policy import evaluate_approval_reasons
from .store import InMemoryTaskStore


class AgentOrchestratorService:
    def __init__(
        self,
        store: InMemoryTaskStore | None = None,
        *,
        mcp_clients: dict[str, MCPClient] | None = None,
        default_policy: AgenticPolicyView | None = None,
        ollama_url: str = "http://localhost:11434",
        ollama_timeout_seconds: float = 60.0,
        coder_model: str = "deepseek-coder:6.7b-instruct",
        reviewer_model: str = "starcoder2:7b",
        advisor_model: str = "deepseek-coder:6.7b-instruct",
        security_advisor_model: str = "codellama:7b-instruct",
    ) -> None:
        self._store = store or InMemoryTaskStore()
        self._default_policy = default_policy or AgenticPolicyView()
        self._ollama = OllamaGenerateClient(base_url=ollama_url, timeout_seconds=ollama_timeout_seconds)
        self._agent_specs = build_agent_specs(
            coder_model=coder_model,
            reviewer_model=reviewer_model,
            advisor_model=advisor_model,
            security_advisor_model=security_advisor_model,
        )
        spec_map = {spec.role_id: spec for spec in self._agent_specs}
        self._graph = build_graph(
            manager=ManagerAgent(),
            worker=WorkerAgent(mcp_clients=mcp_clients, ollama=self._ollama, spec=spec_map["coder_executor"]),
            reviewer=ReviewerAgent(ollama=self._ollama, spec=spec_map["reviewer"]),
            advisor=SecurityAdvisor(ollama=self._ollama, spec=spec_map["advisor"]),
            default_policy=self._default_policy,
        )

    async def aclose(self) -> None:
        await self._ollama.close()

    async def list_agents(self) -> list[AgentRoleView]:
        return [
            AgentRoleView(
                role_id=spec.role_id,
                role_type=spec.role_type,
                display_name=spec.display_name,
                model=spec.model,
                description=spec.description,
                source_agent_name=spec.source_agent_name,
            )
            for spec in self._agent_specs
        ]

    async def create_task(self, req: CreateTaskRequest) -> TaskView:
        return await self._create_task_internal(req, attach_to_project=True)

    async def _create_task_internal(self, req: CreateTaskRequest, *, attach_to_project: bool) -> TaskView:
        policy = await self._resolve_policy(
            tenant_id=req.tenant_id,
            project_id=req.project_id,
            use_global_policy=req.use_global_policy,
            require_human_approval=req.require_human_approval,
            approval_mode=req.approval_mode,
            auto_advance=req.auto_advance,
        )

        task = TaskView(
            task_id=uuid.uuid4().hex,
            tenant_id=req.tenant_id,
            project_id=req.project_id,
            goal=req.goal,
            status="created",
            risk_level=req.risk_level,
            require_human_approval=policy.require_human_approval,
            approval_mode=policy.approval_mode,
            auto_advance=policy.auto_advance,
            approved=True if policy.approval_mode == "policy_auto" else None,
            tool_namespace=req.tool_namespace,
            tool_name=req.tool_name,
            tool_arguments=req.tool_arguments,
            approval_reasons=[],
            plan=[],
            reviewer_notes=[],
            audit_events=[{"role": "api", "event": "created", "at": datetime.utcnow().isoformat()}],
        )
        await self._store.save(task)
        result = await self._graph.ainvoke({**task.model_dump(), "resume_from": "manager_plan", "policy": policy.model_dump()})
        updated = task.model_copy(update=result)
        await self._store.save(updated)
        if req.project_id and attach_to_project:
            await self._attach_task_to_project(req.project_id, updated.task_id)
        return updated

    async def get_policy(self) -> AgenticPolicyView:
        if hasattr(self._store, "get_policy"):
            return await self._store.get_policy()
        return self._default_policy

    async def update_policy(self, req: AgenticPolicyUpdateRequest) -> AgenticPolicyView:
        policy = AgenticPolicyView(
            require_human_approval=req.require_human_approval,
            approval_mode=req.approval_mode,
            auto_advance=req.auto_advance,
            updated_by=req.updated_by,
        )
        if hasattr(self._store, "save_policy"):
            return await self._store.save_policy(policy)
        self._default_policy = policy
        return policy

    async def get_task(self, task_id: str) -> TaskView | None:
        return await self._store.get(task_id)

    async def list_tasks(self, limit: int = 20) -> list[TaskView]:
        return await self._store.list_recent(limit)

    async def create_project(self, req: CreateProjectRequest) -> ProjectView:
        policy_override = None
        if not req.use_global_policy and req.policy_override is not None:
            policy_override = AgenticPolicyView(
                require_human_approval=req.policy_override.require_human_approval,
                approval_mode=req.policy_override.approval_mode,
                auto_advance=req.policy_override.auto_advance,
                require_for_high_risk=req.policy_override.require_for_high_risk,
                require_for_low_confidence=req.policy_override.require_for_low_confidence,
                confidence_threshold=req.policy_override.confidence_threshold,
                require_for_risk_flags=req.policy_override.require_for_risk_flags,
                require_for_destructive_tools=req.policy_override.require_for_destructive_tools,
                require_for_tool_namespaces=req.policy_override.require_for_tool_namespaces,
                updated_by=req.policy_override.updated_by,
            )
        project = ProjectView(
            project_id=uuid.uuid4().hex,
            tenant_id=req.tenant_id,
            name=req.name,
            goal=req.goal,
            status="planned",
            use_global_policy=req.use_global_policy,
            task_ids=[],
            planned_tasks=[
                ProjectPlanItem.model_validate(item)
                for item in await ManagerAgent().expand_project(req.goal)
            ],
            policy_override=policy_override,
            audit_events=[
                {"role": "api", "event": "project_created", "at": datetime.utcnow().isoformat()},
                {"role": "manager", "event": "project_expanded", "at": datetime.utcnow().isoformat()},
            ],
        )
        await self._store.save_project(project)
        return await self._run_project(project.project_id) or project

    async def list_projects(self, limit: int = 20) -> list[ProjectView]:
        if hasattr(self._store, "list_projects"):
            return await self._store.list_projects(limit)
        return []

    async def get_project(self, project_id: str) -> ProjectView | None:
        if hasattr(self._store, "get_project"):
            return await self._store.get_project(project_id)
        return None

    async def simulate_approval(self, req: ApprovalSimulationRequest) -> ApprovalSimulationResponse:
        policy = await self._resolve_policy(
            tenant_id=req.tenant_id,
            project_id=req.project_id,
            use_global_policy=req.use_global_policy,
            require_human_approval=req.require_human_approval,
            approval_mode=req.approval_mode,
            auto_advance=req.auto_advance,
        )
        state = {
            "tenant_id": req.tenant_id,
            "goal": req.goal,
            "risk_level": req.risk_level,
            "require_human_approval": policy.require_human_approval,
            "approval_mode": policy.approval_mode,
            "auto_advance": policy.auto_advance,
            "project_id": req.project_id,
            "tool_namespace": req.tool_namespace,
            "tool_name": req.tool_name,
            "tool_arguments": req.tool_arguments,
            "confidence": req.predicted_confidence,
            "worker_risks": req.predicted_risks,
        }
        reasons = evaluate_approval_reasons(state, policy)
        return ApprovalSimulationResponse(
            effective_policy=policy,
            approval_reasons=reasons,
            approval_required=policy.approval_mode != "policy_auto" and len(reasons) > 0,
        )

    async def approve_task(self, task_id: str, req: ApprovalRequest) -> TaskView | None:
        task = await self._store.get(task_id)
        if task is None:
            return None
        events = list(task.audit_events)
        events.append(
            {
                "role": "human",
                "event": "approval",
                "actor_id": req.actor_id,
                "approved": req.approved,
                "reason": req.reason,
                "at": datetime.utcnow().isoformat(),
            },
        )
        if not req.approved:
            updated = task.model_copy(
                update={
                    "approved": False,
                    "status": "rejected",
                    "next_action": "finalized_by_human",
                    "audit_events": events,
                },
            )
            await self._store.save(updated)
            if updated.project_id:
                await self._mark_project_blocked(updated.project_id, updated.task_id, "rejected")
            return updated

        updated = task.model_copy(
            update={
                "approved": True,
                "status": "approved",
                "next_action": "resume_workflow" if task.auto_advance else "approved_waiting_for_continue",
                "audit_events": events,
            },
        )

        if task.status == "waiting_for_plan_approval" and task.auto_advance:
            resumed_result = await self._graph.ainvoke(
                {
                    **updated.model_dump(),
                    "resume_from": "worker_execute",
                    "policy": (await self._resolve_task_policy(updated)).model_dump(),
                },
            )
            updated = updated.model_copy(update=resumed_result)
        elif task.status == "waiting_for_approval":
            completion_events = list(updated.audit_events)
            completion_events.append(
                {
                    "role": "orchestrator",
                    "event": "finalized_after_human_approval",
                    "at": datetime.utcnow().isoformat(),
                },
            )
            updated = updated.model_copy(
                update={
                    "status": "completed",
                    "next_action": "done",
                    "audit_events": completion_events,
                },
            )

        await self._store.save(updated)
        if updated.project_id:
            project = await self._advance_project_after_task(updated.project_id, updated.task_id, updated.status)
            if project is not None:
                task_after_project = await self._store.get(updated.task_id)
                if task_after_project is not None:
                    updated = task_after_project
        return updated

    async def _resolve_task_policy(self, task: TaskView) -> AgenticPolicyView:
        return await self._resolve_policy(
            tenant_id=task.tenant_id,
            project_id=task.project_id,
            use_global_policy=False,
            require_human_approval=task.require_human_approval,
            approval_mode=task.approval_mode,  # type: ignore[arg-type]
            auto_advance=task.auto_advance,
        )

    async def _resolve_policy(
        self,
        *,
        tenant_id: str,
        project_id: str | None,
        use_global_policy: bool,
        require_human_approval: bool | None,
        approval_mode: str | None,
        auto_advance: bool | None,
    ) -> AgenticPolicyView:
        base_policy = await self.get_policy()
        if project_id:
            project = await self.get_project(project_id)
            if project and not project.use_global_policy and project.policy_override:
                base_policy = project.policy_override
        if use_global_policy:
            return base_policy
        return base_policy.model_copy(
            update={
                "require_human_approval": require_human_approval if require_human_approval is not None else base_policy.require_human_approval,
                "approval_mode": approval_mode or base_policy.approval_mode,
                "auto_advance": auto_advance if auto_advance is not None else base_policy.auto_advance,
            },
        )

    async def _attach_task_to_project(self, project_id: str, task_id: str) -> None:
        project = await self.get_project(project_id)
        if project is None or task_id in project.task_ids:
            return
        updated = project.model_copy(
            update={
                "task_ids": [*project.task_ids, task_id],
                "audit_events": [
                    *project.audit_events,
                    {"role": "orchestrator", "event": "task_attached", "task_id": task_id, "at": datetime.utcnow().isoformat()},
                ],
            },
        )
        await self._store.save_project(updated)

    async def _run_project(self, project_id: str) -> ProjectView | None:
        project = await self.get_project(project_id)
        if project is None:
            return None

        current = project.model_copy(update={"status": "running"})
        await self._store.save_project(current)

        for idx, item in enumerate(current.planned_tasks):
            if item.status == "completed":
                continue
            if item.status in {"waiting_for_approval", "waiting_for_plan_approval", "blocked", "rejected"}:
                return current
            if item.task_id:
                existing_task = await self._store.get(item.task_id)
                if existing_task is not None:
                    final_status = self._project_status_for_task(existing_task.status)
                    planned_tasks = list(current.planned_tasks)
                    planned_tasks[idx] = item.model_copy(update={"status": final_status})
                    current = current.model_copy(update={"planned_tasks": planned_tasks})
                    await self._store.save_project(current)
                    if final_status == "completed":
                        continue
                    if final_status in {"waiting_for_approval", "waiting_for_plan_approval"}:
                        current = current.model_copy(update={"status": "waiting_for_approval"})
                    elif final_status == "rejected":
                        current = current.model_copy(update={"status": "blocked"})
                    await self._store.save_project(current)
                    return current

            running_item = item.model_copy(update={"status": "running"})
            planned_tasks = list(current.planned_tasks)
            planned_tasks[idx] = running_item
            current = current.model_copy(update={"planned_tasks": planned_tasks})
            await self._store.save_project(current)

            task = await self._create_task_internal(
                CreateTaskRequest(
                    goal=running_item.goal,
                    tenant_id=current.tenant_id,
                    project_id=current.project_id,
                    risk_level=running_item.suggested_risk,
                    use_global_policy=current.use_global_policy,
                    tool_namespace=running_item.tool_namespace,
                    tool_name=running_item.tool_name,
                    tool_arguments=running_item.tool_arguments,
                ),
                attach_to_project=True,
            )

            final_status = self._project_status_for_task(task.status)
            planned_tasks = list(current.planned_tasks)
            planned_tasks[idx] = running_item.model_copy(update={"status": final_status, "task_id": task.task_id})

            project_status = "running"
            if final_status in {"waiting_for_approval", "waiting_for_plan_approval"}:
                project_status = "waiting_for_approval"
            elif final_status == "rejected":
                project_status = "blocked"

            current = current.model_copy(
                update={
                    "planned_tasks": planned_tasks,
                    "status": project_status,
                    "audit_events": [
                        *current.audit_events,
                        {
                            "role": "orchestrator",
                            "event": "project_step_executed",
                            "step_id": running_item.step_id,
                            "task_id": task.task_id,
                            "task_status": task.status,
                            "at": datetime.utcnow().isoformat(),
                        },
                    ],
                },
            )
            await self._store.save_project(current)

            if project_status != "running":
                return current

        completed = current.model_copy(
            update={
                "status": "completed",
                "audit_events": [
                    *current.audit_events,
                    {"role": "orchestrator", "event": "project_completed", "at": datetime.utcnow().isoformat()},
                ],
            },
        )
        await self._store.save_project(completed)
        return completed

    async def _advance_project_after_task(self, project_id: str, task_id: str, task_status: str) -> ProjectView | None:
        project = await self.get_project(project_id)
        if project is None:
            return None

        planned_tasks = list(project.planned_tasks)
        changed = False
        for idx, item in enumerate(planned_tasks):
            if item.task_id != task_id:
                continue
            mapped_status = self._project_status_for_task(task_status)
            planned_tasks[idx] = item.model_copy(update={"status": mapped_status})
            changed = True
            break

        if not changed:
            return project

        next_project = project.model_copy(update={"planned_tasks": planned_tasks})
        if task_status == "completed":
            await self._store.save_project(next_project)
            return await self._run_project(project_id)

        if task_status in {"waiting_for_approval", "waiting_for_plan_approval"}:
            next_project = next_project.model_copy(update={"status": "waiting_for_approval"})
        elif task_status == "rejected":
            next_project = next_project.model_copy(update={"status": "blocked"})
        else:
            next_project = next_project.model_copy(update={"status": "running"})
        await self._store.save_project(next_project)
        return next_project

    async def _mark_project_blocked(self, project_id: str, task_id: str, task_status: str) -> None:
        await self._advance_project_after_task(project_id, task_id, task_status)

    @staticmethod
    def _project_status_for_task(task_status: str) -> str:
        if task_status == "completed":
            return "completed"
        if task_status in {"waiting_for_approval", "waiting_for_plan_approval"}:
            return task_status
        if task_status == "rejected":
            return "rejected"
        if task_status in {"created", "planned", "worked", "reviewed", "advised", "policy_evaluated", "approved"}:
            return "running"
        return "planned"
