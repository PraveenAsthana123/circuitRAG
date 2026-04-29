#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: agent-orchestrator completion paths persist memory rows.

Locks the first memory-writing contract:

  * completed task writes one task-scoped memory row
  * completed project writes one project-scoped memory row
  * summary and payload fields are populated from the completed state

This drill stays tier-1 safe by stubbing external imports and using an
in-memory recording store.

Fifteen steps. Fourteen negative assertions covering both task-
completion and project-completion paths: row count, scope_type,
scope_id, memory_kind, source linkage, summary content, payload
status, and payload identifying field (goal for task, name for
project).
"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from typing import Any
import types

REPO = Path(__file__).resolve().parents[2]
APP_DIR = REPO / "services" / "agent-orchestrator-svc" / "app"
PACKAGE_NAME = "agentic_app_memory"


fake_mcp = types.ModuleType("mcp")


class _FakeMCPClient:
    def __init__(self, *args, **kwargs) -> None:
        pass


fake_mcp.MCPClient = _FakeMCPClient
sys.modules["mcp"] = fake_mcp

fake_langgraph = types.ModuleType("langgraph")
fake_langgraph_graph = types.ModuleType("langgraph.graph")


class _FakeCompiledGraph:
    async def ainvoke(self, state):
        return state


class _FakeStateGraph:
    def __init__(self, _state_type) -> None:
        pass

    def add_node(self, *args, **kwargs) -> None:
        return None

    def set_entry_point(self, *args, **kwargs) -> None:
        return None

    def add_conditional_edges(self, *args, **kwargs) -> None:
        return None

    def add_edge(self, *args, **kwargs) -> None:
        return None

    def compile(self):
        return _FakeCompiledGraph()


fake_langgraph_graph.END = "END"
fake_langgraph_graph.StateGraph = _FakeStateGraph
fake_langgraph.graph = fake_langgraph_graph
sys.modules["langgraph"] = fake_langgraph
sys.modules["langgraph.graph"] = fake_langgraph_graph


