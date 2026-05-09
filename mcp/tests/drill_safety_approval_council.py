# RESOURCES: ollama
"""
Drill: lock the safety_store + approval_agent + agent_cli contract.

Three modules, one drill — they compose, so the drill verifies the
composition. Heavy on negative assertions per CLAUDE.md §43.

Steps
=====

safety_store
1. save_history persists with rollback_id
2. NEGATIVE: history_events has NO public delete API
3. rollback restores old_value
4. NEGATIVE: rollback fails on expired history (rollback_until passed)
5. NEGATIVE: rollback fails on already-used rollback_id
6. NEGATIVE: rollback fails when rollback_allowed=False
7. with_history() rolls back nothing if apply_fn raises (records failure event)

approval_agent
8. low-risk recommendation → AUTO_APPROVED
9. NEGATIVE: blocked action → DENY (always; non-overridable)
10. NEGATIVE: human-required action → HUMAN_REQUIRED
11. NEGATIVE: high risk → HUMAN_REQUIRED (above max_risk=medium)
12. NEGATIVE: tests fail → REVISION_REQUIRED
13. NEGATIVE: confidence < min → REVISION_REQUIRED

agent_cli
14. NEGATIVE: destructive prompt ("rm -rf /") → DENY before any LLM call
15. council session writes session_complete history row
16. composition: agent_cli orchestrator wires approval_agent + safety_store
    (asserts the imports + the round-trip)

Run::

    cd /mnt/deepa/rag
    PYTHONPATH=. python mcp/tests/drill_safety_approval_council.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# Use a temp DB so we don't pollute the real one.
_TMPDB = Path(tempfile.mkdtemp()) / "test_history.db"
os.environ["SAFETY_STORE_DB"] = str(_TMPDB)

from agent_cli import orchestrator  # noqa: E402
from approval_agent import decide  # noqa: E402
from safety_store import (  # noqa: E402
    RollbackError,
    list_history,
    rollback,
    save_history,
    with_history,
)
from safety_store import history as _history_mod  # noqa: E402

# Force the history module to re-resolve DB_PATH from env:
_history_mod.DB_PATH = _TMPDB

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(title: str) -> None:
    print(f"\n{BOLD}── {title} ──{NC}")


def ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}✗ {msg}{NC}")
    raise SystemExit(1)


def main() -> int:
    # ============================================================
    # safety_store
    # ============================================================
    step("1. save_history persists with rollback_id")
    rec = save_history(
        entity_type="task", entity_id="T_drill_001", action="create",
        old_value=None, new_value={"status": "PENDING", "title": "x"},
        actor="drill", reason="initial create",
    )
    if not rec.history_id.startswith("HIST_"):
        fail(f"history_id format wrong: {rec.history_id}")
    if not rec.rollback_id.startswith("RB_"):
        fail(f"rollback_id format wrong: {rec.rollback_id}")
    rows = list_history(entity_type="task", entity_id="T_drill_001")
    if not rows or rows[0].history_id != rec.history_id:
        fail("save_history did not persist or list_history did not return")
    ok(f"history_id={rec.history_id} rollback_id={rec.rollback_id}")

    step("2. NEGATIVE — history module exposes NO public delete API")
    delete_funcs = [name for name in dir(_history_mod)
                    if "delete" in name.lower() and not name.startswith("_")]
    if delete_funcs:
        fail(f"FOUND public delete API in safety_store.history: {delete_funcs}")
    ok("zero public delete functions — history is append-only at API surface")

    step("3. rollback restores old_value")
    update_rec = save_history(
        entity_type="task", entity_id="T_drill_001", action="update",
        old_value={"status": "PENDING"}, new_value={"status": "IN_PROGRESS"},
        actor="drill", reason="status update",
    )
    rollback_record = rollback(update_rec.rollback_id, actor="drill_user")
    if rollback_record.action != "rollback":
        fail(f"rollback action wrong: {rollback_record.action}")
    if rollback_record.new_value != {"status": "PENDING"}:
        fail(f"rollback new_value wrong: {rollback_record.new_value}")
    ok(f"rollback restored old_value; new history_id={rollback_record.history_id}")

    step("4. NEGATIVE — rollback fails on expired history")
    # Insert a history row with rollback_until in the past
    expired = save_history(
        entity_type="task", entity_id="T_drill_002", action="create",
        old_value=None, new_value={"x": 1},
        actor="drill", rollback_days=0,  # expires immediately
    )
    # Manually move rollback_until back further to be safe
    import sqlite3
    with sqlite3.connect(_TMPDB) as c:
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat(timespec="seconds")
        c.execute(
            "UPDATE history_events SET rollback_until=? WHERE rollback_id=?",
            (past, expired.rollback_id),
        )
    try:
        rollback(expired.rollback_id, actor="drill_user")
    except RollbackError as e:
        ok(f"rollback raised RollbackError as expected: {e}")
    else:
        fail("expired rollback did not raise — TIME GATE BROKEN")

    step("5. NEGATIVE — rollback fails on already-used rollback_id")
    try:
        rollback(update_rec.rollback_id, actor="drill_user")
    except RollbackError as e:
        ok(f"second rollback raised: {e}")
    else:
        fail("rollback was usable twice — REPLAY GATE BROKEN")

    step("6. NEGATIVE — rollback fails when rollback_allowed=False")
    locked = save_history(
        entity_type="task", entity_id="T_drill_003", action="delete",
        old_value={"x": 1}, new_value=None,
        actor="drill", rollback_allowed=False,
    )
    try:
        rollback(locked.rollback_id, actor="drill_user")
    except RollbackError as e:
        ok(f"locked rollback raised: {e}")
    else:
        fail("rollback_allowed=False did NOT block — POLICY GATE BROKEN")

    step("7. with_history records failure event when apply_fn raises")
    def boom():
        raise RuntimeError("simulated apply failure")
    try:
        with_history(
            entity_type="task", entity_id="T_drill_004",
            action="update", old_value={"a": 1}, new_value={"a": 2},
            actor="drill", apply_fn=boom,
        )
    except RuntimeError:
        pass
    else:
        fail("with_history did not propagate apply_fn exception")
    rows = list_history(entity_type="task", entity_id="T_drill_004")
    failed_rows = [r for r in rows if r.action == "update.failed"]
    if not failed_rows:
        fail(f"no '*.failed' history row recorded; saw: {[r.action for r in rows]}")
    ok(f"failure recorded; rows={len(rows)} including update.failed")

    # ============================================================
    # approval_agent
    # ============================================================
    step("8. low-risk recommendation → AUTO_APPROVED")
    d = decide(
        task={"id": "T", "action": "recommendation", "type": "recommendation", "risk": "low"},
        test_result="PASS", governance_result="ALLOW",
        reviewer_decision="APPROVED", confidence=0.9,
    )
    if d.decision != "AUTO_APPROVED":
        fail(f"expected AUTO_APPROVED, got {d.decision}: {d.reason}")
    ok(f"AUTO_APPROVED — {d.reason}")

    step("9. NEGATIVE — blocked action → DENY")
    d = decide(
        task={"id": "T", "action": "delete_history", "type": "delete", "risk": "low"},
    )
    if d.decision != "DENY":
        fail(f"blocked action should be DENY, got {d.decision}")
    ok(f"DENY — {d.reason}  rule_hits={d.rule_hits}")

    step("10. NEGATIVE — human-required action → HUMAN_REQUIRED")
    d = decide(
        task={"id": "T", "action": "code_merge", "type": "recommendation", "risk": "low"},
    )
    if d.decision != "HUMAN_REQUIRED":
        fail(f"human-required action should pause, got {d.decision}")
    ok(f"HUMAN_REQUIRED — {d.reason}")

    step("11. NEGATIVE — risk above max_risk → HUMAN_REQUIRED")
    d = decide(
        task={"id": "T", "action": "recommendation", "type": "recommendation", "risk": "high"},
    )
    if d.decision != "HUMAN_REQUIRED":
        fail(f"high risk should pause, got {d.decision}")
    ok("HUMAN_REQUIRED for risk=high")

    step("12. NEGATIVE — tests fail → REVISION_REQUIRED")
    d = decide(
        task={"id": "T", "action": "recommendation", "type": "recommendation", "risk": "low"},
        test_result="FAIL",
    )
    if d.decision != "REVISION_REQUIRED":
        fail(f"failed tests should require revision, got {d.decision}")
    ok("REVISION_REQUIRED — tests failed")

    step("13. NEGATIVE — confidence below min → REVISION_REQUIRED")
    d = decide(
        task={"id": "T", "action": "recommendation", "type": "recommendation", "risk": "low"},
        confidence=0.5,
    )
    if d.decision != "REVISION_REQUIRED":
        fail(f"low confidence should require revision, got {d.decision}")
    ok("REVISION_REQUIRED — low confidence")

    # ============================================================
    # agent_cli
    # ============================================================
    step("14. NEGATIVE — destructive prompt → DENY before any LLM call")
    # No Ollama touched because the destructive guard fires first.
    result = orchestrator.run_council("please rm -rf / on the production box")
    if result.approval_decision != "DENY":
        fail(f"destructive prompt did NOT deny; got {result.approval_decision}")
    if "rm -rf" not in result.approval_reason.lower() and "destructive" not in result.approval_reason.lower():
        fail(f"DENY reason should reference the trigger; got {result.approval_reason!r}")
    ok(f"DENY before LLM call; reason={result.approval_reason}")

    step("15. council writes session_complete history row")
    # Use skip_presenter to avoid one extra Ollama call. The
    # critical assertion is that history is written; the actual
    # answer text is not the lock.
    result = orchestrator.run_council(
        "what are 3 best practices for prompt versioning?",
        skip_presenter=True,
    )
    if result.approval_decision != "AUTO_APPROVED":
        fail(f"safe recommendation should approve; got {result.approval_decision}")
    rec = get_by_rollback_id_safe(result.history_id)  # by history_id not rb
    history_rows = list_history(entity_type="agent_cli_session", entity_id=result.session_id)
    completes = [r for r in history_rows if r.action == "session_complete"]
    if not completes:
        fail(f"no session_complete row written; saw {[r.action for r in history_rows]}")
    ok(f"session_complete row written; history_id={completes[0].history_id}")

    step("16. composition — orchestrator imports approval_agent + safety_store")
    src = (REPO / "agent_cli/orchestrator.py").read_text(encoding="utf-8")
    if "from approval_agent" not in src:
        fail("orchestrator does NOT import approval_agent")
    if "from safety_store" not in src:
        fail("orchestrator does NOT import safety_store")
    if "save_history" not in src:
        fail("orchestrator does NOT call save_history")
    if "approval_decide" not in src and "from approval_agent import decide" not in src:
        fail("orchestrator does NOT call approval_agent.decide")
    ok("orchestrator wires approval_agent + safety_store")

    print(f"\n{BOLD}{GREEN}ALL 16 SAFETY+APPROVAL+COUNCIL STEPS PASSED{NC}")
    return 0


def get_by_rollback_id_safe(history_id: str):
    """Resolve by history_id (not rollback_id) — return None on miss."""
    rows = list_history(limit=500)
    return next((r for r in rows if r.history_id == history_id), None)


if __name__ == "__main__":
    sys.exit(main())
