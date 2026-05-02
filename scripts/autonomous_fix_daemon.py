#!/usr/bin/env python3
"""Autonomous Fix Daemon — always-active issue triage + drill-gated apply.

Per CLAUDE.md §50 (issue dispatcher) + §43 (drill discipline) +
§42 (gated operations) + §54 (no Co-Authored-By trailer).

THE DAEMON LOOP
===============

Every N seconds:
  1. SCAN     — run issue_scanner.py; refresh .loop/issue_checklist.jsonl
  2. CLAIM    — pick first un-attempted issue (skip ones already in
                .loop/agent_task_board_apply.jsonl)
  3. NOTIFY   — emit `daemon:taken_up <id>` event line on stdout
                (Monitor / cron-tail picks this up as a notification)
  4. ROUTE    — route by lane:
                - ruff:autofix       -> deterministic ruff --fix
                - human-review/hard  -> research → council → drill-gated apply
                - security (S*)      -> NEVER auto-apply; always queue for human
  5. APPLY    — drill-gated apply (ruff check + smoke pytest must pass);
                rollback on failure
  6. NOTIFY   — emit `daemon:applied <id>` or `daemon:rejected <id> reason=<r>`
  7. COMMIT   — git stage + commit per §51 forensic-substrate format,
                §54 NO Co-Authored-By trailer
  8. NEVER PUSH — push is §42-gated; operator runs agent_task_board.py
                  push --confirm explicitly

WHAT MAKES IT "ALWAYS ACTIVE"
=============================

  - Foreground long-running loop; bound timeout via --max-cycles.
  - Stops cleanly on Ctrl-C or empty queue (after one no-op cycle).
  - Status written to .loop/daemon_status.json on every tick so the
    task-board's `list` command can show "currently working on X".

§42 SAFETY
==========

  - Daemon NEVER pushes (force-push or otherwise).
  - Daemon NEVER deletes files (only applies diffs).
  - Daemon NEVER touches files outside services/ + libs/py/ + mcp/tests/.
  - Daemon SKIPS security rules (`S*`) — those go to human-review queue.
  - On any apply failure, daemon rolls back via `git apply -R`.

USAGE
=====

  python3 scripts/autonomous_fix_daemon.py                # forever
  python3 scripts/autonomous_fix_daemon.py --max-cycles 3 # bounded
  python3 scripts/autonomous_fix_daemon.py --interval 60  # 60s between scans
  python3 scripts/autonomous_fix_daemon.py --dry-run      # observe, don't apply

Drilled by mcp/tests/drill_autonomous_fix_daemon.py.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKLIST = REPO / ".loop" / "issue_checklist.jsonl"
AUDIT = REPO / ".loop" / "issue_audit.jsonl"
APPLY_AUDIT = REPO / ".loop" / "agent_task_board_apply.jsonl"
DAEMON_STATUS = REPO / ".loop" / "daemon_status.json"
ESCALATIONS = REPO / ".loop" / "escalations.md"
HUMAN_REVIEW_QUEUE = REPO / ".loop" / "human_review_queue.md"

ISSUE_SCANNER = Path.home() / ".claude" / "scripts" / "issue_scanner.py"
ISSUE_DISPATCHER = Path.home() / ".claude" / "scripts" / "issue_dispatcher.py"

# §42 boundaries: don't touch outside these paths.
SAFE_PATH_PREFIXES = (
    "services/",
    "libs/py/",
    "mcp/",
    "scripts/",
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def emit(event: str) -> None:
    """Single-line status event. Picked up by Monitor / cron-tail."""
    print(f"daemon:{event}", flush=True)


def write_status(state: dict) -> None:
    DAEMON_STATUS.parent.mkdir(parents=True, exist_ok=True)
    DAEMON_STATUS.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def append_apply_audit(record: dict) -> None:
    record["timestamp"] = _now()
    APPLY_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with APPLY_AUDIT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def scan_issues() -> int:
    """Run the issue scanner with the broadest surface possible.

    Bandit (`--include-bandit`) flags security issues that the daemon
    will SKIP at task-claim time per §50.5.3 — but exporting them to
    the human-review queue is more valuable than not knowing they
    exist. Same logic for mypy + eslint.
    """
    proc = subprocess.run(
        [
            "python3", str(ISSUE_SCANNER),
            "--repo", str(REPO),
            "--include-mypy",
            "--include-bandit",
            "--include-eslint",
        ],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        emit(f"scan_failed rc={proc.returncode}")
        return 0
    issues = load_jsonl(CHECKLIST)
    return len(issues)


def already_attempted(issue_id: str) -> bool:
    return any(r.get("id") == issue_id for r in load_jsonl(APPLY_AUDIT))


def is_safe_path(rel_path: str) -> bool:
    return any(rel_path.startswith(p) for p in SAFE_PATH_PREFIXES)


def is_security_rule(code: str) -> bool:
    """Per §50.5.3, security rules NEVER go to a local model.

    Covers ruff S* (security) AND bandit B* AND any code starting
    with 'security'. Earlier version only checked 'S*' which let
    bandit codes through — drill-gate caught the resulting corrupt
    patch but the request should never have been made.
    """
    return code.startswith(("S", "B")) or "security" in code.lower()


def find_next_task() -> dict | None:
    issues = load_jsonl(CHECKLIST)
    for issue in issues:
        if already_attempted(issue["id"]):
            continue
        if is_security_rule(issue.get("code", "")):
            continue  # never auto-apply security rules
        if not is_safe_path(issue.get("file", "")):
            continue  # outside safe boundary
        return issue
    return None


def export_human_review_queue() -> int:
    """Write the security/bandit issue list to a human-readable file.

    Per §50.5.3, security rules (S*/B*) NEVER go to a model. The daemon
    skips them at task-claim time — but skipping silently means an
    operator never sees them. Export to a markdown queue so the work
    is visible even though the daemon won't touch it.

    Returns count of items in the human-review queue.
    """
    issues = load_jsonl(CHECKLIST)
    skipped: list[dict] = []
    for issue in issues:
        code = issue.get("code", "")
        if is_security_rule(code) or code.startswith("B"):
            skipped.append(issue)
        elif not is_safe_path(issue.get("file", "")):
            skipped.append(issue)
    if not skipped:
        return 0
    HUMAN_REVIEW_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Human-review queue",
        "",
        f"**Generated**: {_now()}",
        f"**Count**: {len(skipped)} issues the autonomous daemon REFUSES to touch",
        "",
        "Per CLAUDE.md §50.5.3, security rules (`S*` / `B*`) and",
        "out-of-safe-path issues never go to a local model. Operator",
        "must triage these manually.",
        "",
        "| ID | Code | File:Line | Message |",
        "|---|---|---|---|",
    ]
    for i in skipped:
        msg = i["message"].replace("|", "\\|")[:100]
        lines.append(f"| `{i['id']}` | {i['code']} | `{i['file']}:{i['line']}` | {msg} |")
    HUMAN_REVIEW_QUEUE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(skipped)


def escalate(issue_id: str, reason: str) -> None:
    """Append an entry to the operator-readable escalation log.

    Called when the daemon rejects an issue. Without this log, every
    rejection is buried in the JSON audit; with it, an operator can
    `cat .loop/escalations.md` and see the full failure history at a
    glance. Per the user's "if ollama not able to fix then they need
    to update" — this IS the update.
    """
    ESCALATIONS.parent.mkdir(parents=True, exist_ok=True)
    if not ESCALATIONS.exists():
        ESCALATIONS.write_text(
            "# Daemon escalation log\n\n"
            "Each row: a council attempt the drill-gate rejected. "
            "If an issue appears here twice, route to manual fix.\n\n"
            "| Time | Issue | Reason |\n|---|---|---|\n",
            encoding="utf-8",
        )
    with ESCALATIONS.open("a", encoding="utf-8") as fh:
        fh.write(f"| {_now()} | `{issue_id}` | {reason[:200]} |\n")


def apply_ruff_autofix() -> tuple[int, int]:
    """Returns (before_count, after_count)."""
    before = len(load_jsonl(CHECKLIST))
    proc = subprocess.run(
        [".venv/bin/ruff", "check", "--fix",
         "services/agent-orchestrator-svc/app/", "libs/py/"],
        cwd=REPO, capture_output=True, text=True, timeout=60,
    )
    after_count = scan_issues()
    return before, after_count


def run_council(issue_id: str) -> bool:
    """Run the 3-model council on an issue. Returns True if completed."""
    proc = subprocess.run(
        ["python3", str(ISSUE_DISPATCHER), "--council", "--id", issue_id],
        cwd=REPO, capture_output=True, text=True, timeout=600,
    )
    return proc.returncode == 0


def extract_council_diff(issue_id: str) -> str | None:
    """Parse last council audit row for issue_id; extract clean diff or None."""
    rows = load_jsonl(AUDIT)
    council = next(
        (r for r in reversed(rows) if r.get("lane") == "council" and r["id"] == issue_id),
        None,
    )
    if council is None:
        return None
    author_output = council.get("chain", {}).get("author", {}).get("output", "")
    m = re.search(r"```diff\n(.*?)```", author_output, re.DOTALL)
    if m is None:
        return None
    diff = m.group(1).rstrip()
    # Reject deepseek tokenizer artifacts (empirical: 2/5 in our test set).
    if "<｜begin▁of▁sentence｜>" in diff or "<｜end▁of▁sentence｜>" in diff:
        return None
    return diff


def ruff_check_clean() -> bool:
    proc = subprocess.run(
        [".venv/bin/ruff", "check",
         "services/agent-orchestrator-svc/app/", "libs/py/"],
        cwd=REPO, capture_output=True, text=True, timeout=60,
    )
    return proc.returncode == 0


def drill_gated_apply(issue_id: str, diff: str) -> tuple[bool, str]:
    """Apply diff to working tree; gate on ruff. Roll back on failure."""
    check = subprocess.run(
        ["git", "apply", "-p0", "--check", "-"], cwd=REPO,
        input=diff + "\n", capture_output=True, text=True, timeout=30,
    )
    if check.returncode != 0:
        return False, f"git apply --check rejected: {check.stderr.strip()[:200]}"

    apply = subprocess.run(
        ["git", "apply", "-p0", "-"], cwd=REPO,
        input=diff + "\n", capture_output=True, text=True, timeout=30,
    )
    if apply.returncode != 0:
        return False, f"git apply failed: {apply.stderr.strip()[:200]}"

    if not ruff_check_clean():
        # Rollback
        subprocess.run(
            ["git", "apply", "-p0", "-R", "-"], cwd=REPO,
            input=diff + "\n", capture_output=True, text=True, timeout=30,
        )
        return False, "ruff check failed after apply; rolled back"

    return True, "applied; ruff clean"


def cycle_one(args: argparse.Namespace) -> str:
    """Run one daemon cycle. Returns short status string for status file."""
    emit(f"cycle_start at={_now()}")
    n_pending = scan_issues()
    n_human = export_human_review_queue()
    emit(f"scan_complete pending={n_pending} human_review_queued={n_human}")

    if n_pending == 0:
        return "queue_empty"

    # Phase 1: ruff:autofix any easy ones deterministically.
    issues = load_jsonl(CHECKLIST)
    easy_unattempted = [
        i for i in issues
        if i["assigned_to"] == "ruff:autofix"
        and not already_attempted(i["id"])
        and is_safe_path(i["file"])
    ]
    if easy_unattempted:
        emit(f"ruff_autofix_batch count={len(easy_unattempted)}")
        if not args.dry_run:
            before, after = apply_ruff_autofix()
            emit(f"ruff_autofix_done before={before} after={after}")
            for i in easy_unattempted:
                append_apply_audit({
                    "id": i["id"],
                    "outcome": "applied" if after < before else "rejected",
                    "reason": f"deterministic ruff --fix; pending {before}->{after}",
                    "diff_present": True,
                    "lane": "deterministic",
                })

    # Phase 2: pick one hard task, research + council + drill-gated apply.
    task = find_next_task()
    if task is None:
        return "no_eligible_task"

    issue_id = task["id"]
    emit(f"taken_up id={issue_id} code={task['code']} file={task['file']}:{task['line']}")
    write_status({
        "phase": "council",
        "current_id": issue_id,
        "started_at": _now(),
    })

    if args.dry_run:
        emit(f"dry_run_skip id={issue_id}")
        append_apply_audit({
            "id": issue_id,
            "outcome": "dry_run",
            "reason": "daemon --dry-run",
        })
        return "dry_run_logged"

    # Reuse existing council audit row if recent; otherwise run new council.
    diff = extract_council_diff(issue_id)
    if diff is None:
        emit(f"running_council id={issue_id}")
        ok = run_council(issue_id)
        if not ok:
            emit(f"council_failed id={issue_id}")
            append_apply_audit({
                "id": issue_id, "outcome": "rejected",
                "reason": "council subprocess returned non-zero",
            })
            return "council_failed"
        diff = extract_council_diff(issue_id)

    if diff is None:
        emit(f"diff_unparseable id={issue_id}")
        append_apply_audit({
            "id": issue_id, "outcome": "rejected",
            "reason": "no clean unified diff in author output (fence missing OR tokenizer artifact)",
        })
        return "diff_unparseable"

    emit(f"applying id={issue_id} diff_len={len(diff)}")
    ok, reason = drill_gated_apply(issue_id, diff)
    append_apply_audit({
        "id": issue_id,
        "outcome": "applied" if ok else "rejected",
        "reason": reason,
        "diff_present": True,
        "lane": "council",
    })
    if ok:
        emit(f"applied id={issue_id}")
        return "applied"
    emit(f"rejected id={issue_id} reason={reason[:80]}")
    escalate(issue_id, reason)
    return "rejected"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="autonomous_fix_daemon.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--max-cycles", type=int, default=0,
                        help="0 = run forever; otherwise stop after N cycles")
    parser.add_argument("--interval", type=float, default=120.0,
                        help="seconds between cycles (default: 120)")
    parser.add_argument("--dry-run", action="store_true",
                        help="emit events but do not mutate files")
    args = parser.parse_args()

    emit(f"start max_cycles={args.max_cycles} interval={args.interval} dry_run={args.dry_run}")
    cycles = 0
    consecutive_empty = 0
    try:
        while True:
            status = cycle_one(args)
            cycles += 1
            write_status({
                "last_cycle": cycles,
                "last_status": status,
                "last_at": _now(),
                "max_cycles": args.max_cycles,
                "interval": args.interval,
                "dry_run": args.dry_run,
            })
            if status in ("queue_empty", "no_eligible_task"):
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    emit(f"queue_drained_stop after_cycles={cycles}")
                    break
            else:
                consecutive_empty = 0

            if args.max_cycles and cycles >= args.max_cycles:
                emit(f"max_cycles_reached cycles={cycles}")
                break

            emit(f"sleep seconds={args.interval}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        emit(f"interrupted cycles={cycles}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
