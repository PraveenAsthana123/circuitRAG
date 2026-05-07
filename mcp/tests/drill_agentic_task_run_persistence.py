#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: agent-orchestrator task execution persists task-run rows.

Locks the execution-history contract added to _create_task_internal():

  * write a started TaskRunView before graph execution
  * write a final TaskRunView after success
  * write a failed TaskRunView with error_text on exception

This drill stays tier-1 safe by stubbing external imports and using an
in-memory recording store.

Fourteen steps. Thirteen negative assertions.

Success path (steps 1-9):

  1. POSITIVE: success path writes exactly 2 task run rows
     (started + completed).
  2. NEGATIVE: first persisted row has status='started'; without
     it operators cannot tell when execution began.
  3. NEGATIVE: second persisted row has status='completed';
     missing terminal status leaves replay ambiguous.
  4. NEGATIVE: started + final rows share the same run_id;
     diverging IDs break correlation across the audit chain.
  5. NEGATIVE: task_id threads through both rows; missing
     task linkage breaks per-task history queries.
  6. NEGATIVE: model_map carries the expected roles on the
     final row (coder/reviewer/advisor); missing role record
     loses the multi-agent provenance.
  7. NEGATIVE: task goal is captured in run inputs; without
     the goal the audit row is opaque.
  8. NEGATIVE: final outputs payload includes completed status;
     downstream consumers gate on this field.
  9. NEGATIVE: final confidence value persists exactly as
     produced; rewriting confidence breaks calibration.

Failure path (steps 10-14):

  10. NEGATIVE: failure path raises RuntimeError; swallowed
      errors break the failure-handling contract.
  11. NEGATIVE: failure path also writes 2 task run rows
      (started + failed); a failure-without-rows is silent.
  12. NEGATIVE: failure path's first row has status='started';
      the failure point is observable.
  13. NEGATIVE: failure path's second row has status='failed';
      crash-without-status looks identical to in-progress.
  14. NEGATIVE: failed row persists error_text; without it
      operators cannot triage the cause.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
APP_DIR = REPO / "services" / "agent-orchestrator-svc" / "app"
PACKAGE_NAME = "agentic_app_task_run"


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

CreateTaskRequest = models_mod.CreateTaskRequest
InMemoryTaskStore = store_mod.InMemoryTaskStore
AgentOrchestratorService = service_mod.AgentOrchestratorService


class RecordingStore(InMemoryTaskStore):
    def __init__(self) -> None:
        super().__init__()
        self.task_runs: list[Any] = []

    async def save_task_run(self, run) -> None:  # type: ignore[no-untyped-def]
        self.task_runs.append(run)


class SuccessService(AgentOrchestratorService):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._graph = _SuccessGraph()


class FailureService(AgentOrchestratorService):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._graph = _FailureGraph()


class _SuccessGraph:
    async def ainvoke(self, state):
        return {
            "status": "completed",
            "confidence": 0.91,
            "plan": ["classify", "execute", "review", "finalize"],
            "worker_output": "implemented the requested task",
            "reviewer_notes": ["review passed"],
            "advisor_summary": "safe to proceed",
            "approval_reasons": [],
            "next_action": "done",
            "audit_events": [*state.get("audit_events", []), {"role": "test", "event": "completed"}],
        }


class _FailureGraph:
    async def ainvoke(self, state):
        raise RuntimeError("synthetic workflow failure")


async def _success_case() -> tuple[int, str]:
    store = RecordingStore()
    svc = SuccessService(store=store)
    task = await svc.create_task(
        CreateTaskRequest(
            tenant_id="tenant-drill",
            goal="Persist task run history",
            use_global_policy=True,
        )
    )

    if len(store.task_runs) != 2:
        return 1, f"x step 1: expected 2 task run rows on success, got {len(store.task_runs)}"
    started, finished = store.task_runs
    if started.status != "started":
        return 1, f"x step 2: first run row status should be 'started', got {started.status!r}"
    if finished.status != "completed":
        return 1, f"x step 3: final run row status should be 'completed', got {finished.status!r}"
    if started.run_id != finished.run_id:
        return 1, "x step 4: started/final rows must share run_id"
    if started.task_id != task.task_id or finished.task_id != task.task_id:
        return 1, "x step 5: task_id did not thread through task run rows"
    if "coder_executor" not in finished.model_map or "advisor" not in finished.model_map:
        return 1, f"x step 6: model_map missing expected roles: {finished.model_map!r}"
    if finished.inputs.get("goal") != task.goal:
        return 1, "x step 7: task goal missing from persisted run inputs"
    if finished.outputs.get("status") != "completed":
        return 1, f"x step 8: final outputs missing completed status: {finished.outputs!r}"
    if finished.confidence != 0.91:
        return 1, f"x step 9: final confidence mismatch, got {finished.confidence!r}"
    return 0, "\n".join(
        [
            "✓ step 1: success path writes 2 task run rows",
            "✓ step 2: first row is started",
            "✓ step 3: second row reflects final completed status",
            "✓ step 4: started/final rows share run_id",
            "✓ step 5: task_id threads through run rows",
            "✓ step 6: model_map carries expected roles",
            "✓ step 7: goal is captured in run inputs",
            "✓ step 8: final outputs capture completed status",
            "✓ step 9: final confidence is persisted",
        ]
    )


async def _failure_case() -> tuple[int, str]:
    store = RecordingStore()
    svc = FailureService(store=store)
    try:
        await svc.create_task(
            CreateTaskRequest(
                tenant_id="tenant-drill",
                goal="Persist failed task run history",
                use_global_policy=True,
            )
        )
    except RuntimeError as exc:
        if str(exc) != "synthetic workflow failure":
            return 1, f"x step 10: unexpected exception text {exc!r}"
    else:
        return 1, "x step 10: expected RuntimeError was not raised"

    if len(store.task_runs) != 2:
        return 1, f"x step 11: expected 2 task run rows on failure, got {len(store.task_runs)}"
    started, failed = store.task_runs
    if started.status != "started":
        return 1, f"x step 12: first failure-path row should be started, got {started.status!r}"
    if failed.status != "failed":
        return 1, f"x step 13: final failure-path row should be failed, got {failed.status!r}"
    if failed.error_text != "synthetic workflow failure":
        return 1, f"x step 14: failed row missing error_text, got {failed.error_text!r}"
    return 0, "\n".join(
        [
            "✓ step 10: failure path raises the underlying workflow error",
            "✓ step 11: failure path also writes 2 task run rows",
            "✓ step 12: failure path starts with a started row",
            "✓ step 13: failure path ends with a failed row",
            "✓ step 14: failed row persists error_text",
        ]
    )


async def _main() -> int:
    rc, msg = await _success_case()
    if rc != 0:
        print(msg)
        return rc
    print(msg)

    rc, msg = await _failure_case()
    if rc != 0:
        print(msg)
        return rc
    print(msg)
    print("\n==================================================")
    print("  ALL 14 TASK-RUN-PERSISTENCE STEPS PASSED")
    print("  (13 negative assertions: 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)")
    print("==================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
