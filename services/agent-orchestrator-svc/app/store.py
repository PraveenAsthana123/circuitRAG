from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from .models import AgenticPolicyView, ProjectView, TaskView


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._items: dict[str, TaskView] = {}
        self._projects: dict[str, ProjectView] = {}
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
