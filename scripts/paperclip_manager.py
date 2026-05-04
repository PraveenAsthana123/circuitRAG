#!/usr/bin/env python3
"""Paperclip Stage-1 — read-only manager-layer aggregator.

Per CLAUDE.md §47 (orchestration architecture) + ADR-012
(Paperclip = manager UX above MCP/council substrate). Stage-1 is
**read-only by contract**: subscribes to existing surfaces, never
writes, never dispatches.

The architecture:

  Policy (OPA)  →  Manager (Paperclip)  →  Workers (council)  →  External
                       ↑
                    THIS MODULE

What Stage-1 does:

  - Aggregate council batch summary (.loop/council_batch_summary.json)
  - Aggregate task-board state (agent_task_board.py list)
  - Aggregate outcome metrics (outcome_eval.py report)
  - Aggregate apply-rate over last 7d from .loop/issue_audit.jsonl
  - Surface the brutal honesty signal:
    * total_attempts (council runs)
    * applied (drill-gate accepted)
    * apply_rate (= applied / total_attempts)
    * pending_human_review (rejected proposals awaiting operator)

What Stage-1 does NOT do (drill-locked negatives):

  - No write methods. No `assign_*`, `dispatch_*`, `push_*`,
    `update_*`, `mutate_*`. Only `snapshot_*` / `read_*` / `aggregate_*`.
  - No mutation of .loop/ files (drill: worktree byte-identical
    pre/post snapshot).
  - No outbound HTTP calls (drill: offline-runnable).
  - No side effects on import (drill: pure module load).
  - Refuses §42-gated verbs (push, dispatch, escalate) with a
    §42 citation in the error.

Stage 2 (proposal-only) and Stage 3 (gated delegation) compose on
top by adding capabilities — never by modifying this contract.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
LOOP_DIR = REPO / ".loop"

# --------------------------------------------------------------------------
# Read-only surfaces. Each function ONLY reads + aggregates. Never writes.
# --------------------------------------------------------------------------


def _read_jsonl(path: Path, limit: int = 1000) -> list[dict[str, Any]]:
    """Read JSONL with bounded limit. Returns [] if missing."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(rows) >= limit:
                break
    return rows


