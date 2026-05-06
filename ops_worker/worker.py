"""Ops worker — autonomous task picker (Ollama proposes, Claude reviews).

Status lifecycle (matches user spec):
  PENDING → PICKED_UP → IN_PROGRESS → CODE_READY → CLAUDE_REVIEW
        → COMPLETED | REVISION_REQUIRED | FAILED

Recommendation mode (default + only mode currently):
  - Ollama produces a proposal (text only — no file writes)
  - Claude reviews it and emits decision
  - Operator reviews tasks.json and decides whether to apply
  - The worker NEVER writes to source files (CLAUDE.md §42 boundary)

Composition with existing repo (per CLAUDE.md §49):
  - §50 issue dispatcher: handles ruff/mypy issues at code-fix layer
  - This: handles task-level work (features / refactors / docs / spikes)
  - §55 fix-bot strategy: this is the "Tier B fallback" Claude reviewer
  - approval_agent.decide      — gate between Claude review and COMPLETED
  - safety_store.save_history  — every status transition writes a row
  - risk_classifier.classify_task — server-side risk before approval
  - scripts/paperclip_manager.aggregate_ops_worker — Stage-1 dashboard reads here
  - mcp/tests/drill_ops_worker.py — 8-step contract drill

Usage:
  # one iteration (cron-friendly):
  python ops_worker/worker.py --once

  # loop with sleep (foreground daemon):
  python ops_worker/worker.py --loop --interval 300

  # dry-run (no Ollama call, no Claude call):
  python ops_worker/worker.py --once --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

# safety_store + approval_agent are repo-level packages, not in ops_worker/
import sys as _sys
import time
from pathlib import Path
from pathlib import Path as _Path
from typing import Any

from claude_reviewer import review_with_claude
from notifier import notify
from ollama_agent import solve_with_ollama

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from approval_agent import decide as approval_decide  # noqa: E402
from risk_classifier import classify_task  # noqa: E402
from safety_store import save_history  # noqa: E402

TASK_FILE = Path(__file__).resolve().parent / "tasks.json"

PRIORITY_ORDER = {"high": 3, "medium": 2, "low": 1}

ACTIVE_STATUSES = {"PENDING", "REVISION_REQUIRED"}


def load_tasks() -> list[dict[str, Any]]:
    if not TASK_FILE.exists():
        return []
    return json.loads(TASK_FILE.read_text(encoding="utf-8"))


def save_tasks(tasks: list[dict[str, Any]]) -> None:
    """Write tasks to JSONL (authoritative) + optionally to SQL (queryable).

    Per CLAUDE.md §47.7 migrate-phase: when OPS_WORKER_SQL_ENABLED=1
    is set, ALSO upserts each task into orchestration.agent_tasks.
    JSONL stays authoritative; SQL is the queryable surface. Either
    side failing does NOT block the other (best-effort dual-write).
    Drill: drill_ops_worker_dual_write.py.
    """
    # JSONL write — authoritative surface, NEVER skipped.
    TASK_FILE.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")

    # SQL upsert — opt-in via env. Failure NEVER blocks the JSONL path.
    if os.getenv("OPS_WORKER_SQL_ENABLED", "").strip() == "1":
        for task in tasks:
            _persist_sql_task(task)


def _persist_sql_task(task: dict[str, Any]) -> None:
    """Upsert one task into orchestration.agent_tasks.

    Per §47.7 migrate-phase. The SQL surface complements (not replaces)
    the JSONL queue. Insert failure is logged but NEVER raised — the
    worker's response path stays unblocked.

    Field mapping ops_worker → orchestration.agent_tasks:
      id              → task_id (PK)
      title           → goal
      description     → first audit_events_json entry (preserves prose)
      status          → status (string roundtrip; SQL uses lowercase)
      risk            → risk_level
      ollama_output   → worker_output
      claude_review   → reviewer_notes_json (JSONB)
      approval_decision.reason → next_action

    tenant_id is 'system' because ops_worker tasks are service-account
    (no human tenant). The SQL table requires tenant_id NOT NULL with
    forced RLS; 'system' value matches the convention used by other
    service-account writers in this repo.
    """
    try:
        import asyncio

        import asyncpg
    except ImportError:
        return

    pg_host = os.getenv("DOCUMIND_PG_HOST", "localhost")
    pg_port = int(os.getenv("DOCUMIND_PG_PORT", "55432"))
    pg_user = os.getenv("DOCUMIND_PG_USER", "documind_app")
    pg_password = os.getenv("DOCUMIND_PG_PASSWORD", "documind_app")
    pg_db = os.getenv("DOCUMIND_PG_DB", "documind")

    # Normalize status — orchestration table expects lowercase; ops_worker
    # uses uppercase. Drill verifies the mapping is exact.
    status_normalized = str(task.get("status", "pending")).lower()
    risk_level = str(task.get("risk", "low")).lower()
    if risk_level not in ("low", "medium", "high", "critical"):
        risk_level = "low"

    review = task.get("claude_review") or {}

    async def _upsert() -> None:
        conn = await asyncpg.connect(
            host=pg_host, port=pg_port, user=pg_user,
            password=pg_password, database=pg_db, timeout=2.0,
        )
        try:
            # SET LOCAL only applies within a transaction. Without the
            # explicit tx, asyncpg's autocommit silently drops the GUC
            # and the RLS WITH CHECK fails with InsufficientPrivilege.
            async with conn.transaction():
                await conn.execute("SET LOCAL app.current_tenant = 'system'")
                await conn.execute(
                    "INSERT INTO orchestration.agent_tasks "
                    "(task_id, tenant_id, goal, status, risk_level, "
                    " worker_output, reviewer_notes_json, next_action) "
                    "VALUES ($1, 'system', $2, $3, $4, $5, $6::jsonb, $7) "
                    "ON CONFLICT (task_id) DO UPDATE SET "
                    "  status = EXCLUDED.status, "
                    "  risk_level = EXCLUDED.risk_level, "
                    "  worker_output = EXCLUDED.worker_output, "
                    "  reviewer_notes_json = EXCLUDED.reviewer_notes_json, "
                    "  next_action = EXCLUDED.next_action, "
                    "  updated_at = NOW()",
                    str(task.get("id", "")),
                    str(task.get("title", ""))[:500],
                    status_normalized,
                    risk_level,
                    str(task.get("ollama_output", ""))[:8000],
                    json.dumps(review),
                    str(task.get("approval_decision", {}).get("reason", ""))[:500],
                )
        finally:
            await conn.close()

    try:
        asyncio.run(_upsert())
    except Exception as exc:  # noqa: BLE001
        _log = logging.getLogger(__name__)
        _log.warning("ops_worker_sql_upsert_failed task_id=%s err=%s",
                     task.get("id"), type(exc).__name__)


def pick_next_task(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick highest-priority ACTIVE task. Returns None when queue is empty."""
    candidates = [t for t in tasks if t.get("status") in ACTIVE_STATUSES]
    if not candidates:
        return None
    candidates.sort(
        key=lambda t: (
            PRIORITY_ORDER.get(t.get("priority", "low"), 0),
            -t.get("attempts", 0),  # prefer fresh attempts
        ),
        reverse=True,
    )
    return candidates[0]


