#!/usr/bin/env python3
"""Empirical apply-rate test harness — runs council on synthetic broken file.

Per §55.3 (apply-rate as outcome contract). The deferred-30+-iterations
empirical test, now durable as a script operators can invoke.

Operator workflow:
    bash scripts/run.sh check   # confirm Ollama + council models loaded
    python scripts/empirical_apply_test.py setup
    python scripts/empirical_apply_test.py scan
    python scripts/empirical_apply_test.py simulate --max-cycles 1
    # ... wait 5-15 min for council to run on the synthetic issue
    python scripts/empirical_apply_test.py inspect    # show result
    python scripts/empirical_apply_test.py cleanup    # remove synthetic file

Subcommands:
    setup   — create tests/_empirical_synthetic.py with known F401 issue
    scan    — run issue_scanner.py to populate checklist
    simulate — run daemon dry-run (or --apply for live)
    inspect — read .loop/agent_task_board_apply.jsonl tail
    cleanup — remove synthetic file (does NOT remove audit rows)

Safety:
    - synthetic file is at tests/_empirical_synthetic.py (under tests/;
      not imported by production code)
    - cleanup is `git restore` on the synthetic file path; never deletes
      anything not under that exact path
    - simulate runs `bash scripts/run.sh fix-dry` by default (no
      mutation); `--apply` flag escalates to mutating run

This script does NOT run automatically. Operators invoke it for
on-demand empirical validation. CI gates use the drill, not this
script.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SYNTHETIC_FILE = REPO / "tests" / "_empirical_synthetic.py"
PYTHON = REPO / ".venv" / "bin" / "python3"
APPLY_LOG = REPO / ".loop" / "agent_task_board_apply.jsonl"

# Synthetic content — known F401 unused import that ruff:autofix
# can deterministically remove. Used as the EASIEST possible
# test case: if the daemon fails on this, council quality is the
# blocker (not edge cases).
SYNTHETIC_CONTENT = '''"""Synthetic test file — deliberately broken to validate apply rate.

