from __future__ import annotations

import json
from typing import Any

from documind_core.db_client import DbClient

from .models import (
    AgenticPolicyView,
    ApprovalView,
    MemoryRecordView,
    ProjectPlanItem,
    ProjectPlanItemView,
    ProjectView,
    TaskRunView,
    TaskView,
)


class PostgresTaskStore:
    def __init__(self, db: DbClient) -> None:
        self._db = db

    async def save(self, task: TaskView) -> None:
        async with self._db.admin_connection() as conn:
            await conn.execute(
                """
                INSERT INTO orchestration.agent_tasks
                    (task_id, tenant_id, project_id, goal, status, risk_level,
                     require_human_approval, approval_mode, auto_advance,
                     approved, confidence,
                     tool_namespace, tool_name, tool_arguments,
                     plan_json, worker_output, reviewer_notes_json,
                     approval_reasons_json,
                     advisor_summary, next_action, audit_events_json)
                VALUES
                    ($1, $2, $3, $4, $5, $6,
                     $7, $8, $9,
                     $10, $11,
                     $12, $13, $14::jsonb,
                     $15::jsonb, $16, $17::jsonb,
                     $18::jsonb, $19, $20, $21::jsonb)
                ON CONFLICT (task_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    project_id = EXCLUDED.project_id,
                    goal = EXCLUDED.goal,
                    status = EXCLUDED.status,
                    risk_level = EXCLUDED.risk_level,
                    require_human_approval = EXCLUDED.require_human_approval,
                    approval_mode = EXCLUDED.approval_mode,
                    auto_advance = EXCLUDED.auto_advance,
                    approved = EXCLUDED.approved,
                    confidence = EXCLUDED.confidence,
                    tool_namespace = EXCLUDED.tool_namespace,
                    tool_name = EXCLUDED.tool_name,
                    tool_arguments = EXCLUDED.tool_arguments,
                    plan_json = EXCLUDED.plan_json,
                    worker_output = EXCLUDED.worker_output,
                    reviewer_notes_json = EXCLUDED.reviewer_notes_json,
                    approval_reasons_json = EXCLUDED.approval_reasons_json,
                    advisor_summary = EXCLUDED.advisor_summary,
                    next_action = EXCLUDED.next_action,
                    audit_events_json = EXCLUDED.audit_events_json,
                    updated_at = NOW()
                """,
                task.task_id,
                task.tenant_id,
                task.project_id,
                task.goal,
                task.status,
                task.risk_level,
                task.require_human_approval,
                task.approval_mode,
                task.auto_advance,
                task.approved,
                task.confidence,
                task.tool_namespace,
                task.tool_name,
                json.dumps(task.tool_arguments),
                json.dumps(task.plan),
                task.worker_output,
                json.dumps(task.reviewer_notes),
                json.dumps(task.approval_reasons),
                task.advisor_summary,
                task.next_action,
                json.dumps(task.audit_events),
            )

    async def get(self, task_id: str) -> TaskView | None:
        async with self._db.admin_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT task_id, tenant_id, goal, status, risk_level,
                       project_id, require_human_approval, approval_mode, auto_advance,
                       approved, confidence,
                       tool_namespace, tool_name, tool_arguments,
                       plan_json, worker_output, reviewer_notes_json,
                       approval_reasons_json,
                       advisor_summary, next_action, audit_events_json
                  FROM orchestration.agent_tasks
                 WHERE task_id = $1
                """,
                task_id,
            )
        return _row_to_task(row) if row else None

    async def list_recent(self, limit: int = 20) -> list[TaskView]:
        async with self._db.admin_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT task_id, tenant_id, goal, status, risk_level,
                       project_id, require_human_approval, approval_mode, auto_advance,
                       approved, confidence,
                       tool_namespace, tool_name, tool_arguments,
                       plan_json, worker_output, reviewer_notes_json,
                       approval_reasons_json,
                       advisor_summary, next_action, audit_events_json
                  FROM orchestration.agent_tasks
                 ORDER BY updated_at DESC, created_at DESC
                 LIMIT $1
                """,
                limit,
            )
        return [_row_to_task(row) for row in rows]

    async def get_policy(self) -> AgenticPolicyView:
        async with self._db.admin_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT require_human_approval, approval_mode, auto_advance,
                       require_for_high_risk, require_for_low_confidence,
                       confidence_threshold, require_for_risk_flags,
                       require_for_destructive_tools, require_for_tool_namespaces,
                       updated_by, updated_at
                  FROM orchestration.agent_policies
                 WHERE policy_key = 'global'
                """,
            )
            if row is None:
                await conn.execute(
                    """
                    INSERT INTO orchestration.agent_policies
                        (policy_key, require_human_approval, approval_mode, auto_advance)
                    VALUES
                        ('global', FALSE, 'plan_once', TRUE)
                    ON CONFLICT (policy_key) DO NOTHING
                    """,
                )
                row = await conn.fetchrow(
                    """
                    SELECT require_human_approval, approval_mode, auto_advance,
                           require_for_high_risk, require_for_low_confidence,
                           confidence_threshold, require_for_risk_flags,
                           require_for_destructive_tools, require_for_tool_namespaces,
                           updated_by, updated_at
                      FROM orchestration.agent_policies
                     WHERE policy_key = 'global'
                    """,
                )
        return AgenticPolicyView(
            require_human_approval=row["require_human_approval"],
            approval_mode=row["approval_mode"],
            auto_advance=row["auto_advance"],
            require_for_high_risk=row["require_for_high_risk"],
            require_for_low_confidence=row["require_for_low_confidence"],
            confidence_threshold=float(row["confidence_threshold"]),
            require_for_risk_flags=row["require_for_risk_flags"],
            require_for_destructive_tools=row["require_for_destructive_tools"],
            require_for_tool_namespaces=list(row["require_for_tool_namespaces"] or []),
            updated_by=row["updated_by"],
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
        )

    async def save_policy(self, policy: AgenticPolicyView) -> AgenticPolicyView:
        async with self._db.admin_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO orchestration.agent_policies
                    (policy_key, require_human_approval, approval_mode, auto_advance,
                     require_for_high_risk, require_for_low_confidence, confidence_threshold,
                     require_for_risk_flags, require_for_destructive_tools, require_for_tool_namespaces,
                     updated_by)
                VALUES
                    ('global', $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10)
                ON CONFLICT (policy_key) DO UPDATE SET
                    require_human_approval = EXCLUDED.require_human_approval,
                    approval_mode = EXCLUDED.approval_mode,
                    auto_advance = EXCLUDED.auto_advance,
                    require_for_high_risk = EXCLUDED.require_for_high_risk,
                    require_for_low_confidence = EXCLUDED.require_for_low_confidence,
                    confidence_threshold = EXCLUDED.confidence_threshold,
                    require_for_risk_flags = EXCLUDED.require_for_risk_flags,
                    require_for_destructive_tools = EXCLUDED.require_for_destructive_tools,
                    require_for_tool_namespaces = EXCLUDED.require_for_tool_namespaces,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
                RETURNING require_human_approval, approval_mode, auto_advance,
                          require_for_high_risk, require_for_low_confidence, confidence_threshold,
                          require_for_risk_flags, require_for_destructive_tools, require_for_tool_namespaces,
                          updated_by, updated_at
                """,
                policy.require_human_approval,
                policy.approval_mode,
                policy.auto_advance,
                policy.require_for_high_risk,
                policy.require_for_low_confidence,
                policy.confidence_threshold,
                policy.require_for_risk_flags,
                policy.require_for_destructive_tools,
                json.dumps(policy.require_for_tool_namespaces),
                policy.updated_by,
            )
        return AgenticPolicyView(
            require_human_approval=row["require_human_approval"],
            approval_mode=row["approval_mode"],
            auto_advance=row["auto_advance"],
            require_for_high_risk=row["require_for_high_risk"],
            require_for_low_confidence=row["require_for_low_confidence"],
            confidence_threshold=float(row["confidence_threshold"]),
            require_for_risk_flags=row["require_for_risk_flags"],
            require_for_destructive_tools=row["require_for_destructive_tools"],
            require_for_tool_namespaces=list(row["require_for_tool_namespaces"] or []),
            updated_by=row["updated_by"],
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
        )

    async def save_project(self, project: ProjectView) -> None:
        async with self._db.admin_connection() as conn:
            await conn.execute(
                """
                INSERT INTO orchestration.agent_projects
                    (project_id, tenant_id, name, goal, status,
                     use_global_policy, task_ids_json, planned_tasks_json, policy_override_json, audit_events_json)
                VALUES
                    ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9::jsonb, $10::jsonb)
                ON CONFLICT (project_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    name = EXCLUDED.name,
                    goal = EXCLUDED.goal,
                    status = EXCLUDED.status,
                    use_global_policy = EXCLUDED.use_global_policy,
                    task_ids_json = EXCLUDED.task_ids_json,
                    planned_tasks_json = EXCLUDED.planned_tasks_json,
                    policy_override_json = EXCLUDED.policy_override_json,
                    audit_events_json = EXCLUDED.audit_events_json,
                    updated_at = NOW()
                """,
                project.project_id,
                project.tenant_id,
                project.name,
                project.goal,
                project.status,
                project.use_global_policy,
                json.dumps(project.task_ids),
                json.dumps([item.model_dump() for item in project.planned_tasks]),
                json.dumps(project.policy_override.model_dump() if project.policy_override else None),
                json.dumps(project.audit_events),
            )

    async def get_project(self, project_id: str) -> ProjectView | None:
        async with self._db.admin_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT project_id, tenant_id, name, goal, status,
                       use_global_policy, task_ids_json, planned_tasks_json, policy_override_json, audit_events_json
                  FROM orchestration.agent_projects
                 WHERE project_id = $1
                """,
                project_id,
            )
        return _row_to_project(row) if row else None

    async def list_projects(self, limit: int = 20) -> list[ProjectView]:
        async with self._db.admin_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT project_id, tenant_id, name, goal, status,
                       use_global_policy, task_ids_json, planned_tasks_json, policy_override_json, audit_events_json
                  FROM orchestration.agent_projects
                 ORDER BY updated_at DESC, created_at DESC
                 LIMIT $1
                """,
                limit,
            )
        return [_row_to_project(row) for row in rows]

    async def save_project_plan_item(self, item: ProjectPlanItemView) -> None:
        async with self._db.admin_connection() as conn:
            await conn.execute(
                """
                INSERT INTO orchestration.agent_project_plan_items
                    (plan_item_id, tenant_id, project_id, title, objective, status,
                     risk_level, owner_role, depends_on_json, acceptance_checks_json,
                     scope_paths_json, task_id, sort_index)
                VALUES
                    ($1, $2, $3, $4, $5, $6,
                     $7, $8, $9::jsonb, $10::jsonb,
                     $11::jsonb, $12, $13)
                ON CONFLICT (plan_item_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    project_id = EXCLUDED.project_id,
                    title = EXCLUDED.title,
                    objective = EXCLUDED.objective,
                    status = EXCLUDED.status,
                    risk_level = EXCLUDED.risk_level,
                    owner_role = EXCLUDED.owner_role,
                    depends_on_json = EXCLUDED.depends_on_json,
                    acceptance_checks_json = EXCLUDED.acceptance_checks_json,
                    scope_paths_json = EXCLUDED.scope_paths_json,
                    task_id = EXCLUDED.task_id,
                    sort_index = EXCLUDED.sort_index,
                    updated_at = NOW()
                """,
                item.plan_item_id,
                item.tenant_id,
                item.project_id,
                item.title,
                item.objective,
                item.status,
                item.risk_level,
                item.owner_role,
                json.dumps(item.depends_on),
                json.dumps(item.acceptance_checks),
                json.dumps(item.scope_paths),
                item.task_id,
                item.sort_index,
            )

    async def list_project_plan_items(self, project_id: str) -> list[ProjectPlanItemView]:
        async with self._db.admin_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT plan_item_id, tenant_id, project_id, title, objective, status,
                       risk_level, owner_role, depends_on_json, acceptance_checks_json,
                       scope_paths_json, task_id, sort_index, created_at, updated_at
                  FROM orchestration.agent_project_plan_items
                 WHERE project_id = $1
                 ORDER BY sort_index ASC, created_at ASC
                """,
                project_id,
            )
        return [_row_to_project_plan_item(row) for row in rows]

    async def save_task_run(self, run: TaskRunView) -> None:
        async with self._db.admin_connection() as conn:
            await conn.execute(
                """
                INSERT INTO orchestration.agent_task_runs
                    (run_id, tenant_id, task_id, project_id, phase, status,
                     model_map_json, inputs_json, outputs_json,
                     confidence, risk_level, duration_ms, error_text,
                     tokens_in, tokens_out, cost_usd_cents, routing_decision)
                VALUES
                    ($1, $2, $3, $4, $5, $6,
                     $7::jsonb, $8::jsonb, $9::jsonb,
                     $10, $11, $12, $13,
                     $14, $15, $16, $17::jsonb)
                ON CONFLICT (run_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    task_id = EXCLUDED.task_id,
                    project_id = EXCLUDED.project_id,
                    phase = EXCLUDED.phase,
                    status = EXCLUDED.status,
                    model_map_json = EXCLUDED.model_map_json,
                    inputs_json = EXCLUDED.inputs_json,
                    outputs_json = EXCLUDED.outputs_json,
                    confidence = EXCLUDED.confidence,
                    risk_level = EXCLUDED.risk_level,
                    duration_ms = EXCLUDED.duration_ms,
                    error_text = EXCLUDED.error_text,
                    tokens_in = EXCLUDED.tokens_in,
                    tokens_out = EXCLUDED.tokens_out,
                    cost_usd_cents = EXCLUDED.cost_usd_cents,
                    routing_decision = EXCLUDED.routing_decision
                """,
                run.run_id,
                run.tenant_id,
                run.task_id,
                run.project_id,
                run.phase,
                run.status,
                json.dumps(run.model_map),
                json.dumps(run.inputs),
                json.dumps(run.outputs),
                run.confidence,
                run.risk_level,
                run.duration_ms,
                run.error_text,
                run.tokens_in,
                run.tokens_out,
                run.cost_usd_cents,
                json.dumps(run.routing_decision) if run.routing_decision is not None else None,
            )

    async def list_task_runs(self, task_id: str) -> list[TaskRunView]:
        async with self._db.admin_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT run_id, tenant_id, task_id, project_id, phase, status,
                       model_map_json, inputs_json, outputs_json,
                       confidence, risk_level, duration_ms, error_text, created_at,
                       tokens_in, tokens_out, cost_usd_cents, routing_decision
                  FROM orchestration.agent_task_runs
                 WHERE task_id = $1
                 ORDER BY created_at DESC
                """,
                task_id,
            )
        return [_row_to_task_run(row) for row in rows]

    async def save_approval(self, approval: ApprovalView) -> None:
        async with self._db.admin_connection() as conn:
            await conn.execute(
                """
                INSERT INTO orchestration.agent_approvals
                    (approval_id, tenant_id, task_id, project_id, actor_id, decision,
                     reason, reason_codes_json, snapshot_json)
                VALUES
                    ($1, $2, $3, $4, $5, $6,
                     $7, $8::jsonb, $9::jsonb)
                ON CONFLICT (approval_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    task_id = EXCLUDED.task_id,
                    project_id = EXCLUDED.project_id,
                    actor_id = EXCLUDED.actor_id,
                    decision = EXCLUDED.decision,
                    reason = EXCLUDED.reason,
                    reason_codes_json = EXCLUDED.reason_codes_json,
                    snapshot_json = EXCLUDED.snapshot_json
                """,
                approval.approval_id,
                approval.tenant_id,
                approval.task_id,
                approval.project_id,
                approval.actor_id,
                approval.decision,
                approval.reason,
                json.dumps(approval.reason_codes),
                json.dumps(approval.snapshot),
            )

    async def list_approvals(self, task_id: str) -> list[ApprovalView]:
        async with self._db.admin_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT approval_id, tenant_id, task_id, project_id, actor_id, decision,
                       reason, reason_codes_json, snapshot_json, created_at
                  FROM orchestration.agent_approvals
                 WHERE task_id = $1
                 ORDER BY created_at DESC
                """,
                task_id,
            )
        return [_row_to_approval(row) for row in rows]

    async def save_memory(self, memory: MemoryRecordView) -> None:
        async with self._db.admin_connection() as conn:
            await conn.execute(
                """
                INSERT INTO orchestration.agent_memories
                    (memory_id, tenant_id, scope_type, scope_id, memory_kind,
                     source_type, source_id, summary, payload_json)
                VALUES
                    ($1, $2, $3, $4, $5,
                     $6, $7, $8, $9::jsonb)
                ON CONFLICT (memory_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    scope_type = EXCLUDED.scope_type,
                    scope_id = EXCLUDED.scope_id,
                    memory_kind = EXCLUDED.memory_kind,
                    source_type = EXCLUDED.source_type,
                    source_id = EXCLUDED.source_id,
                    summary = EXCLUDED.summary,
                    payload_json = EXCLUDED.payload_json
                """,
                memory.memory_id,
                memory.tenant_id,
                memory.scope_type,
                memory.scope_id,
                memory.memory_kind,
                memory.source_type,
                memory.source_id,
                memory.summary,
                json.dumps(memory.payload),
            )

    async def list_memories(self, scope_type: str, scope_id: str) -> list[MemoryRecordView]:
        async with self._db.admin_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT memory_id, tenant_id, scope_type, scope_id, memory_kind,
                       source_type, source_id, summary, payload_json, created_at
                  FROM orchestration.agent_memories
                 WHERE scope_type = $1 AND scope_id = $2
                 ORDER BY created_at DESC
                """,
                scope_type,
                scope_id,
            )
        return [_row_to_memory(row) for row in rows]


