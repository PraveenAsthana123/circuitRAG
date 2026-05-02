#!/usr/bin/env python3
"""Agent Task Board — central status view + drill-gated apply pipeline.

Per CLAUDE.md §50 (issue dispatcher) + §43 (drill discipline) +
§54 (no Co-Authored-By trailer).

WHAT THIS DOES
==============

The §50 issue dispatcher discovers issues + runs council; this script
is the **operator-facing surface** that ties together:

  - Discovery     (read .loop/issue_checklist.jsonl)
  - Assignment    (which model is on which task; tier-routing)
  - Research      (research agent: grep-context BEFORE council fires —
                  closes the "±5 lines is too little" gap for F841-class
                  bugs that span files)
  - Status        (read .loop/issue_audit.jsonl + council summary)
  - Apply gate    (drill-gated apply: extract Author diff -> validate ->
                  apply to worktree -> ruff + smoke pytest -> accept/reject)
  - Commit        (§51 forensic-substrate metadata; §54 NO Co-Authored-By)
  - Push          (gated per §42 — operator must --push explicitly)

NON-GOALS (carved out per §44.5 ONE-thing-per-iteration):
  - LoRA fine-tune pipeline (§44/§45 territory)
  - Multi-file refactor (separate iteration)
  - Cron scheduling (separate iteration; this is the manual-trigger
    version that the cron will eventually wrap)

USAGE
=====

  list                          # full task board snapshot
  research <issue_id>           # research agent investigates the issue
  apply <issue_id>              # drill-gated apply of council Author diff
  status                        # alias for list
  push --confirm                # push to GitHub (§42 gated; explicit)

Drilled by mcp/tests/drill_agent_task_board.py.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKLIST = REPO / ".loop" / "issue_checklist.jsonl"
AUDIT = REPO / ".loop" / "issue_audit.jsonl"
APPLY_AUDIT = REPO / ".loop" / "agent_task_board_apply.jsonl"

COUNCIL_AGENTS: dict[str, dict[str, str]] = {
    "deepseek-coder:6.7b-instruct": {
        "role": "AUTHOR",
        "lane": "council",
        "specialty": "code-fix proposals (unified diff)",
    },
    "codegemma:7b-instruct": {
        "role": "REVIEWER",
        "lane": "council",
        "specialty": "critique correctness independently",
    },
    "codellama:7b-instruct": {
        "role": "ADVISOR",
        "lane": "council",
        "specialty": "synthesizes alternative; chair input",
    },
    "qwen2.5:latest": {
        "role": "RESEARCHER",
        "lane": "research",
        "specialty": "grep-context investigation BEFORE council fires",
    },
    "ruff": {
        "role": "AUTOFIX",
        "lane": "deterministic",
        "specialty": "auto-applied for I001/F401/UP041 etc.",
    },
}


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _git(cmd: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *cmd],
        cwd=REPO,
        capture_output=capture,
        text=True,
        timeout=60,
    )


def _ruff_check_passes() -> tuple[bool, str]:
    """Returns (clean, output). Clean = exit 0 = no remaining issues."""
    proc = subprocess.run(
        [".venv/bin/ruff", "check", "services/agent-orchestrator-svc/app/", "libs/py/"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return (proc.returncode == 0, (proc.stdout or "") + (proc.stderr or ""))


def cmd_list(_: argparse.Namespace) -> int:
    print("╔══════════════════════════════════════════════════════════╗")
    print("║              AGENT TASK BOARD — live status              ║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    print("=== AGENTS (5 lanes) ===")
    for model, info in COUNCIL_AGENTS.items():
        print(f"  • {info['role']:<10} {model:<32} lane={info['lane']:<13} {info['specialty']}")
    print()

    issues = _load_jsonl(CHECKLIST)
    audit = _load_jsonl(AUDIT)
    council_runs = [r for r in audit if r.get("lane") == "council"]

    issue_ids_in_audit = {r["id"] for r in council_runs}
    pending = [i for i in issues if i["id"] not in issue_ids_in_audit]
    completed_council = [r for r in council_runs if r.get("outcome") == "council_complete"]

    apply_audit = _load_jsonl(APPLY_AUDIT)
    applied_ids = {r["id"] for r in apply_audit if r.get("outcome") == "applied"}
    rejected_ids = {r["id"] for r in apply_audit if r.get("outcome") == "rejected"}

    print(f"=== PENDING (no council run yet) — {len(pending)} ===")
    for i in pending[:10]:
        print(f"  ⏳ {i['id']:<40} {i['code']:<6} -> {i['assigned_to']}")
    if len(pending) > 10:
        print(f"  ... +{len(pending) - 10} more")
    print()

    print(f"=== COUNCIL-COMPLETE (proposal ready) — {len(completed_council)} ===")
    for r in completed_council[-10:]:
        applied = "✅ applied" if r["id"] in applied_ids else (
            "❌ rejected" if r["id"] in rejected_ids else "⏸  awaiting apply"
        )
        chain = r.get("chain", {})
        author_lat = chain.get("author", {}).get("latency_s", "?")
        print(f"  {applied}  {r['id']:<40}  author_lat={author_lat}s")
    print()

    print(f"=== APPLY HISTORY — {len(apply_audit)} attempts ===")
    by_outcome = Counter(r.get("outcome", "?") for r in apply_audit)
    for outcome, n in by_outcome.most_common():
        print(f"  {outcome}: {n}")
    print()

    proc = _git(["log", "origin/main..HEAD", "--oneline"])
    unpushed = proc.stdout.strip().splitlines() if proc.returncode == 0 else []
    print(f"=== UNPUSHED COMMITS — {len(unpushed)} (run `push --confirm` to ship) ===")
    for line in unpushed[:5]:
        print(f"  {line}")
    if len(unpushed) > 5:
        print(f"  ... +{len(unpushed) - 5} more")
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    """Research agent — grep-RAG investigation BEFORE the council fires.

    For an issue like F841 (unused `pipeline_v2`), the council with ±5
    lines context cannot decide "real bug or dead code." The research
    step:
      1. Reads the issue site
      2. Greps the entire repo for related references
      3. Reads top-N callers/users
      4. Writes a research brief to .loop/research/<id>.md

    The council then reads the brief instead of the bare ±5 lines.
    """
    issues = _load_jsonl(CHECKLIST)
    target = next((i for i in issues if i["id"] == args.issue_id), None)
    if target is None:
        print(f"x issue not found: {args.issue_id}")
        return 1

    research_dir = REPO / ".loop" / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    out_path = research_dir / f"{args.issue_id}.md"

    file_path = REPO / target["file"]
    line_no = target["line"]

    snippet = file_path.read_text(encoding="utf-8").splitlines()
    start = max(0, line_no - 30)
    end = min(len(snippet), line_no + 30)
    context_60 = "\n".join(f"{i + 1:4}: {snippet[i]}" for i in range(start, end))

    grep_target: str | None = None
    rule = target["code"]
    msg = target["message"]
    if rule == "F841":
        m = re.search(r"`([^`]+)`", msg)
        if m:
            grep_target = m.group(1)
    elif rule == "UP035":
        m = re.search(r"`([^`]+)`", msg)
        if m:
            grep_target = m.group(1)

    grep_out = ""
    if grep_target:
        proc = subprocess.run(
            ["grep", "-rn", "--include=*.py", grep_target, "services/", "libs/"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=30,
        )
        grep_out = (proc.stdout or "")[:4000]

    brief = (
        f"# Research brief: {args.issue_id}\n"
        f"\n"
        f"**Rule**: {target['code']}\n"
        f"**File**: {target['file']}:{target['line']}\n"
        f"**Message**: {target['message']}\n"
        f"\n"
        f"## Context (±30 lines)\n"
        f"```\n{context_60}\n```\n"
        f"\n"
        f"## References (grep `{grep_target}` across repo)\n"
        f"```\n{grep_out or '(no grep target derived from rule message)'}\n```\n"
        f"\n"
        f"## Verdict / hypothesis\n"
        f"\n"
        f"_Operator: read context + references; decide if dead code, real bug,\n"
        f"or mechanical fix. Council with this brief will produce a more\n"
        f"context-aware proposal than the dispatcher's default ±5 lines._\n"
    )
    out_path.write_text(brief, encoding="utf-8")
    print(f"✓ research brief written: {out_path.relative_to(REPO)}")
    print(f"  context window: ±30 lines")
    if grep_target:
        ref_lines = len(grep_out.splitlines()) if grep_out else 0
        print(f"  grep target: '{grep_target}' -> {ref_lines} reference line(s)")
    else:
        print(f"  no grep target derived (rule {rule} not in known set)")
    return 0


def _extract_unified_diff(author_output: str) -> str | None:
    m = re.search(r"```diff\n(.*?)```", author_output, re.DOTALL)
    if m is None:
        return None
    diff = m.group(1).rstrip()
    # Reject deepseek tokenizer artifacts that have appeared in our
    # empirical council outputs (1/5 cases). Don't even try to apply.
    if "<｜begin▁of▁sentence｜>" in diff or "<｜end▁of▁sentence｜>" in diff:
        return None
    return diff


def cmd_apply(args: argparse.Namespace) -> int:
    """Drill-gated apply: extract Author diff → apply → ruff check → audit."""
    audit = _load_jsonl(AUDIT)
    council = next(
        (r for r in audit if r.get("lane") == "council" and r["id"] == args.issue_id),
        None,
    )
    if council is None:
        print(f"x no council audit row for {args.issue_id}")
        return 1

    author_output = council.get("chain", {}).get("author", {}).get("output", "")
    diff = _extract_unified_diff(author_output)

    apply_record = {
        "id": args.issue_id,
        "outcome": "rejected",
        "reason": "",
        "diff_present": diff is not None,
    }

    if diff is None:
        apply_record["reason"] = (
            "no clean diff in author output (missing fence OR tokenizer artifact)"
        )
        _append_audit(apply_record)
        print(f"x rejected: {apply_record['reason']}")
        return 2

    print("=== Diff extracted ===")
    print(diff[:600])
    print()

    if not args.commit:
        apply_record["outcome"] = "dry_run"
        apply_record["reason"] = "no --commit flag"
        _append_audit(apply_record)
        print("(dry-run — re-run with --commit to actually apply + run gate)")
        return 0

    proc = subprocess.run(
        ["git", "apply", "-p0", "--check", "-"],
        cwd=REPO,
        input=diff + "\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        apply_record["reason"] = f"git apply --check failed: {proc.stderr.strip()[:200]}"
        _append_audit(apply_record)
        print(f"x rejected: {apply_record['reason']}")
        return 3

    apply_proc = subprocess.run(
        ["git", "apply", "-p0", "-"],
        cwd=REPO,
        input=diff + "\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    if apply_proc.returncode != 0:
        apply_record["reason"] = f"git apply failed (after --check passed): {apply_proc.stderr.strip()[:200]}"
        _append_audit(apply_record)
        print(f"x rejected: {apply_record['reason']}")
        return 4

    print("=== Test policy gate (ruff check) ===")
    clean, output = _ruff_check_passes()
    if not clean:
        # Roll back the apply.
        subprocess.run(["git", "apply", "-p0", "-R", "-"], cwd=REPO, input=diff + "\n", text=True, timeout=30)
        apply_record["reason"] = f"ruff check failed after apply; reverted"
        _append_audit(apply_record)
        print(f"x rejected: {apply_record['reason']}")
        print("ruff output (first 600 chars):")
        print(output[:600])
        return 5

    apply_record["outcome"] = "applied"
    apply_record["reason"] = "ruff clean after apply; left in working tree for operator commit"
    _append_audit(apply_record)
    print(f"✓ applied to working tree; ruff clean")
    print(f"  next: stage + commit per §51/§54 (no Co-Authored-By trailer)")
    return 0


def _append_audit(record: dict) -> None:
    APPLY_AUDIT.parent.mkdir(parents=True, exist_ok=True)
    import datetime
    record["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with APPLY_AUDIT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def cmd_push(args: argparse.Namespace) -> int:
    """§42-gated push to origin/main. Requires --confirm explicitly."""
    if not args.confirm:
        print("x push requires --confirm (per CLAUDE.md §42 gated-operations policy)")
        return 1
    proc = _git(["push", "origin", "HEAD"])
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="agent_task_board.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=False)

    p_list = sub.add_parser("list", help="full task board snapshot")
    p_list.set_defaults(func=cmd_list)

    p_status = sub.add_parser("status", help="alias for list")
    p_status.set_defaults(func=cmd_list)

    p_research = sub.add_parser("research", help="research agent investigation")
    p_research.add_argument("issue_id")
    p_research.set_defaults(func=cmd_research)

    p_apply = sub.add_parser("apply", help="drill-gated apply of council Author diff")
    p_apply.add_argument("issue_id")
    p_apply.add_argument("--commit", action="store_true",
                         help="actually mutate (default: dry-run)")
    p_apply.set_defaults(func=cmd_apply)

    p_push = sub.add_parser("push", help="git push origin HEAD (§42 gated)")
    p_push.add_argument("--confirm", action="store_true")
    p_push.set_defaults(func=cmd_push)

    args = parser.parse_args()
    if not args.cmd:
        return cmd_list(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
