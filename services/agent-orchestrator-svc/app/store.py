from __future__ import annotations

import asyncio
from collections import OrderedDict
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


# P0 #35: bound the InMemory fallback to prevent OOM in long-running
# dev sessions. OrderedDict + LRU eviction. The fallback is documented
# as dev-only / Postgres-unavailable, but a leaky dev process is
# still a real footgun. Default 1000 tasks; override via constructor.
_DEFAULT_MAX_TASKS = 1000
_DEFAULT_MAX_RUNS_PER_TASK = 100
_DEFAULT_MAX_PROJECTS = 500
_DEFAULT_MAX_MEMORIES_PER_SCOPE = 200


class InMemoryTaskStore:
    def __init__(
        self,
        *,
        max_tasks: int = _DEFAULT_MAX_TASKS,
        max_runs_per_task: int = _DEFAULT_MAX_RUNS_PER_TASK,
        max_projects: int = _DEFAULT_MAX_PROJECTS,
        max_memories_per_scope: int = _DEFAULT_MAX_MEMORIES_PER_SCOPE,
    ) -> None:
        # Use OrderedDict so we can evict LRU when over cap.
        self._items: OrderedDict[str, TaskView] = OrderedDict()
        self._projects: OrderedDict[str, ProjectView] = OrderedDict()
        self._project_plan_items: dict[str, list[ProjectPlanItemView]] = {}
        self._task_runs: dict[str, list[TaskRunView]] = {}
        self._approvals: dict[str, list[ApprovalView]] = {}
        self._memories: dict[tuple[str, str], list[MemoryRecordView]] = {}
        self._policy = AgenticPolicyView()
        self._lock = asyncio.Lock()
        self.max_tasks = max(1, max_tasks)
        self.max_runs_per_task = max(1, max_runs_per_task)
        self.max_projects = max(1, max_projects)
        self.max_memories_per_scope = max(1, max_memories_per_scope)

    def _evict_if_over(self, od: OrderedDict[str, Any], cap: int) -> None:
        """LRU eviction when an OrderedDict exceeds cap. Removes oldest
        entries (popitem(last=False)) until size <= cap. Called inside
        the lock by callers."""
        while len(od) > cap:
            od.popitem(last=False)

    async def save(self, task: TaskView) -> None:
        async with self._lock:
            # Move-to-end on update so recently-accessed tasks aren't evicted.
            if task.task_id in self._items:
                del self._items[task.task_id]
            self._items[task.task_id] = task
            self._evict_if_over(self._items, self.max_tasks)

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
            if project.project_id in self._projects:
                del self._projects[project.project_id]
            self._projects[project.project_id] = project
            self._evict_if_over(self._projects, self.max_projects)

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
            # P0 #35: bound per-task run history.
            if len(rows) > self.max_runs_per_task:
                rows = rows[-self.max_runs_per_task:]
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
            # P0 #35: bound per-scope memories.
            if len(rows) > self.max_memories_per_scope:
                rows = rows[-self.max_memories_per_scope:]
            self._memories[key] = rows

    async def list_memories(self, scope_type: str, scope_id: str) -> list[MemoryRecordView]:
        async with self._lock:
            return list(self._memories.get((scope_type, scope_id), []))