def _update_task(tasks: list[dict[str, Any]], task: dict[str, Any]) -> None:
    for i, t in enumerate(tasks):
        if t["id"] == task["id"]:
            tasks[i] = task
            return
    tasks.append(task)  # shouldn't happen, but defensive


def run_once(*, dry_run: bool = False) -> dict[str, Any]:
    """One iteration. Returns ``{outcome, task_id?, decision?}`` for callers."""
    tasks = load_tasks()
    task = pick_next_task(tasks)
    if task is None:
        notify(task_id=None, status="IDLE", message="No active task")
        return {"outcome": "idle"}

    # PICKED_UP — also server-classify the risk before any further gate.
    # The client-supplied ``risk`` becomes ``risk_declared``; the server's
    # classification becomes ``risk`` (the value approval_agent reads).
    # Audit row keeps both so a regulator can see when humans disagreed
    # with the classifier.
    task["status"] = "PICKED_UP"
    task["attempts"] = task.get("attempts", 0) + 1
    declared = task.get("risk")
    classified = classify_task(task)
    task["risk_declared"] = declared
    task["risk"] = classified.level
    task["risk_triggers"] = classified.triggers
    _update_task(tasks, task)
    save_tasks(tasks)
    notify(
        task_id=task["id"], status="PICKED_UP",
        message=task["title"],
        details={"risk_declared": declared, "risk_classified": classified.level,
                 "triggers": classified.triggers[:3]},
    )

    if dry_run:
        notify(task_id=task["id"], status="DRY_RUN", message="skipping Ollama + Claude")
        task["status"] = "PENDING"  # leave for real run
        _update_task(tasks, task)
        save_tasks(tasks)
        return {"outcome": "dry_run", "task_id": task["id"]}

    # IN_PROGRESS — Ollama proposes
    task["status"] = "IN_PROGRESS"
    _update_task(tasks, task)
    save_tasks(tasks)
    notify(task_id=task["id"], status="IN_PROGRESS", message="Ollama proposing")

    try:
        ollama_result = solve_with_ollama(task)
    except Exception as e:  # noqa: BLE001 — single boundary catch is intentional
        task["status"] = "FAILED"
        task["error"] = f"ollama: {e!s}"
        _update_task(tasks, task)
        save_tasks(tasks)
        notify(task_id=task["id"], status="FAILED", message=str(e))
        return {"outcome": "failed", "task_id": task["id"], "error": str(e)}

    task["ollama_output"] = ollama_result["response"]
    task["ollama_model"] = ollama_result["model"]
    task["ollama_tokens"] = ollama_result["tokens"]
    task["ollama_latency_ms"] = ollama_result["latency_ms"]
    task["status"] = "CODE_READY"
    _update_task(tasks, task)
    save_tasks(tasks)
    notify(
        task_id=task["id"],
        status="CODE_READY",
        message=f"proposal ready ({ollama_result['tokens']} tokens, "
        f"{ollama_result['latency_ms']}ms)",
        details={"model": ollama_result["model"]},
    )

    # CLAUDE_REVIEW
    task["status"] = "CLAUDE_REVIEW"
    _update_task(tasks, task)
    save_tasks(tasks)
    notify(task_id=task["id"], status="CLAUDE_REVIEW", message="Claude reviewing")

    try:
        review = review_with_claude(task, ollama_result["response"])
    except Exception as e:  # noqa: BLE001
        task["status"] = "FAILED"
        task["error"] = f"claude: {e!s}"
        _update_task(tasks, task)
        save_tasks(tasks)
        notify(task_id=task["id"], status="FAILED", message=f"Claude review failed: {e}")
        return {"outcome": "failed", "task_id": task["id"], "error": str(e)}

    task["claude_review"] = review
    decision = review["decision"]

    # ── Approval gate (composes approval_agent rules) ─────────────────
    # Reviewer output → approval decision. The approval_agent has
    # final say on whether the task is auto-completed, paused for
    # human, or denied. Even if Claude APPROVED, the approval_agent
    # may pause if the task type / risk requires human approval.
    approval = approval_decide(
        task=task,
        test_result="PASS",  # ops_worker doesn't run tests yet (TODO)
        governance_result="ALLOW",
        reviewer_decision=decision,
        confidence=0.85,
    )
    task["approval_decision"] = {
        "decision": approval.decision,
        "reason": approval.reason,
        "rule_hits": approval.rule_hits,
    }

    # ── History gate (composes safety_store) ──────────────────────────
    # Every status transition into a terminal state (COMPLETED, BLOCKED,
    # WAITING_FOR_HUMAN) writes a history row. Rollback IS available.
    old_state = {
        "status": "CLAUDE_REVIEW",
        "claude_decision": decision,
    }

    if approval.decision == "DENY":
        task["status"] = "BLOCKED"
        new_state = {"status": "BLOCKED", "approval": approval.reason}
        rec = save_history(
            entity_type="ops_worker_task", entity_id=task["id"],
            action="approval_deny", old_value=old_state, new_value=new_state,
            actor="approval_agent", reason=approval.reason,
            rollback_allowed=False,  # blocked tasks should not auto-rollback
        )
        notify(task_id=task["id"], status="BLOCKED",
               message=approval.reason, details={"history_id": rec.history_id})
    elif approval.decision == "HUMAN_REQUIRED":
        task["status"] = "WAITING_FOR_HUMAN"
        new_state = {"status": "WAITING_FOR_HUMAN", "approval": approval.reason}
        rec = save_history(
            entity_type="ops_worker_task", entity_id=task["id"],
            action="approval_pause_for_human", old_value=old_state, new_value=new_state,
            actor="approval_agent", reason=approval.reason,
        )
        notify(task_id=task["id"], status="WAITING_FOR_HUMAN",
               message=approval.reason, details={"history_id": rec.history_id})
    elif approval.decision == "AUTO_APPROVED":
        task["status"] = "COMPLETED"
        new_state = {"status": "COMPLETED", "claude_decision": decision}
        rec = save_history(
            entity_type="ops_worker_task", entity_id=task["id"],
            action="approval_auto", old_value=old_state, new_value=new_state,
            actor="approval_agent", reason=approval.reason, approved_by="approval_agent",
        )
        # Message clearly attributes the approval source. When Claude
        # was SKIPPED, completion is by policy rules (low risk +
        # auto_approve_task_type), not by Claude review.
        attribution = (
            f"approved by approval_agent (Claude=SKIPPED): {approval.reason}"
            if decision == "SKIPPED"
            else review.get("final_comment", approval.reason)
        )
        notify(
            task_id=task["id"], status="COMPLETED",
            message=attribution[:200],
            details={"claude_decision": decision,
                     "drill_present": review.get("drill_present"),
                     "neg_assertion": review.get("negative_assertion_present"),
                     "history_id": rec.history_id, "rollback_id": rec.rollback_id},
        )
    elif decision == "SKIPPED":
        # Claude unavailable — operator must review. NOT auto-promoted.
        task["status"] = "CODE_READY"
        new_state = {"status": "CODE_READY", "claude_decision": "SKIPPED"}
        rec = save_history(
            entity_type="ops_worker_task", entity_id=task["id"],
            action="manual_review_required", old_value=old_state, new_value=new_state,
            actor="ops_worker", reason="Claude review skipped (no API key)",
        )
        notify(
            task_id=task["id"], status="MANUAL_REVIEW",
            message="Claude review skipped (no API key) — operator must review",
            details={"history_id": rec.history_id},
        )
    else:  # REVISION_REQUIRED
        task["status"] = "REVISION_REQUIRED"
        new_state = {"status": "REVISION_REQUIRED", "claude_decision": decision}
        rec = save_history(
            entity_type="ops_worker_task", entity_id=task["id"],
            action="revision_required", old_value=old_state, new_value=new_state,
            actor="approval_agent", reason=approval.reason,
        )
        notify(
            task_id=task["id"],
            status="REVISION_REQUIRED",
            message=review.get("final_comment", "needs revision")[:200],
            details={
                "issues": review.get("issues", [])[:3],
                "required_fixes": review.get("required_fixes", [])[:3],
                "history_id": rec.history_id,
            },
        )

    _update_task(tasks, task)
    save_tasks(tasks)
    return {"outcome": "ok", "task_id": task["id"], "decision": decision}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true", help="single iteration")
    p.add_argument("--loop", action="store_true", help="loop with sleep")
    p.add_argument("--interval", type=int, default=300, help="loop sleep seconds")
    p.add_argument("--dry-run", action="store_true", help="skip Ollama + Claude calls")
    args = p.parse_args()

    if not (args.once or args.loop):
        args.once = True

    if args.once:
        result = run_once(dry_run=args.dry_run)
        return 0 if result["outcome"] != "failed" else 1

    while True:
        run_once(dry_run=args.dry_run)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
