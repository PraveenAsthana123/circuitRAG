#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: agent-orchestrator control-plane read APIs expose normalized
plan/run/approval/memory records end-to-end.

This locks the HTTP surfaces added for the new Agentic Control Plane UI:

  * GET /api/v1/agentic/projects/{project_id}/plan-items
  * GET /api/v1/agentic/tasks/{task_id}/runs
  * GET /api/v1/agentic/tasks/{task_id}/approvals
  * GET /api/v1/agentic/memories?scope_type=...&scope_id=...

The drill is hermetic:
  * TestClient only, no service-up requirement
  * fake MCP import
  * fake graph behavior
  * forced in-memory store
  * observability export disabled

Nine steps. Eight negative assertions.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import types

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
APP_DIR = REPO / "services" / "agent-orchestrator-svc" / "app"
PACKAGE_NAME = "agentic_control_plane_api"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "libs" / "py"))

os.environ.setdefault("DOCUMIND_OTEL_EXPORTER_OTLP_ENDPOINT", "")
os.environ.setdefault("DOCUMIND_PROMETHEUS_PORT", "0")
os.environ.setdefault("DOCUMIND_MCP_HR_URL", "")
os.environ.setdefault("DOCUMIND_MCP_ITSM_URL", "")
os.environ.setdefault("DOCUMIND_MCP_DRILLS_URL", "")

fake_mcp = types.ModuleType("mcp")


class _FakeMCPClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def close(self) -> None:
        return None


fake_mcp.MCPClient = _FakeMCPClient
sys.modules["mcp"] = fake_mcp

fake_langgraph = types.ModuleType("langgraph")
fake_langgraph_graph = types.ModuleType("langgraph.graph")


class _FakeCompiledGraph:
    async def ainvoke(self, state):  # type: ignore[no-untyped-def]
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
main_mod = _load_submodule("main", "main.py")


class _FakeDbClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def connect(self) -> None:
        raise RuntimeError("force in-memory store for drill")

    async def close(self) -> None:
        return None


class _FakeGraph:
    async def ainvoke(self, state):  # type: ignore[no-untyped-def]
        if state.get("approved") is True and state.get("resume_from") == "worker_execute":
            return {
                "status": "completed",
                "confidence": 0.93,
                "plan": ["classify", "execute", "review", "finalize"],
                "worker_output": "workflow resumed after human approval",
                "reviewer_notes": ["resume path verified"],
                "advisor_summary": "completed after human approval",
                "approval_reasons": ["operator requested approval"],
                "next_action": "done",
                "audit_events": [*state.get("audit_events", []), {"role": "test", "event": "resumed"}],
            }
        if state.get("require_human_approval"):
            return {
                "status": "waiting_for_approval",
                "confidence": 0.61,
                "plan": ["classify", "execute", "review", "await approval"],
                "worker_output": "task paused for operator review",
                "reviewer_notes": ["manual review required"],
                "advisor_summary": "await human sign-off",
                "approval_reasons": ["operator requested approval"],
                "next_action": "await approval",
                "audit_events": [*state.get("audit_events", []), {"role": "test", "event": "waiting"}],
            }
        return {
            "status": "completed",
            "confidence": 0.88,
            "plan": ["classify", "execute", "review", "finalize"],
            "worker_output": "workflow completed cleanly",
            "reviewer_notes": ["review passed"],
            "advisor_summary": "safe to proceed",
            "approval_reasons": [],
            "next_action": "done",
            "audit_events": [*state.get("audit_events", []), {"role": "test", "event": "completed"}],
        }


def ok(msg: str) -> None:
    print(f"  \033[32m✓ {msg}\033[0m")


