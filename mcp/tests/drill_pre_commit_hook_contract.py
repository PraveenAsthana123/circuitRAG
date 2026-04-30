#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/git-hooks/pre-commit honors the structural contract.

Phase 7MM extended the hook's HIGH_BLAST_RADIUS pattern to include
mcp/tests/drill_*.py — drill edits now force a drill_status refresh
on commit, breaking the 3-REJECT stale-snapshot pattern that hit
Phases 7JJ/7KK/7LL.

Without a drill, the hook's pattern is forward-looking-check-prone
per ADR-017: a future operator could "simplify" the regex back to
the pre-7MM shape and the regression returns silently. This drill
locks the structural contract so any narrowing of the pattern
fires immediately.

Seven steps. Five negative assertions.

  1. POSITIVE: pre-commit hook file exists at canonical path.
  2. NEGATIVE: file is executable (else git won't run it).
  3. NEGATIVE: HIGH_BLAST_RADIUS regex contains all required
     pattern fragments — sidecar/, mcp/server, sidecar-advisor/,
     mcp/tests/drill_ (Phase 7MM addition). Removing any one
     reverts the regression Phase 5Y or 7MM closed.
  4. NEGATIVE: hook calls write_drill_status.py with
     --only-readonly (the canonical refresh invocation).
  5. NEGATIVE: hook always exits 0 (`exit 0` at end). ADR-014's
     advisory contract: pre-commit never blocks the commit.
  6. NEGATIVE: hook respects SKIP_DRILL_STATUS env override
     (operator escape hatch from Phase 5F).
  7. POSITIVE: emit pattern + summary for operator visibility.

Run: python3 mcp/tests/drill_pre_commit_hook_contract.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "scripts" / "git-hooks" / "pre-commit"

REQUIRED_PATTERN_FRAGMENTS = (
    "services/frontend/app/admin/sidecar/",  # Phase 5Y original
    r"mcp/server.*\.py",                     # Phase 5Y original
    "services/sidecar-advisor/",             # Phase 5Y original
    r"mcp/tests/drill_.*\.py",               # Phase 7MM addition
)

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}{msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}-- {title} --{NC}")


def main() -> int:
    step("1. POSITIVE: pre-commit hook file exists")
    if not HOOK.is_file():
        fail(f"hook missing at {HOOK}")
    body = HOOK.read_text()
    ok(f"hook present ({len(body):,} bytes)")

    step("2. NEGATIVE: hook file is executable")
    mode = HOOK.stat().st_mode
    if not (mode & 0o111):  # any execute bit
        fail(f"hook not executable (mode = {oct(mode)}). chmod +x.")
    ok(f"hook executable (mode = {oct(mode)[-3:]})")

    step("3. NEGATIVE: HIGH_BLAST_RADIUS regex contains all required fragments")
    # Find the grep -qE pattern line
    grep_line = None
    for line in body.splitlines():
        if "grep -qE" in line and "^(" in line:
            grep_line = line
            break
    if not grep_line:
        fail("could not locate `grep -qE '^(...)'` pattern line in hook")
    missing_fragments = [
        frag for frag in REQUIRED_PATTERN_FRAGMENTS
        if frag not in grep_line
    ]
    if missing_fragments:
        fail(
            f"{len(missing_fragments)} required pattern fragment(s) "
            f"missing from HIGH_BLAST_RADIUS regex: {missing_fragments}. "
            "Pre-commit refresh won't fire on those file types; "
            "regression risk per Phase 5Y / 7MM."
        )
    ok(
        f"all {len(REQUIRED_PATTERN_FRAGMENTS)} required fragments present "
        f"in HIGH_BLAST_RADIUS regex"
    )

    step("4. NEGATIVE: hook invokes write_drill_status.py --only-readonly")
    if "write_drill_status.py" not in body:
        fail("hook does not call write_drill_status.py — refresh broken")
    if "--only-readonly" not in body:
        fail("hook missing --only-readonly flag — would refresh full catalog")
    ok("hook calls write_drill_status.py --only-readonly")

    step("5. NEGATIVE: hook always exits 0 (advisory contract per ADR-014)")
    # The hook should have an `exit 0` at the end (not just an
    # implicit successful exit). Catches accidental `exit 1` insertion.
    last_lines = body.rstrip().splitlines()[-5:]
    has_exit_zero = any(re.match(r"^\s*exit\s+0\s*$", ln) for ln in last_lines)
    if not has_exit_zero:
        fail(
            f"no explicit `exit 0` in last 5 lines of hook. ADR-014's "
            "advisory contract requires the hook to never block the "
            "commit; explicit exit 0 makes that intent visible."
        )
    ok("hook ends with explicit `exit 0`")

    step("6. NEGATIVE: SKIP_DRILL_STATUS env override is respected")
    if "SKIP_DRILL_STATUS" not in body:
        fail(
            "hook missing SKIP_DRILL_STATUS env-var check — operator "
            "escape hatch from Phase 5F broken."
        )
    # Verify the check actually exits early.
    if not re.search(r'SKIP_DRILL_STATUS[^}\n]*\}.*\n.*exit\s+0', body, re.DOTALL):
        # Alternative pattern: bash conditional + exit
        if not re.search(r"if.*SKIP_DRILL_STATUS.*then\s*\n\s*exit", body, re.DOTALL):
            fail(
                "SKIP_DRILL_STATUS referenced but doesn't trigger early "
                "exit. Operator escape hatch incomplete."
            )
    ok("SKIP_DRILL_STATUS env override exits early")

    step("7. POSITIVE: emit pattern + summary")
    # Extract the actual regex from the hook for visibility.
    pattern_match = re.search(r"grep -qE '\^\(([^']+)\)'", grep_line)
    pattern = pattern_match.group(1) if pattern_match else "(unparseable)"
    line_count = len(body.splitlines())
    ok(
        f"hook: {line_count} lines; HIGH_BLAST_RADIUS pattern: "
        f"{pattern[:80]}{'...' if len(pattern) > 80 else ''}"
    )
    ok(
        f"required fragments: {len(REQUIRED_PATTERN_FRAGMENTS)} present; "
        "advisory contract honored (exits 0); refresh wired"
    )

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 7 PRE-COMMIT-HOOK-CONTRACT STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 2, 3, 4, 5, 6){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