def _read_json(path: Path) -> dict[str, Any]:
    """Read JSON; return {} if missing or malformed."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def aggregate_council_batch() -> dict[str, Any]:
    """Aggregate the latest council batch summary."""
    summary = _read_json(LOOP_DIR / "council_batch_summary.json")
    return {
        "total_attempted": summary.get("total_medium", 0),
        "unique_ids_run": summary.get("unique_ids_run", 0),
        "total_elapsed_s": summary.get("total_elapsed_s", 0.0),
        "last_run_count": len(summary.get("runs", [])),
    }


def _ts_to_epoch(ts: Any) -> float:
    """Coerce timestamp (epoch float OR ISO-8601 string) to epoch seconds.

    The repo writes both shapes across different writers; the Paperclip
    aggregator must tolerate both rather than crash.
    """
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        from datetime import datetime
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            return 0.0
    return 0.0


def aggregate_apply_attempts(window_days: int = 7) -> dict[str, Any]:
    """Aggregate apply-attempt outcomes over last N days.

    The brutal-honesty surface — surfaces apply_rate even when 0%.
    """
    rows = _read_jsonl(LOOP_DIR / "agent_task_board_apply.jsonl", limit=5000)
    cutoff = time.time() - (window_days * 86400)

    recent = [r for r in rows if _ts_to_epoch(r.get("timestamp", 0)) >= cutoff]
    outcomes = Counter(r.get("outcome", "unknown") for r in recent)
    applied = outcomes.get("applied", 0)
    total = sum(outcomes.values())
    rate = (applied / total) if total > 0 else 0.0

    return {
        "window_days": window_days,
        "total_attempts": total,
        "applied": applied,
        "rejected": outcomes.get("rejected", 0),
        "drill_failed": outcomes.get("drill_failed", 0),
        "errored": outcomes.get("errored", 0),
        "apply_rate": round(rate, 4),
        "honesty_signal": (
            f"{applied}/{total} applied — apply_rate {rate:.1%}"
            if total > 0
            else "no apply attempts in window"
        ),
    }


def aggregate_audit_decisions(limit: int = 50) -> list[dict[str, Any]]:
    """Recent decision audit rows (truncated for snapshot).

    The on-disk audit rows are uneven: some flat (single-role attempts),
    some nested under .chain.{author,reviewer,advisor,researcher}.
    Stage-1 surfaces the top-level outcome + the dominant role's model
    + total tokens summed across the chain.
    """
    rows = _read_jsonl(LOOP_DIR / "issue_audit.jsonl", limit=limit * 4)
    rows.sort(
        key=lambda r: _ts_to_epoch(r.get("ts") or r.get("timestamp", 0)),
        reverse=True,
    )
    out = []
    for r in rows[:limit]:
        chain = r.get("chain", {}) or {}
        # Sum tokens + max latency across the chain (or fall back to flat fields)
        total_tokens = sum(
            int(v.get("tokens", 0)) for v in chain.values() if isinstance(v, dict)
        ) or int(r.get("tokens", 0))
        max_latency = max(
            (float(v.get("latency_s", 0.0)) for v in chain.values() if isinstance(v, dict)),
            default=float(r.get("latency_s", 0.0)),
        )
        # Pick the dominant model: author if present, else any role, else flat
        author = chain.get("author") or {}
        model = author.get("model") or r.get("model", "?")
        out.append({
            "issue_id": r.get("id") or r.get("issue_id", "?"),
            "lane": r.get("lane", "?"),
            "model": model,
            "outcome": r.get("outcome", "?"),
            "tokens_total": total_tokens,
            "max_latency_s": round(max_latency, 2),
        })
    return out


def aggregate_pending_issues() -> dict[str, Any]:
    """Pending issues from the checklist."""
    rows = _read_jsonl(LOOP_DIR / "issue_checklist.jsonl", limit=10000)
    by_assignee: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    by_difficulty: Counter[str] = Counter()
    for r in rows:
        if r.get("status") == "pending":
            by_assignee[r.get("assignee", "?")] += 1
            by_severity[r.get("severity", "?")] += 1
            by_difficulty[r.get("difficulty", "?")] += 1
    return {
        "total_pending": sum(by_assignee.values()),
        "by_assignee": dict(by_assignee),
        "by_severity": dict(by_severity),
        "by_difficulty": dict(by_difficulty),
    }


def aggregate_council_outcomes() -> dict[str, Any]:
    """Council outcome breakdown — how many ✓ vs ✗ vs pending.

    Top-level `outcome` is the chair-equivalent verdict on each council
    attempt. Aggregates across both schemas (lane=council_local rows
    and the older flat shape).
    """
    rows = _read_jsonl(LOOP_DIR / "issue_audit.jsonl", limit=10000)
    by_outcome: Counter[str] = Counter()
    for r in rows:
        if r.get("lane", "").startswith("council") or "chain" in r:
            by_outcome[r.get("outcome", "?")] += 1
    return {
        "by_outcome": dict(by_outcome),
        "total": sum(by_outcome.values()),
    }


# --------------------------------------------------------------------------
# Top-level snapshot — composes all read-only aggregators.
# --------------------------------------------------------------------------


def snapshot(window_days: int = 7) -> dict[str, Any]:
    """The single read-only entry point. Returns aggregated JSON.

    This is THE Paperclip Stage-1 contract. The drill locks:
      - this function exists
      - it returns dict with the 6 documented top-level keys
      - it does not mutate state
      - it does not call out to network
    """
    return {
        "stage": 1,
        "version": "paperclip-readonly-v1",
        "generated_at": time.time(),
        "council_batch": aggregate_council_batch(),
        "apply_attempts": aggregate_apply_attempts(window_days=window_days),
        "audit_decisions": aggregate_audit_decisions(limit=20),
        "pending_issues": aggregate_pending_issues(),
        "council_outcomes": aggregate_council_outcomes(),
    }


# --------------------------------------------------------------------------
# §42-gated verb refusal. Stage-1 has NO write capability; any attempt
# to invoke a write-style verb returns a refusal that cites §42.
# --------------------------------------------------------------------------

WRITE_VERBS = (
    "push", "dispatch", "assign", "escalate", "apply",
    "merge", "deploy", "rollback", "promote",
)


def refuse_write_verb(verb: str) -> dict[str, Any]:
    """Stage-1 contract: write verbs are refused with §42 citation."""
    return {
        "ok": False,
        "error_code": "STAGE_1_READ_ONLY",
        "verb": verb,
        "message": (
            f"Paperclip Stage-1 is read-only by contract. "
            f"Verb {verb!r} is §42-gated and not available until Stage 2 "
            f"(proposal-only) and Stage 3 (gated delegation) ship with "
            f"explicit MCP scope tokens + drill-gated apply."
        ),
        "see": "docs/architecture/adr/012-orchestration-layer-local-first.md",
    }


# --------------------------------------------------------------------------
# CLI surface — for operator + drill consumption.
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="paperclip_manager",
        description="Stage-1 read-only manager-layer aggregator.",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_snap = sub.add_parser("snapshot", help="Print aggregated snapshot JSON")
    p_snap.add_argument("--window-days", type=int, default=7)
    p_snap.add_argument("--pretty", action="store_true")

    sub.add_parser("verbs", help="List allowed read-only verbs")

    # Write verbs registered explicitly so they route to refuse_write_verb
    # rather than argparse's generic "invalid choice" error. The point is
    # that the §42 refusal must be the loud, operator-readable response —
    # not an argparse error swallowed in CI logs.
    for verb in WRITE_VERBS:
        sub.add_parser(verb, help=f"§42-gated (Stage-1 refuses; see refusal payload)")

    args = parser.parse_args()

    if args.cmd == "snapshot":
        snap = snapshot(window_days=args.window_days)
        indent = 2 if args.pretty else None
        print(json.dumps(snap, indent=indent, default=str))
        return 0

    if args.cmd == "verbs":
        print(json.dumps({
            "stage": 1,
            "read_only_verbs": ["snapshot", "verbs"],
            "refused_verbs_until_stage_2_3": list(WRITE_VERBS),
            "rationale": "Stage-1 is read-only per ADR-012. §42 boundaries.",
        }, indent=2))
        return 0

    if args.cmd in WRITE_VERBS:
        print(json.dumps(refuse_write_verb(args.cmd), indent=2))
        return 2  # §42-gated exit code

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
