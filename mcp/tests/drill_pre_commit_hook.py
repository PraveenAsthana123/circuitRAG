#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/git-hooks/pre-commit refreshes drill status when stale,
preserves advisory contract.

Phase 5F closes the gap where rule 1 of LoopWatcher kept REJECTing
because the drill_status.json was stale. The pre-commit hook
refreshes it BEFORE the commit lands, so post-commit's rule 1 sees
fresh data.

Eight steps. Six negative assertions.

  1. Hook exists at scripts/git-hooks/pre-commit + executable.
  2. NEGATIVE: NEVER blocks the commit. Drill failures must NOT
     exit non-zero from pre-commit; they land in the status file
     and post-commit's rule 1 decides verdict.
  3. NEGATIVE: skips refresh when status fresh (age < STALE_AFTER).
     Zero cost on rapid commits — operator's velocity matters.
  4. NEGATIVE: refreshes when status missing. Fresh repo on first
     commit needs the seed.
  5. NEGATIVE: refreshes when status stale (age >= STALE_AFTER).
     The whole point of this hook.
  6. NEGATIVE: SKIP_DRILL_STATUS=1 escape hatch present. Operator
     in a hurry can bypass without uninstalling the hook.
  7. NEGATIVE: STALE_AFTER configurable via env var (default 600s).
     Different operators have different drill speeds.
  8. NEGATIVE: invokes write_drill_status.py with --only-readonly
     (tier-1 drills, ~12s wall). Tier-2/3 drills would balloon
     pre-commit time to minutes.

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
HOOK = REPO / "scripts" / "git-hooks" / "pre-commit"

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
    # 1. Hook exists + executable
    step("1. pre-commit hook exists at scripts/git-hooks/pre-commit + +x")
    if not HOOK.exists():
        fail(f"missing: {HOOK}")
    if not os.access(HOOK, os.X_OK):
        fail(f"not executable: {HOOK}")
    text = HOOK.read_text()
    if len(text) < 500:
        fail(f"hook too short: {len(text)} chars")
    ok(f"pre-commit hook exists ({len(text)} chars), +x set")

    # 2. NEVER blocks commit
    step("2. NEGATIVE: hook NEVER blocks commit (advisory contract)")
    # Final exit must be 0
    if not text.rstrip().endswith("exit 0"):
        fail(
            "hook doesn't end with `exit 0`. Pre-commit hooks that "
            "exit non-zero block the commit; this hook is advisory."
        )
    # write_drill_status invocation must be wrapped in `|| true`
    # so its non-zero exit doesn't propagate to the hook's exit.
    if "|| true" not in text:
        fail(
            "drill refresh isn't wrapped in `|| true`. A failed drill "
            "would set the hook's exit to non-zero and BLOCK the "
            "commit — wrong layer for that decision (post-commit "
            "watcher's rule 1 owns it)."
        )
    ok("hook ends `exit 0`; write_drill_status wrapped in `|| true`")

    # 3. Skips refresh when fresh
    step("3. NEGATIVE: skips refresh when status fresh (age < STALE_AFTER)")
    # Look for the freshness check pattern: age < STALE_AFTER -> exit 0
    if not re.search(r'\$age.+\$STALE_AFTER.+exit 0', text, re.DOTALL):
        # Try a more lenient pattern
        if "age" not in text or "STALE_AFTER" not in text:
            fail(
                "no freshness check (age vs STALE_AFTER). Without it, "
                "every commit pays the ~12s drill cost — operator "
                "velocity destroyed."
            )
    if "exit 0" not in text:
        fail("no early-exit on freshness")
    ok("freshness check + early-exit present")

    # 4. Refreshes when missing
    step("4. NEGATIVE: refreshes when status file missing")
    if "[ -f \"$STATUS\" ]" not in text and "[ -f $STATUS ]" not in text:
        fail("no `if [ -f ... ]` check on status file existence")
    if "drill status missing" not in text and "drill suite" not in text:
        fail("no message for the missing-file case")
    ok("missing-file case handled")

    # 5. Refreshes when stale
    step("5. NEGATIVE: refreshes when status stale (age >= STALE_AFTER)")
    # The synchronous refresh path runs write_drill_status.py
    if "write_drill_status.py" not in text:
        fail("doesn't invoke write_drill_status.py for refresh")
    ok("stale path invokes write_drill_status.py")

    # 6. SKIP_DRILL_STATUS escape hatch
    step("6. NEGATIVE: SKIP_DRILL_STATUS env-var escape hatch")
    if "SKIP_DRILL_STATUS" not in text:
        fail(
            "no SKIP_DRILL_STATUS escape hatch. Operator in a "
            "hurry must be able to bypass without uninstalling "
            "the hook."
        )
    if not re.search(r'SKIP_DRILL_STATUS.+exit 0', text, re.DOTALL):
        fail("SKIP_DRILL_STATUS path doesn't early-exit")
    ok("SKIP_DRILL_STATUS bypass present + exits early")

    # 7. STALE_AFTER configurable
    step("7. NEGATIVE: STALE_AFTER configurable via env (default 600s)")
    if 'STALE_AFTER="${STALE_AFTER:-600}"' not in text and \
       "STALE_AFTER=${STALE_AFTER:-600}" not in text:
        fail(
            "STALE_AFTER not env-configurable with a default. "
            "Different drill speeds need different freshness "
            "windows."
        )
    ok("STALE_AFTER configurable via env; default 600s")

    # 8. --only-readonly tier-1 drills
    step("8. NEGATIVE: invokes drills with --only-readonly (tier-1 only)")
    if "--only-readonly" not in text:
        fail(
            "doesn't pass --only-readonly to write_drill_status.py. "
            "Without it, tier-2/3 drills run too — would balloon "
            "pre-commit time from ~12s to minutes (Postgres + Kafka "
            "+ MCP servers etc.)."
        )
    ok("--only-readonly tier-1 scoping enforced")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 PRE-COMMIT-HOOK STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