Per scripts/empirical_apply_test.py. NOT imported by production code.
Cleanup with: python scripts/empirical_apply_test.py cleanup
"""

# Deliberately-introduced unused import (ruff F401). Easiest fix: remove.
import os  # noqa: F401 — drill-injected for empirical retest


def hello() -> str:
    return "hi"
'''


def cmd_setup(_args: argparse.Namespace) -> int:
    """Create the synthetic broken file."""
    SYNTHETIC_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SYNTHETIC_FILE.exists():
        print(f"  note: {SYNTHETIC_FILE} already exists; overwriting")
    # Strip the noqa comment so ruff actually flags it
    content = SYNTHETIC_CONTENT.replace("  # noqa: F401 — drill-injected for empirical retest", "")
    SYNTHETIC_FILE.write_text(content, encoding="utf-8")
    print(f"  ok: created {SYNTHETIC_FILE}")
    print(f"  ok: file size {SYNTHETIC_FILE.stat().st_size} bytes")
    print(f"  next: python scripts/empirical_apply_test.py scan")
    return 0


def cmd_scan(_args: argparse.Namespace) -> int:
    """Run issue_scanner.py to populate checklist."""
    if not SYNTHETIC_FILE.exists():
        print(f"x synthetic file missing — run setup first")
        return 1
    scanner = Path.home() / ".claude" / "scripts" / "issue_scanner.py"
    if not scanner.exists():
        print(f"x scanner missing: {scanner}")
        return 1
    print(f"  running: {scanner}")
    proc = subprocess.run(
        [str(PYTHON), str(scanner), "--repo", "."],
        cwd=REPO, capture_output=True, text=True, timeout=120,
    )
    print(f"  exit={proc.returncode}")
    if proc.returncode != 0:
        print(f"  stderr: {proc.stderr[:300]}")
        return 1
    # Show whether our synthetic issue made it into the checklist
    checklist = REPO / ".loop" / "issue_checklist.jsonl"
    if checklist.exists():
        synthetic_count = 0
        for line in checklist.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if "_empirical_synthetic" in row.get("file", ""):
                    synthetic_count += 1
            except json.JSONDecodeError:
                continue
        print(f"  synthetic issues in checklist: {synthetic_count}")
    print(f"  next: python scripts/empirical_apply_test.py simulate --max-cycles 1")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    """Run the daemon for N cycles (dry-run by default)."""
    daemon = REPO / "scripts" / "autonomous_fix_daemon.py"
    if not daemon.exists():
        print(f"x daemon missing: {daemon}")
        return 1
    # Empirical retest only needs F401 detection on the synthetic file;
    # mypy/bandit/eslint full-scan can exceed 600s and timeout the daemon.
    # Per docs/architecture/empirical-retest-2026-05-04-scanner-timeout.md.
    cmd = [
        str(PYTHON), str(daemon),
        "--max-cycles", str(args.max_cycles),
        "--scan-fast",
        "--scan-paths", "tests/_empirical_synthetic.py",
    ]
    if not args.apply:
        cmd.append("--dry-run")
    print(f"  running: {' '.join(cmd)}")
    print(f"  expected wall time: 1-3 min per cycle (ruff-only scan + Ollama council)")
    started = time.time()
    proc = subprocess.run(cmd, cwd=REPO, capture_output=False, text=True)
    elapsed = time.time() - started
    print(f"  exit={proc.returncode}; elapsed {elapsed:.1f}s")
    if proc.returncode != 0:
        return 1
    print(f"  next: python scripts/empirical_apply_test.py inspect")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    """Read the apply log tail to see what happened."""
    if not APPLY_LOG.exists():
        print(f"  no apply log yet: {APPLY_LOG}")
        return 0
    rows = []
    for line in APPLY_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not rows:
        print(f"  apply log empty")
        return 0
    tail = rows[-args.limit:]
    print(f"  last {len(tail)} apply attempts:")
    applied = sum(1 for r in tail if r.get("outcome") == "applied")
    rejected = sum(1 for r in tail if r.get("outcome") == "rejected")
    drill_failed = sum(1 for r in tail if r.get("outcome") == "drill_failed")
    errored = sum(1 for r in tail if r.get("outcome") == "errored")
    rate = applied / max(len(tail), 1)
    print(f"  applied={applied}  rejected={rejected}  drill_failed={drill_failed}  errored={errored}")
    print(f"  apply rate (last {len(tail)}): {rate:.1%}")
    print()
    print("  Recent rows:")
    for r in tail[-5:]:
        outcome = r.get("outcome", "?")
        issue_id = r.get("id", "?")[:50]
        reason = (r.get("reason", "") or "")[:80]
        print(f"    {outcome:<14} {issue_id}")
        if reason:
            print(f"    reason: {reason}")
    return 0


def cmd_cleanup(_args: argparse.Namespace) -> int:
    """Remove the synthetic file (safe path-only delete)."""
    if not SYNTHETIC_FILE.exists():
        print(f"  note: {SYNTHETIC_FILE} already gone")
        return 0
    # Guard: only delete if path is exactly the expected synthetic file
    rel = SYNTHETIC_FILE.relative_to(REPO).as_posix()
    if rel != "tests/_empirical_synthetic.py":
        print(f"x refusing to delete unexpected path: {rel}")
        return 1
    SYNTHETIC_FILE.unlink()
    print(f"  ok: removed {SYNTHETIC_FILE}")
    print(f"  note: audit rows in .loop/*.jsonl are preserved")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="empirical_apply_test")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="Create synthetic broken file")
    sub.add_parser("scan", help="Run issue_scanner.py")

    p_sim = sub.add_parser("simulate", help="Run daemon for N cycles")
    p_sim.add_argument("--max-cycles", type=int, default=1)
    p_sim.add_argument("--apply", action="store_true", help="real apply (mutating); default dry-run")

    p_ins = sub.add_parser("inspect", help="Read apply log tail")
    p_ins.add_argument("--limit", type=int, default=20)

    sub.add_parser("cleanup", help="Remove synthetic file")

    args = parser.parse_args()

    cmds = {
        "setup": cmd_setup,
        "scan": cmd_scan,
        "simulate": cmd_simulate,
        "inspect": cmd_inspect,
        "cleanup": cmd_cleanup,
    }
    return cmds[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
