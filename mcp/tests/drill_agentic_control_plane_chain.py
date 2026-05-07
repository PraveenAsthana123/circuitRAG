#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: the normalized agentic control-plane chain is internally
consistent across project creation, task execution, approval, memory
distillation, and the read APIs.

This is the aggregate guardrail on top of the narrower persistence +
API drills. It proves the records agree with each other, not just that
they exist.

Nine steps. Eight negative assertions.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
APP_DIR = REPO / "services" / "agent-orchestrator-svc" / "app"
PACKAGE_NAME = "agentic_control_plane_chain"

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
    # NEGATIVE: control-plane chain endpoints surface composed
    # plan + memory + decision rows without losing parent linkage.
    # Per-step assertions below verify each contract.
    main_mod.DbClient = _FakeDbClient
    app = main_mod.create_app()

    with TestClient(app) as client:
        app.state.service._graph = _FakeGraph()

        step("1. Create project and collect normalized plan rows")
        r = client.post(
            "/api/v1/agentic/projects",
            json={
                "tenant_id": "tenant-drill",
                "name": "Control plane chain drill",
                "goal": "Prove chain consistency across normalized views",
                "use_global_policy": True,
            },
        )
        if r.status_code != 200:
            fail(f"project create returned {r.status_code}: {r.text[:200]}")
        project = r.json()
        project_id = project["project_id"]
        r = client.get(f"/api/v1/agentic/projects/{project_id}/plan-items")
        plan_rows = r.json()
        if len(plan_rows) != len(project["planned_tasks"]):
            fail("x step 1: project planned_tasks and normalized plan rows disagree")
        ok("project planned_tasks and normalized plan rows agree")

        step("2. Plan item ids map back to project + step ordering")
        for idx, row in enumerate(plan_rows):
            expected_id = f"{project_id}:{project['planned_tasks'][idx]['step_id']}"
            if row["plan_item_id"] != expected_id:
                fail(f"x step 2: plan_item_id drift: expected {expected_id!r}, got {row['plan_item_id']!r}")
        ok("plan row ids map back to project and step order")

        step("3. Create manual-approval task attached to the project")
        r = client.post(
            "/api/v1/agentic/tasks",
            json={
                "tenant_id": "tenant-drill",
                "goal": "Pause and then complete through approval",
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
        if task["project_id"] != project_id or task["status"] != "waiting_for_approval":
            fail("x step 3: task did not attach to project in waiting_for_approval state")
        ok("task attached to project and paused for approval")

        step("4. Task-run rows agree with the task identity")
        r = client.get(f"/api/v1/agentic/tasks/{task_id}/runs")
        run_rows = r.json()
        if len(run_rows) != 2:
            fail(f"x step 4: expected 2 task run rows, got {len(run_rows)}")
        if any(row["task_id"] != task_id or row["project_id"] != project_id for row in run_rows):
            fail("x step 4: task run rows drifted from task/project identity")
        ok("task runs agree with task and project identity")

        step("5. Approval resumes the same task to completed")
        r = client.post(
            f"/api/v1/agentic/tasks/{task_id}/approve",
            json={"approved": True, "actor_id": "admin-user", "reason": "resume the workflow"},
        )
        approved_task = r.json()
        if approved_task["task_id"] != task_id or approved_task["status"] != "completed":
            fail("x step 5: approval did not resume the same task to completed")
        ok("approval resumes the same task to completed")

        step("6. Approval row matches the completed task identity")
        r = client.get(f"/api/v1/agentic/tasks/{task_id}/approvals")
        approval_rows = r.json()
        if len(approval_rows) != 1:
            fail(f"x step 6: expected 1 approval row, got {len(approval_rows)}")
        approval = approval_rows[0]
        if approval["task_id"] != task_id or approval["project_id"] != project_id or approval["decision"] != "approved":
            fail("x step 6: approval row drifted from task/project identity")
        ok("approval row matches task and project identity")

        step("7. Task memory matches the completed task identity")
        r = client.get(f"/api/v1/agentic/memories?scope_type=task&scope_id={task_id}")
        task_memories = r.json()
        if len(task_memories) != 1:
            fail(f"x step 7: expected 1 task memory row, got {len(task_memories)}")
        task_memory = task_memories[0]
        if task_memory["scope_id"] != task_id or task_memory["source_id"] != task_id:
            fail("x step 7: task memory drifted from task identity")
        if task_memory["payload"].get("status") != "completed":
            fail("x step 7: task memory payload missing completed status")
        ok("task memory matches completed task identity")

        step("8. Project memory matches the completed project identity")
        r = client.get(f"/api/v1/agentic/memories?scope_type=project&scope_id={project_id}")
        project_memories = r.json()
        if len(project_memories) != 1:
            fail(f"x step 8: expected 1 project memory row, got {len(project_memories)}")
        project_memory = project_memories[0]
        if project_memory["scope_id"] != project_id or project_memory["source_id"] != project_id:
            fail("x step 8: project memory drifted from project identity")
        planned_steps = project_memory["payload"].get("planned_steps") or []
        if len(planned_steps) != len(project["planned_tasks"]):
            fail("x step 8: project memory planned_steps disagrees with project planned_tasks")
        ok("project memory matches project identity and planned step count")

        step("9. Cross-surface chain is internally consistent")
        if approval["project_id"] != project_id:
            fail("x step 9: approval row project_id mismatch")
        if any(row["project_id"] != project_id for row in run_rows):
            fail("x step 9: one or more task run rows point at the wrong project")
        if task_memory["tenant_id"] != project["tenant_id"] or project_memory["tenant_id"] != project["tenant_id"]:
            fail("x step 9: tenant identity drifted across control-plane records")
        ok("tenant/project/task identity is consistent across plan, runs, approval, and memories")

    print("\n\033[1;32m════════════════════════════════════════\033[0m")
    print("\033[1;32m  ALL 9 AGENTIC-CONTROL-PLANE CHAIN STEPS PASSED\033[0m")
    print("\033[1;32m════════════════════════════════════════\033[0m")


if __name__ == "__main__":
    main()
