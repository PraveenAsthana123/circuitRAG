#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: agent-orchestrator project expansion persists normalized plan rows.

Locks the first persistence hop of the advanced agentic workflow:

  create_project()
    -> expands planned_tasks
    -> saves ProjectView
    -> persists ProjectPlanItemView rows via save_project_plan_item()

This drill uses an in-memory recording store so it stays tier-1 safe
and deterministic. It does not require Postgres, Ollama, or MCP.

Eight steps. Seven negative assertions.

  1. POSITIVE: at least one ProjectPlanItemView row is persisted
     after create_project() runs.
  2. NEGATIVE: persisted plan row count matches the count of
     expanded planned_tasks (no drops, no duplicates).
  3. NEGATIVE: plan_item_id format stays deterministic
     ('<project_id>:<step_id>'); drift breaks idempotent reload.
  4. NEGATIVE: every persisted row points at the just-created
     project_id; cross-project leakage would corrupt the plan.
  5. NEGATIVE: tenant_id threads through to all persisted rows;
     missing tenant = RLS bypass.
  6. NEGATIVE: persisted title/objective match the expanded plan
     literally; silent rewrites = lost operator intent.
  7. NEGATIVE: sort_index is sequential (0..N-1); gaps or
     duplicates break ordered replay.
  8. NEGATIVE: owner_role defaults to 'manager' on every row;
     other roles must be explicit, never silent fallback.
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
PACKAGE_NAME = "agentic_app"


fake_mcp = types.ModuleType("mcp")


class _FakeMCPClient:
    def __init__(self, *args, **kwargs) -> None:  # noqa: D401
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
InMemoryTaskStore = store_mod.InMemoryTaskStore
AgentOrchestratorService = service_mod.AgentOrchestratorService


class RecordingStore(InMemoryTaskStore):
    def __init__(self) -> None:
        super().__init__()
        self.plan_rows: list[Any] = []

    async def save_project_plan_item(self, item) -> None:  # type: ignore[no-untyped-def]
        self.plan_rows.append(item)


class DrillService(AgentOrchestratorService):
    async def _run_project(self, project_id: str):  # type: ignore[override]
        return None


async def _main() -> int:
    store = RecordingStore()
    svc = DrillService(store=store)
    project = await svc.create_project(
        CreateProjectRequest(
            tenant_id="tenant-drill",
            name="Agentic persistence drill",
            goal="Build a normalized project plan persistence path",
            use_global_policy=True,
        )
    )

    if not store.plan_rows:
        print("x step 1: no ProjectPlanItemView rows were persisted")
        return 1
    if len(store.plan_rows) != len(project.planned_tasks):
        print(
            "x step 2: persisted plan row count mismatch: "
            f"{len(store.plan_rows)} rows vs {len(project.planned_tasks)} planned tasks"
        )
        return 1

    expected_ids = [f"{project.project_id}:{item.step_id}" for item in project.planned_tasks]
    actual_ids = [row.plan_item_id for row in store.plan_rows]
    if actual_ids != expected_ids:
        print(f"x step 3: plan_item_id drift. expected {expected_ids!r}, got {actual_ids!r}")
        return 1

    bad_project_ids = [row.project_id for row in store.plan_rows if row.project_id != project.project_id]
    if bad_project_ids:
        print(f"x step 4: persisted rows reference wrong project ids: {bad_project_ids!r}")
        return 1

    bad_tenants = [row.tenant_id for row in store.plan_rows if row.tenant_id != project.tenant_id]
    if bad_tenants:
        print(f"x step 5: persisted rows reference wrong tenant ids: {bad_tenants!r}")
        return 1

    mismatched_titles = [
        (row.title, task.title)
        for row, task in zip(store.plan_rows, project.planned_tasks, strict=True)
        if row.title != task.title or row.objective != task.goal
    ]
    if mismatched_titles:
        print(f"x step 6: title/objective mismatch in persisted rows: {mismatched_titles!r}")
        return 1

    sort_indexes = [row.sort_index for row in store.plan_rows]
    if sort_indexes != list(range(len(store.plan_rows))):
        print(f"x step 7: sort_index drift. got {sort_indexes!r}")
        return 1

    non_manager_roles = [row.owner_role for row in store.plan_rows if row.owner_role != "manager"]
    if non_manager_roles:
        print(f"x step 8: unexpected owner_role values: {non_manager_roles!r}")
        return 1

    print("✓ step 1: ProjectPlanItemView rows were persisted")
    print("✓ step 2: row count matches expanded planned_tasks")
    print("✓ step 3: plan_item_id format is stable and deterministic")
    print("✓ step 4: all persisted rows point at the created project")
    print("✓ step 5: tenant id threads through to all persisted rows")
    print("✓ step 6: persisted title/objective match expanded plan")
    print("✓ step 7: sort_index is sequential")
    print("✓ step 8: owner_role defaults to manager")
    print("\n==================================================")
    print("  ALL 8 PROJECT-PLAN-PERSISTENCE STEPS PASSED")
    print("  (7 negative assertions: 2, 3, 4, 5, 6, 7, 8)")
    print("==================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
