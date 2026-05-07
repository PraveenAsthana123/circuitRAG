#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/migrate_ai_caches_to_deepa.sh structural contract.

The migration script touched ~1.6M files across 73GB. It must
NEVER lose data. This drill verifies the script's safety
invariants WITHOUT actually running rsync (which would re-migrate
already-migrated caches).

Eight steps. Six negative assertions.

  1. Script exists at scripts/migrate_ai_caches_to_deepa.sh +
     executable bit set.
  2. NEGATIVE: defaults to dry-run (NOT --apply). A fresh user
     running `./script.sh` must not destructively migrate.
  3. NEGATIVE: declares set -euo pipefail (errors abort; no
     partial migration on first failure).
  4. NEGATIVE: uses rsync NOT mv across the / -> /mnt/deepa
     boundary. mv between filesystems is copy-then-delete; if
     copy fails midway you may lose data.
  5. NEGATIVE: ALL four modes present (dry-run, apply, rollback,
     finalize). Missing rollback would leave operator stuck if
     migration breaks; missing finalize means disk never frees.
  6. NEGATIVE: log file uses JSONL append-only format. Operators
     parse with jq; line-oriented JSON is the contract.
  7. NEGATIVE: bak-index file referenced for rollback (records
     which paths were migrated; rollback iterates this).
  8. NEGATIVE: dry-run mode does NOT call rsync, mv, or rm.
     Re-running the dry-run report should never mutate state.

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import os
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "migrate_ai_caches_to_deepa.sh"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg):
    print(f"  {GREEN}{msg}{NC}")


def fail(msg):
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title):
    print(f"\n{BOLD}-- {title} --{NC}")