def _load_package():
    init_path = APP_DIR / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        init_path,
        submodule_search_locations=[str(APP_DIR)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load package from {init_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_submodule(module_suffix: str, relative_path: str):
    path = APP_DIR / relative_path
    fullname = f"{PACKAGE_NAME}.{module_suffix}"
    spec = importlib.util.spec_from_file_location(fullname, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {fullname} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = mod
    spec.loader.exec_module(mod)
    return mod


_load_package()
models_mod = _load_submodule("models", "models.py")
store_mod = _load_submodule("store", "store.py")
service_mod = _load_submodule("service", "service.py")

CreateProjectRequest = models_mod.CreateProjectRequest
CreateTaskRequest = models_mod.CreateTaskRequest
InMemoryTaskStore = store_mod.InMemoryTaskStore
AgentOrchestratorService = service_mod.AgentOrchestratorService


class RecordingStore(InMemoryTaskStore):
    def __init__(self) -> None:
        super().__init__()
        self.memories: list[Any] = []

    async def save_memory(self, memory) -> None:  # type: ignore[no-untyped-def]
        self.memories.append(memory)


class CompletedTaskService(AgentOrchestratorService):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._graph = _CompletedTaskGraph()


class _CompletedTaskGraph:
    async def ainvoke(self, state):
        return {
            "status": "completed",
            "confidence": 0.93,
            "plan": ["classify", "execute", "review", "finalize"],
            "worker_output": "implemented feature",
            "reviewer_notes": ["review passed"],
            "advisor_summary": "ship it",
            "approval_reasons": [],
            "next_action": "done",
            "audit_events": [*state.get("audit_events", []), {"role": "test", "event": "completed"}],
        }


class CompletedProjectService(AgentOrchestratorService):
    async def _create_task_internal(self, req, *, attach_to_project):  # type: ignore[override]
        task = await super()._create_task_internal(req, attach_to_project=attach_to_project)
        return task.model_copy(update={"status": "completed"})


async def _task_case() -> tuple[int, str]:
    store = RecordingStore()
    svc = CompletedTaskService(store=store)
    task = await svc.create_task(
        CreateTaskRequest(
            tenant_id="tenant-drill",
            goal="Persist task completion memory",
            use_global_policy=True,
        )
    )
    if len(store.memories) != 1:
        return 1, f"x step 1: expected 1 task memory row, got {len(store.memories)}"
    memory = store.memories[0]
    if memory.scope_type != "task":
        return 1, f"x step 2: task memory scope_type mismatch, got {memory.scope_type!r}"
    if memory.scope_id != task.task_id:
        return 1, f"x step 3: task memory scope_id mismatch, got {memory.scope_id!r}"
    if memory.memory_kind != "episodic":
        return 1, f"x step 4: task memory kind mismatch, got {memory.memory_kind!r}"
    if memory.source_type != "task_run" or memory.source_id != task.task_id:
        return 1, "x step 5: task memory source linkage drifted"
    if memory.summary != "ship it":
        return 1, f"x step 6: task memory summary mismatch, got {memory.summary!r}"
    if memory.payload.get("status") != "completed":
        return 1, f"x step 7: task memory payload status mismatch, got {memory.payload!r}"
    if memory.payload.get("goal") != task.goal:
        return 1, "x step 8: task memory payload goal mismatch"
    return 0, "\n".join(
        [
            "✓ step 1: completed task writes exactly 1 memory row",
            "✓ step 2: task memory scope_type is task",
            "✓ step 3: task memory scope_id matches task_id",
            "✓ step 4: task memory kind is episodic",
            "✓ step 5: task memory source linkage is correct",
            "✓ step 6: task memory summary uses advisor summary",
            "✓ step 7: task memory payload captures completed status",
            "✓ step 8: task memory payload captures goal",
        ]
    )


async def _project_case() -> tuple[int, str]:
    store = RecordingStore()
    svc = CompletedProjectService(store=store)
    project = await svc.create_project(
        CreateProjectRequest(
            tenant_id="tenant-drill",
            name="Memory drill project",
            goal="Persist project completion memory",
            use_global_policy=True,
        )
    )
    project_memories = [m for m in store.memories if m.scope_type == "project"]
    if len(project_memories) != 1:
        return 1, f"x step 9: expected 1 project memory row, got {len(project_memories)}"
    memory = project_memories[0]
    if memory.scope_id != project.project_id:
        return 1, f"x step 10: project memory scope_id mismatch, got {memory.scope_id!r}"
    if memory.memory_kind != "project":
        return 1, f"x step 11: project memory kind mismatch, got {memory.memory_kind!r}"
    if memory.source_type != "project" or memory.source_id != project.project_id:
        return 1, "x step 12: project memory source linkage drifted"
    if memory.summary != f"Project completed: {project.name}":
        return 1, f"x step 13: project memory summary mismatch, got {memory.summary!r}"
    if memory.payload.get("status") != "completed":
        return 1, f"x step 14: project memory payload status mismatch, got {memory.payload!r}"
    if memory.payload.get("name") != project.name:
        return 1, "x step 15: project memory payload name mismatch"
    return 0, "\n".join(
        [
            "✓ step 9: completed project writes exactly 1 project memory row",
            "✓ step 10: project memory scope_id matches project_id",
            "✓ step 11: project memory kind is project",
            "✓ step 12: project memory source linkage is correct",
            "✓ step 13: project memory summary uses project name",
            "✓ step 14: project memory payload captures completed status",
            "✓ step 15: project memory payload captures project name",
        ]
    )


async def _main() -> int:
    rc, msg = await _task_case()
    if rc != 0:
        print(msg)
        return rc
    print(msg)

    rc, msg = await _project_case()
    if rc != 0:
        print(msg)
        return rc
    print(msg)
    print("\n==================================================")
    print("  ALL 15 MEMORY-PERSISTENCE STEPS PASSED")
    print("  (14 negative assertions: 2-8, 9-15)")
    print("==================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
