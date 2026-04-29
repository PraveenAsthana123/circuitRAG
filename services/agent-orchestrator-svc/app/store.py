from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from .models import (
    AgenticPolicyView,
    ApprovalView,
    MemoryRecordView,
    ProjectPlanItemView,
    ProjectView,
    TaskRunView,
    TaskView,
)


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._items: dict[str, TaskView] = {}
        self._projects: dict[str, ProjectView] = {}
        self._project_plan_items: dict[str, list[ProjectPlanItemView]] = {}
        self._task_runs: dict[str, list[TaskRunView]] = {}
        self._approvals: dict[str, list[ApprovalView]] = {}
        self._memories: dict[tuple[str, str], list[MemoryRecordView]] = {}
        self._policy = AgenticPolicyView()
        self._lock = asyncio.Lock()

    async def save(self, task: TaskView) -> None:
        async with self._lock:
            self._items[task.task_id] = task

    async def get(self, task_id: str) -> TaskView | None:
        async with self._lock:
            return self._items.get(task_id)

    async def patch(self, task_id: str, **updates: Any) -> TaskView | None:
        async with self._lock:
            current = self._items.get(task_id)
            if current is None:
                return None
            updated = current.model_copy(update=updates)
            self._items[task_id] = updated
            return updated

    async def list_recent(self, limit: int = 20) -> list[TaskView]:
        async with self._lock:
            rows = list(self._items.values())
        rows.sort(
            key=lambda item: next(
                (
                    event.get("at", "")
                    for event in reversed(item.audit_events)
                    if isinstance(event, dict)
                ),
                "",
            ),
            reverse=True,
        )
        return rows[:limit]

    async def get_policy(self) -> AgenticPolicyView:
        async with self._lock:
            return self._policy.model_copy()

    async def save_policy(self, policy: AgenticPolicyView) -> AgenticPolicyView:
        async with self._lock:
            stamped = policy.model_copy(
                update={"updated_at": datetime.utcnow().isoformat()},
            )
            self._policy = stamped
            return stamped.model_copy()

    async def save_project(self, project: ProjectView) -> None:
        async with self._lock:
            self._projects[project.project_id] = project

    async def get_project(self, project_id: str) -> ProjectView | None:
        async with self._lock:
            return self._projects.get(project_id)

    async def list_projects(self, limit: int = 20) -> list[ProjectView]:
        async with self._lock:
            rows = list(self._projects.values())
        rows.sort(
            key=lambda item: next(
                (
                    event.get("at", "")
                    for event in reversed(item.audit_events)
                    if isinstance(event, dict)
                ),
                "",
            ),
            reverse=True,
        )
        return rows[:limit]

    async def save_project_plan_item(self, item: ProjectPlanItemView) -> None:
        async with self._lock:
            rows = list(self._project_plan_items.get(item.project_id, []))
            rows = [row for row in rows if row.plan_item_id != item.plan_item_id]
            rows.append(item)
            rows.sort(key=lambda row: row.sort_index)
            self._project_plan_items[item.project_id] = rows

    async def list_project_plan_items(self, project_id: str) -> list[ProjectPlanItemView]:
        async with self._lock:
            return list(self._project_plan_items.get(project_id, []))

    async def save_task_run(self, run: TaskRunView) -> None:
        async with self._lock:
            rows = list(self._task_runs.get(run.task_id, []))
            rows.append(run)
            self._task_runs[run.task_id] = rows

    async def list_task_runs(self, task_id: str) -> list[TaskRunView]:
        async with self._lock:
            return list(self._task_runs.get(task_id, []))

    async def save_approval(self, approval: ApprovalView) -> None:
        async with self._lock:
            rows = list(self._approvals.get(approval.task_id, []))
            rows.append(approval)
            self._approvals[approval.task_id] = rows

    async def list_approvals(self, task_id: str) -> list[ApprovalView]:
        async with self._lock:
            return list(self._approvals.get(task_id, []))

    async def save_memory(self, memory: MemoryRecordView) -> None:
        async with self._lock:
            key = (memory.scope_type, memory.scope_id)
            rows = list(self._memories.get(key, []))
            rows.append(memory)
            self._memories[key] = rows

    async def list_memories(self, scope_type: str, scope_id: str) -> list[MemoryRecordView]:
        async with self._lock:
            return list(self._memories.get((scope_type, scope_id), []))
