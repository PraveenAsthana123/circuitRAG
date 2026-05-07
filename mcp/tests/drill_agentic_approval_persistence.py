#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: agent-orchestrator approval decisions persist ApprovalView rows.

Locks the human-decision audit contract added to approve_task():

  * one approval row per decision
  * rejected branch persists decision="rejected"
  * approved branch persists decision="approved"
  * snapshot / reason / actor / task linkage are preserved

This drill stays tier-1 safe by stubbing external imports and using an
in-memory recording store.

Fifteen steps. Fourteen negative assertions covering both reject
and approve branches: row count, decision string, actor + reason
persistence, task/project linkage, snapshot status, reason_codes,
and (for approve) workflow resumption to completed.
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
PACKAGE_NAME = "agentic_app_approval"


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

ApprovalRequest = models_mod.ApprovalRequest
TaskView = models_mod.TaskView
InMemoryTaskStore = store_mod.InMemoryTaskStore
AgentOrchestratorService = service_mod.AgentOrchestratorService


class RecordingStore(InMemoryTaskStore):
    def __init__(self) -> None:
        super().__init__()
        self.approvals: list[Any] = []

    async def save_approval(self, approval) -> None:  # type: ignore[no-untyped-def]
        self.approvals.append(approval)


class ApprovalResumeService(AgentOrchestratorService):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._graph = _ResumeGraph()


class _ResumeGraph:
    async def ainvoke(self, state):
        return {
            "status": "completed",
            "confidence": 0.88,
            "advisor_summary": "workflow resumed and completed",
            "next_action": "done",
            "approval_reasons": list(state.get("approval_reasons", [])),
            "audit_events": [*state.get("audit_events", []), {"role": "test", "event": "resumed"}],
        }


def _make_task(*, status: str, project_id: str | None = None) -> Any:
    return TaskView(
        task_id="task-123",
        tenant_id="tenant-drill",
        project_id=project_id,
        goal="Persist approval decision",
        status=status,
        risk_level="medium",
        require_human_approval=True,
        approval_mode="plan_once",
        auto_advance=True,
        approved=None,
        confidence=0.63,
        plan=["classify", "execute"],
        worker_output="partial result",
        reviewer_notes=["needs approval"],
        advisor_summary="approval required",
        next_action="await_approval",
        tool_arguments={},
        approval_reasons=["requires human approval"],
        audit_events=[],
    )


async def _reject_case() -> tuple[int, str]:
    store = RecordingStore()
    svc = AgentOrchestratorService(store=store)
    task = _make_task(status="waiting_for_approval", project_id="project-1")
    await store.save(task)
    updated = await svc.approve_task(
        task.task_id,
        ApprovalRequest(approved=False, actor_id="human-1", reason="unsafe change"),
    )
    if updated is None:
        return 1, "x step 1: reject path returned None"
    if len(store.approvals) != 1:
        return 1, f"x step 2: reject path should persist 1 approval row, got {len(store.approvals)}"
    approval = store.approvals[0]
    if approval.decision != "rejected":
        return 1, f"x step 3: reject path decision mismatch, got {approval.decision!r}"
    if approval.actor_id != "human-1":
        return 1, f"x step 4: reject path actor mismatch, got {approval.actor_id!r}"
    if approval.reason != "unsafe change":
        return 1, f"x step 5: reject path reason mismatch, got {approval.reason!r}"
    if approval.task_id != task.task_id or approval.project_id != task.project_id:
        return 1, "x step 6: reject path task/project linkage drifted"
    if approval.reason_codes != ["requires human approval"]:
        return 1, f"x step 7: reject path reason_codes mismatch, got {approval.reason_codes!r}"
    if approval.snapshot.get("status") != "rejected":
        return 1, f"x step 8: reject path snapshot status mismatch, got {approval.snapshot!r}"
    return 0, "\n".join(
        [
            "✓ step 1: reject path returned updated task",
            "✓ step 2: reject path persisted exactly 1 approval row",
            "✓ step 3: reject path decision is rejected",
            "✓ step 4: reject path actor_id is persisted",
            "✓ step 5: reject path reason is persisted",
            "✓ step 6: reject path task/project linkage is preserved",
            "✓ step 7: reject path reason_codes are preserved",
            "✓ step 8: reject path snapshot reflects rejected status",
        ]
    )


async def _approve_case() -> tuple[int, str]:
    store = RecordingStore()
    svc = ApprovalResumeService(store=store)
    task = _make_task(status="waiting_for_plan_approval")
    await store.save(task)
    updated = await svc.approve_task(
        task.task_id,
        ApprovalRequest(approved=True, actor_id="human-2", reason="looks good"),
    )
    if updated is None:
        return 1, "x step 9: approve path returned None"
    if len(store.approvals) != 1:
        return 1, f"x step 10: approve path should persist 1 approval row, got {len(store.approvals)}"
    approval = store.approvals[0]
    if approval.decision != "approved":
        return 1, f"x step 11: approve path decision mismatch, got {approval.decision!r}"
    if approval.actor_id != "human-2":
        return 1, f"x step 12: approve path actor mismatch, got {approval.actor_id!r}"
    if approval.reason != "looks good":
        return 1, f"x step 13: approve path reason mismatch, got {approval.reason!r}"
    if approval.snapshot.get("status") != "completed":
        return 1, f"x step 14: approve path snapshot status mismatch, got {approval.snapshot!r}"
    if updated.status != "completed":
        return 1, f"x step 15: approve path task should complete after resume, got {updated.status!r}"
    return 0, "\n".join(
        [
            "✓ step 9: approve path returned updated task",
            "✓ step 10: approve path persisted exactly 1 approval row",
            "✓ step 11: approve path decision is approved",
            "✓ step 12: approve path actor_id is persisted",
            "✓ step 13: approve path reason is persisted",
            "✓ step 14: approve path snapshot reflects completed status",
            "✓ step 15: approve path resumes workflow to completed",
        ]
    )


async def _main() -> int:
    rc, msg = await _reject_case()
    if rc != 0:
        print(msg)
        return rc
    print(msg)

    rc, msg = await _approve_case()
    if rc != 0:
        print(msg)
        return rc
    print(msg)
    print("\n==================================================")
    print("  ALL 15 APPROVAL-PERSISTENCE STEPS PASSED")
    print("  (14 negative assertions: 2-8, 9-15)")
    print("==================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