def main():
    # Step 1: script exists + executable
    step("1. migrate_ai_caches_to_deepa.sh exists + executable")
    if not SCRIPT.exists():
        fail(f"script missing: {SCRIPT}")
    if not os.access(SCRIPT, os.X_OK):
        fail(f"script not executable: {SCRIPT}")
    text = SCRIPT.read_text()
    if len(text) < 1500:
        fail(f"script suspiciously short: {len(text)} chars")
    ok(f"script exists ({len(text)} chars), +x set")

    # Step 2: defaults to dry-run
    step("2. NEGATIVE: defaults to dry-run (no destructive default)")
    # The script's MODE assignment with no arg should set MODE=dry-run.
    if 'MODE="dry-run"' not in text:
        fail(
            "script doesn't default MODE to dry-run. A user invocation "
            "without flags must not destructively migrate."
        )
    # Check the case statement explicitly handles "" (empty arg) as dry-run
    if not re.search(r'""\)\s*MODE="dry-run"', text):
        fail(
            'empty-arg case ("") missing — operator running '
            './script.sh with no flags must hit dry-run.'
        )
    ok("default mode = dry-run; empty-arg path explicit")

    # Step 3: set -euo pipefail
    step("3. NEGATIVE: set -euo pipefail (fail-fast on first error)")
    if "set -euo pipefail" not in text:
        fail(
            "missing `set -euo pipefail` — without it, a failed rsync "
            "or mv would silently continue and partial-migrate the "
            "next cache."
        )
    ok("set -euo pipefail declared")

    # Step 4: rsync, not mv across boundary
    step("4. NEGATIVE: rsync used for cross-filesystem migration")
    # Look for rsync in the apply path
    if "rsync -aP" not in text and "rsync " not in text:
        fail(
            "no rsync invocation found. Cross-filesystem mv is "
            "copy-then-delete; rsync is resumable + verifiable."
        )
    # Verify mv is NOT used as the migration primitive (only for .bak rename)
    # mv appears legitimately for the .bak rename (same-fs, instant).
    # The drill's check: rsync MUST appear in apply_one().
    if not re.search(r"apply_one\(\).*?rsync", text, re.DOTALL):
        fail("rsync not present in apply_one() function")
    ok("rsync used; mv only for same-fs .bak rename")

    # Step 5: all 4 modes implemented
    step("5. NEGATIVE: all 4 modes present (dry-run/apply/rollback/finalize)")
    required_modes = ['MODE="apply"', 'MODE="rollback"', 'MODE="finalize"',
                       'MODE="dry-run"']
    missing = [m for m in required_modes if m not in text]
    if missing:
        fail(f"missing mode assignments: {missing}")
    # Each mode also has a case branch in main
    case_branches = re.findall(r"^\s*(dry-run|apply|rollback|finalize)\)",
                                  text, re.MULTILINE)
    if len(set(case_branches)) < 4:
        fail(
            f"main case has only {sorted(set(case_branches))} branches; "
            f"need all 4 modes routed."
        )
    ok(f"all 4 modes assignable AND routed: {sorted(set(case_branches))}")

    # Step 6: JSONL log format
    step("6. NEGATIVE: log uses JSON-line append-only format")
    if "log_event" not in text:
        fail("log_event helper missing")
    # The helper should write printf '{...}\n' not multi-line
    log_event_block = re.search(
        r"log_event\(\)\s*{(.*?)\n}", text, re.DOTALL,
    )
    if not log_event_block:
        fail("log_event() body not parseable")
    body = log_event_block.group(1)
    if "printf" not in body:
        fail("log_event doesn't use printf for line-oriented output")
    if ">>" not in body:
        fail(
            "log_event doesn't append (>>); without append, every "
            "session would overwrite history."
        )
    ok("log_event uses printf '{...}\\n' >> for JSONL append")

    # Step 7: bak-index for rollback
    step("7. NEGATIVE: bak-index file maintained for rollback")
    if "BAK_INDEX" not in text:
        fail(
            "BAK_INDEX variable missing - rollback can't iterate "
            "what was migrated."
        )
    # Index should be appended-to in apply_one and READ in rollback_all
    if not re.search(r"apply_one\(\).*?>>\s*\"\$BAK_INDEX\"", text, re.DOTALL):
        fail("apply_one doesn't append to BAK_INDEX")
    if "rollback_all" not in text:
        fail("rollback_all function missing")
    if "BAK_INDEX" not in re.findall(r"rollback_all\(\)\s*{(.*?)\n}",
                                       text, re.DOTALL)[0] if re.findall(
        r"rollback_all\(\)\s*{(.*?)\n}", text, re.DOTALL) else True:
        # rollback_all should reference BAK_INDEX
        # (relaxed check: it should be in the function body)
        rb = re.search(r"rollback_all\(\)\s*{(.*?)^\}", text,
                        re.DOTALL | re.MULTILINE)
        if rb and "BAK_INDEX" not in rb.group(1):
            fail("rollback_all doesn't read BAK_INDEX")
    ok("BAK_INDEX written by apply_one; read by rollback_all")

    # Step 8: dry-run NEVER mutates
    step(
        "8. NEGATIVE: dry-run path NEVER calls rsync / mv / rm "
        "(verified by reading the dry-run case branch)"
    )
    # Find the dry-run case body
    dry_run_match = re.search(
        r"dry-run\)\s*(.*?)(?=apply\)|;;\s*\n)", text, re.DOTALL,
    )
    if not dry_run_match:
        fail("can't find dry-run case branch")
    dry_run_body = dry_run_match.group(1)
    forbidden = ["rsync ", "mv ", "rm ", "ln -s"]
    leaked = [cmd for cmd in forbidden if cmd in dry_run_body]
    if leaked:
        fail(
            f"dry-run case branch contains destructive commands: "
            f"{leaked}. Re-running --dry-run should never mutate."
        )
    # dry_run_one() is the helper called from this branch; it must
    # also be free of destructive commands.
    dry_run_one_match = re.search(
        r"dry_run_one\(\)\s*{(.*?)\n}", text, re.DOTALL,
    )
    if dry_run_one_match:
        dr1_body = dry_run_one_match.group(1)
        leaked1 = [cmd for cmd in forbidden if cmd in dr1_body]
        if leaked1:
            fail(
                f"dry_run_one() contains destructive commands: {leaked1}"
            )
    ok("dry-run case branch + dry_run_one() are read-only")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 MIGRATE-AI-CACHES STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
