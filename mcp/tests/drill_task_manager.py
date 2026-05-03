#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: task manager (Tier 5 #5.7) — schema + DAG + persistence.

Per CLAUDE.md §43 + §55. Locks the contract: Task schema fields,
extra='forbid' rejection, DAG validation, JSONL append-only,
latest-row-wins semantics.

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "task_manager.py"


def _load():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("task_manager", SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load {SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["task_manager"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    print("-- 1. POSITIVE: task_manager imports + 6 exports --")
    tm = _load()
    for name in ("Task", "add_task", "update_status", "list_current_tasks",
                 "_detect_cycle", "TASKS_LOG"):
        if not hasattr(tm, name):
            print(f"x step 1: missing export {name}")
            return 1
    print("  ok: 6 exports present")

    # Use temp log to avoid polluting real tasks
    real_log = tm.TASKS_LOG
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
        tm.TASKS_LOG = Path(fh.name)
    try:
        print("-- 2. POSITIVE: well-formed Task validates + adds --")
        task = tm.add_task(
            title="test task", owner="praveen", owner_type="human",
            priority="high",
        )
        if task.status != "pending":
            print(f"x step 2: default status should be 'pending'; got {task.status!r}")
            return 1
        if task.priority != "high":
            print(f"x step 2: priority not preserved")
            return 1
        print(f"  ok: task added; id={task.id} status=pending")

        print("-- 3. NEGATIVE: invalid status rejected --")
        try:
            tm.Task.model_validate({
                "id": "x", "title": "x", "owner_type": "human",
                "owner": "x", "status": "abandoned",  # not in Literal
                "priority": "medium", "depends_on": [], "tags": [],
                "created_at": tm.now_iso(), "updated_at": tm.now_iso(),
            })
        except Exception:
            print("  ok: status='abandoned' rejected by Literal")
        else:
            print("x step 3: invalid status accepted")
            return 1

        print("-- 4. NEGATIVE: extra hallucinated field rejected (extra='forbid') --")
        try:
            tm.Task.model_validate({
                "id": "x", "title": "x", "owner_type": "human",
                "owner": "x", "status": "pending", "priority": "medium",
                "depends_on": [], "tags": [],
                "created_at": tm.now_iso(), "updated_at": tm.now_iso(),
                "operator_pii_email": "praveen@example.com",  # extra
            })
        except Exception:
            print("  ok: extra 'operator_pii_email' rejected (extra='forbid')")
        else:
            print("x step 4: extra field accepted")
            return 1

        print("-- 5. NEGATIVE: cyclic depends_on rejected --")
        # add task A; add task B depending on A; try to add task C
        # making A depend on C (cycle: A → C → A would form, but
        # we add by changing existing — drill via direct cycle test)
        a = tm.add_task(title="A", owner="praveen", task_id="task-a")
        # Direct cycle: task that depends on itself
        try:
            tm.add_task(title="self-cycle", owner="praveen",
                        task_id="task-a-self", depends_on=["task-a-self"])
        except ValueError as e:
            if "cycle" not in str(e).lower():
                print(f"x step 5: error msg should mention 'cycle'; got {e}")
                return 1
            print(f"  ok: self-cycle rejected; reason={e}")
        else:
            print("x step 5: self-cycle accepted")
            return 1

        print("-- 6. NEGATIVE: invalid id pattern (uppercase) rejected --")
        try:
            tm.add_task(title="x", owner="praveen", task_id="Task-Uppercase")
        except Exception:
            print("  ok: 'Task-Uppercase' rejected by id pattern")
        else:
            print("x step 6: uppercase id accepted")
            return 1

        print("-- 7. NEGATIVE: update_status appends; latest-row-wins --")
        b = tm.add_task(title="B", owner="praveen", task_id="task-b")
        # initial: pending
        loaded = tm.list_current_tasks()
        b_initial = next((t for t in loaded if t.id == "task-b"), None)
        if b_initial.status != "pending":
            print(f"x step 7: B initial status should be pending; got {b_initial.status}")
            return 1
        # transition: in_progress
        tm.update_status("task-b", "in_progress")
        # transition: done
        tm.update_status("task-b", "done")
        # latest-row should reflect 'done'
        loaded = tm.list_current_tasks()
        b_final = next((t for t in loaded if t.id == "task-b"), None)
        if b_final.status != "done":
            print(f"x step 7: latest-row-wins broken; expected 'done', got {b_final.status}")
            return 1
        # raw log should have 3 rows for task-b (1 add + 2 updates)
        log_text = tm.TASKS_LOG.read_text(encoding="utf-8")
        b_rows = [l for l in log_text.splitlines() if '"id":"task-b"' in l]
        if len(b_rows) != 3:
            print(f"x step 7: expected 3 task-b rows in log; got {len(b_rows)}")
            return 1
        print(f"  ok: 3 append rows for task-b; latest-row-wins → 'done'")

        print("-- 8. POSITIVE: update_status on nonexistent id raises --")
        try:
            tm.update_status("task-zzz-nonexistent", "done")
        except ValueError as e:
            if "not found" not in str(e):
                print(f"x step 8: error msg should say 'not found'; got {e}")
                return 1
            print("  ok: nonexistent id raises ValueError")
        else:
            print("x step 8: update_status of nonexistent id succeeded")
            return 1
    finally:
        tm.TASKS_LOG = real_log

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