def _row_to_task(row: Any) -> TaskView:
    return TaskView(
        task_id=row["task_id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        goal=row["goal"],
        status=row["status"],
        risk_level=row["risk_level"],
        require_human_approval=row["require_human_approval"],
        approval_mode=row["approval_mode"],
        auto_advance=row["auto_advance"],
        approved=row["approved"],
        confidence=row["confidence"],
        tool_namespace=row["tool_namespace"],
        tool_name=row["tool_name"],
        tool_arguments=dict(row["tool_arguments"] or {}),
        plan=list(row["plan_json"] or []),
        worker_output=row["worker_output"],
        reviewer_notes=list(row["reviewer_notes_json"] or []),
        approval_reasons=list(row["approval_reasons_json"] or []),
        advisor_summary=row["advisor_summary"],
        next_action=row["next_action"],
        audit_events=list(row["audit_events_json"] or []),
    )


def _row_to_project(row: Any) -> ProjectView:
    override = row["policy_override_json"]
    return ProjectView(
        project_id=row["project_id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        goal=row["goal"],
        status=row["status"],
        use_global_policy=row["use_global_policy"],
        task_ids=list(row["task_ids_json"] or []),
        planned_tasks=[ProjectPlanItem.model_validate(item) for item in list(row["planned_tasks_json"] or [])],
        policy_override=AgenticPolicyView.model_validate(dict(override)) if override else None,
        audit_events=list(row["audit_events_json"] or []),
    )


def _row_to_project_plan_item(row: Any) -> ProjectPlanItemView:
    return ProjectPlanItemView(
        plan_item_id=row["plan_item_id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        title=row["title"],
        objective=row["objective"],
        status=row["status"],
        risk_level=row["risk_level"],
        owner_role=row["owner_role"],
        depends_on=list(row["depends_on_json"] or []),
        acceptance_checks=list(row["acceptance_checks_json"] or []),
        scope_paths=list(row["scope_paths_json"] or []),
        task_id=row["task_id"],
        sort_index=row["sort_index"],
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
        updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
    )


def _row_to_task_run(row: Any) -> TaskRunView:
    # Backward compat: A5 added 4 columns. Old rows return them as None;
    # row.get(col) without default would KeyError on asyncpg.Record.
    # asyncpg.Record supports __getitem__ but not .get with default — use try.
    def _maybe(col: str):
        try:
            return row[col]
        except (KeyError, IndexError):
            return None

    routing = _maybe("routing_decision")
    return TaskRunView(
        run_id=row["run_id"],
        tenant_id=row["tenant_id"],
        task_id=row["task_id"],
        project_id=row["project_id"],
        phase=row["phase"],
        status=row["status"],
        model_map=dict(row["model_map_json"] or {}),
        inputs=dict(row["inputs_json"] or {}),
        outputs=dict(row["outputs_json"] or {}),
        confidence=row["confidence"],
        risk_level=row["risk_level"],
        duration_ms=row["duration_ms"],
        error_text=row["error_text"],
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
        tokens_in=_maybe("tokens_in"),
        tokens_out=_maybe("tokens_out"),
        cost_usd_cents=_maybe("cost_usd_cents"),
        routing_decision=dict(routing) if routing else None,
    )


def _row_to_approval(row: Any) -> ApprovalView:
    return ApprovalView(
        approval_id=row["approval_id"],
        tenant_id=row["tenant_id"],
        task_id=row["task_id"],
        project_id=row["project_id"],
        actor_id=row["actor_id"],
        decision=row["decision"],
        reason=row["reason"],
        reason_codes=list(row["reason_codes_json"] or []),
        snapshot=dict(row["snapshot_json"] or {}),
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
    )


def _row_to_memory(row: Any) -> MemoryRecordView:
    return MemoryRecordView(
        memory_id=row["memory_id"],
        tenant_id=row["tenant_id"],
        scope_type=row["scope_type"],
        scope_id=row["scope_id"],
        memory_kind=row["memory_kind"],
        source_type=row["source_type"],
        source_id=row["source_id"],
        summary=row["summary"],
        payload=dict(row["payload_json"] or {}),
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
    )