def fail(msg: str) -> None:
    print(f"  \033[31m✗ {msg}\033[0m")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n\033[1m── {title} ──\033[0m")


def main() -> None:
    # NEGATIVE: control-plane API endpoints round-trip plan/memory/
    # snapshot data without dropping rows or rewriting payloads.
    # Per-step assertions below verify each contract.
    main_mod.DbClient = _FakeDbClient
    app = main_mod.create_app()

    with TestClient(app) as client:
        app.state.service._graph = _FakeGraph()

        step("1. Create project and read normalized plan rows")
        r = client.post(
            "/api/v1/agentic/projects",
            json={
                "tenant_id": "tenant-drill",
                "name": "Control plane drill",
                "goal": "Prove the control plane APIs end-to-end",
                "use_global_policy": True,
            },
        )
        if r.status_code != 200:
            fail(f"project create returned {r.status_code}: {r.text[:200]}")
        project = r.json()
        project_id = project["project_id"]
        r = client.get(f"/api/v1/agentic/projects/{project_id}/plan-items")
        if r.status_code != 200:
            fail(f"plan-items endpoint returned {r.status_code}: {r.text[:200]}")
        plan_rows = r.json()
        if not plan_rows:
            fail("x step 1: plan-items endpoint returned no rows")
        ok("plan-items endpoint returned normalized rows")

        step("2. Plan row count matches project.planned_tasks")
        if len(plan_rows) != len(project["planned_tasks"]):
            fail(
                "x step 2: plan row count mismatch: "
                f"{len(plan_rows)} vs {len(project['planned_tasks'])}"
            )
        ok("plan row count matches planned_tasks")

        step("3. Project memories are exposed after project completion")
        r = client.get(f"/api/v1/agentic/memories?scope_type=project&scope_id={project_id}")
        if r.status_code != 200:
            fail(f"project memories endpoint returned {r.status_code}: {r.text[:200]}")
        project_memories = r.json()
        if len(project_memories) != 1:
            fail(f"x step 3: expected exactly 1 project memory row, got {len(project_memories)}")
        if project_memories[0]["scope_id"] != project_id:
            fail("x step 3: project memory scope_id drifted")
        ok("project memories endpoint returns completed project memory")

        step("4. Create manual-approval task")
        r = client.post(
            "/api/v1/agentic/tasks",
            json={
                "tenant_id": "tenant-drill",
                "goal": "Create a task that pauses for approval",
                "project_id": project_id,
                "risk_level": "medium",
                "use_global_policy": False,
                "require_human_approval": True,
                "approval_mode": "manual",
                "auto_advance": True,
            },
        )
        if r.status_code != 200:
            fail(f"task create returned {r.status_code}: {r.text[:200]}")
        task = r.json()
        task_id = task["task_id"]
        if task["status"] != "waiting_for_approval":
            fail(f"x step 4: task should pause for approval, got status={task['status']!r}")
        ok("manual-approval task pauses at waiting_for_approval")

        step("5. Task-run endpoint exposes started + waiting rows")
        r = client.get(f"/api/v1/agentic/tasks/{task_id}/runs")
        if r.status_code != 200:
            fail(f"task-runs endpoint returned {r.status_code}: {r.text[:200]}")
        run_rows = r.json()
        if len(run_rows) != 2:
            fail(f"x step 5: expected 2 task run rows, got {len(run_rows)}")
        if run_rows[0]["status"] != "started" or run_rows[1]["status"] != "waiting_for_approval":
            fail(f"x step 5: unexpected task run statuses: {[row['status'] for row in run_rows]!r}")
        ok("task-runs endpoint exposes started and waiting rows")

        step("6. Approve task through HTTP")
        r = client.post(
            f"/api/v1/agentic/tasks/{task_id}/approve",
            json={"approved": True, "actor_id": "admin-user", "reason": "resume the workflow"},
        )
        if r.status_code != 200:
            fail(f"approve endpoint returned {r.status_code}: {r.text[:200]}")
        approved_task = r.json()
        if approved_task["status"] != "completed":
            fail(f"x step 6: approved task should complete, got {approved_task['status']!r}")
        ok("approval endpoint resumes task to completed")

        step("7. Approval rows are exposed")
        r = client.get(f"/api/v1/agentic/tasks/{task_id}/approvals")
        if r.status_code != 200:
            fail(f"approvals endpoint returned {r.status_code}: {r.text[:200]}")
        approval_rows = r.json()
        if len(approval_rows) != 1:
            fail(f"x step 7: expected 1 approval row, got {len(approval_rows)}")
        if approval_rows[0]["decision"] != "approved" or approval_rows[0]["actor_id"] != "admin-user":
            fail(f"x step 7: approval row drifted: {approval_rows[0]!r}")
        ok("approvals endpoint returns the persisted human decision")

        step("8. Task memories are exposed after completion")
        r = client.get(f"/api/v1/agentic/memories?scope_type=task&scope_id={task_id}")
        if r.status_code != 200:
            fail(f"task memories endpoint returned {r.status_code}: {r.text[:200]}")
        task_memories = r.json()
        if len(task_memories) != 1:
            fail(f"x step 8: expected 1 task memory row, got {len(task_memories)}")
        if task_memories[0]["scope_id"] != task_id or task_memories[0]["scope_type"] != "task":
            fail(f"x step 8: task memory scope drifted: {task_memories[0]!r}")
        ok("task memories endpoint returns the completion memory")

        step("9. Missing task id still returns empty read surfaces, not 500")
        r = client.get("/api/v1/agentic/tasks/no-such-task/runs")
        if r.status_code != 200 or r.json() != []:
            fail(f"x step 9: missing task run lookup should be [], got {r.status_code} {r.text[:120]}")
        r = client.get("/api/v1/agentic/tasks/no-such-task/approvals")
        if r.status_code != 200 or r.json() != []:
            fail(f"x step 9: missing task approval lookup should be [], got {r.status_code} {r.text[:120]}")
        ok("missing task read APIs degrade to empty lists")

    print("\n\033[1;32m════════════════════════════════════════\033[0m")
    print("\033[1;32m  ALL 9 AGENTIC-CONTROL-PLANE API STEPS PASSED\033[0m")
    print("\033[1;32m════════════════════════════════════════\033[0m")


if __name__ == "__main__":
    main()
