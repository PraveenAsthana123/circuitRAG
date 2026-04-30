#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: pre-commit hook surfaces drill failures when high-blast-radius
files are staged (Phase 5Y).

Phase 5F's pre-commit hook refreshes drill status. Phase 5S landed
with two pre-existing drill assertions silently failing; the verdict
log caught it but I missed the warning during iteration reporting.
Phase 5Y makes the warning LOUD: when staged changes touch a
high-blast-radius surface (frontend sidecar/, MCP servers, sidecar-
advisor/), the hook prints a banner naming the failing drills BEFORE
the commit lands.

The hook still exits 0 (advisory contract per ADR-014). The goal is
SURFACING signal, not blocking — operators see the warning and decide.

Eight steps. Six negative assertions.

  1. POSITIVE: hook file exists; size grew vs Phase 5F baseline
     (we added a meaningful detection block, not a one-line tweak).
  2. NEGATIVE: HIGH_BLAST_RADIUS regex covers all three surfaces:
     services/frontend/app/admin/sidecar/, mcp/server*.py,
     services/sidecar-advisor/. Without all three, classes of
     regression go uncaught.
  3. NEGATIVE: HIGH_BLAST_RADIUS regex does NOT match unrelated
     paths (docs/, README, generic scripts). Over-broad matching
     would force expensive sweeps on every commit, defeating 5F.
  4. NEGATIVE: when HBR is set, the staleness cache check is
     BYPASSED (force-refresh). Without this, an HBR commit within
     the staleness window gets the cached status and misses fresh
     regressions.
  5. NEGATIVE: warning banner uses === lines + lists failing drill
     names, one per line. Without this shape, the warning blends
     into other stderr output and operators miss it.
  6. NEGATIVE: SKIP_DRILL_STATUS escape hatch still works. The
     5Y additions must NOT silently bypass operator overrides.
  7. NEGATIVE: hook ALWAYS exits 0 (no `exit 1` paths added).
     Adding a non-zero exit on drill failure would break the
     advisory contract and shift the gate from LoopWatcher to
     the hook — wrong layer.
  8. POSITIVE: end-to-end — invoke the hook against the live repo
     with no staged changes (clean state) and verify it exits 0.

Run: python3 mcp/tests/drill_pre_commit_high_blast_radius.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "scripts" / "git-hooks" / "pre-commit"


def main() -> int:
    if not HOOK.exists():
        print(f"✗ pre-step: {HOOK} missing")
        return 1
    body = HOOK.read_text()

    # ── Step 1: hook exists and grew vs Phase 5F baseline ──
    line_count = len(body.splitlines())
    if line_count < 80:
        print(f"✗ step 1: hook is {line_count} lines; 5Y additions should "
              "have grown it past 80 lines")
        return 1
    if "Phase 5Y" not in body:
        print(f"✗ step 1: hook missing 'Phase 5Y' citation in header")
        return 1
    print(f"✓ step 1: hook exists, {line_count} lines, cites Phase 5Y")

    # ── Step 2: NEGATIVE — HBR regex covers all required surfaces ──
    # Phase 7MM extended the pattern to include drill catalog edits;
    # all of these paths must match the regex (any miss = regression
    # class uncaught).
    hbr_match_targets = [
        "services/frontend/app/admin/sidecar/page.tsx",
        "services/frontend/app/admin/sidecar/deep/page.tsx",
        "services/frontend/app/admin/sidecar/telemetry/page.tsx",
        "mcp/server_drills.py",
        "mcp/server.py",
        "services/sidecar-advisor/advisor.py",
        "services/sidecar-advisor/git_capture.py",
        # Phase 7MM: drill catalog edits trigger refresh (closes the
        # 3-REJECT stale-snapshot pattern from Phase 7JJ/7KK/7LL).
        "mcp/tests/drill_example.py",
        "mcp/tests/drill_adr020_audit_cadence.py",
    ]
    # Extract the regex string from the hook body.
    regex_match = re.search(
        r"grep -qE '\^\(([^)]+)\)'",
        body,
    )
    if not regex_match:
        print("✗ step 2: HBR regex pattern not found in hook")
        return 1
    pattern_body = regex_match.group(1)
    # Build a Python regex from the bash one for testing
    py_re = re.compile(rf"^({pattern_body})")
    for target in hbr_match_targets:
        if not py_re.match(target):
            print(f"✗ step 2: HBR regex doesn't match {target!r}; "
                  "regression class uncaught")
            return 1
    print(f"✓ step 2: HBR regex matches all {len(hbr_match_targets)} "
          "high-blast-radius surfaces")

    # ── Step 3: NEGATIVE — regex doesn't match unrelated paths ──
    # Phase 7MM removed `mcp/tests/drill_x.py` from this safe list
    # (drill catalog edits SHOULD now trigger HBR — see step 2).
    # Other test files outside drill_*.py (e.g. audit_*.py, .test.ts)
    # remain safe-by-design.
    safe_targets = [
        "docs/NEXT_POLICY.md",
        "README.md",
        "scripts/utils/something.py",
        "mcp/tests/audit_x.py",          # audit_*.py is non-gating per ADR-018
        "mcp/tests/conftest.py",         # pytest config, not a drill
        "services/frontend/app/page.tsx",  # outside sidecar/
        "services/frontend/styles/globals.css",
    ]
    for target in safe_targets:
        if py_re.match(target):
            print(f"✗ step 3: HBR regex over-matches {target!r}; "
                  "would force expensive sweeps on unrelated commits")
            return 1
    print(f"✓ step 3: HBR regex does NOT match {len(safe_targets)} unrelated paths")

    # ── Step 4: NEGATIVE — HBR bypasses staleness cache ──
    # Look for the conditional structure: when HBR=1, the staleness
    # check is bypassed. The bash uses `[ "$HIGH_BLAST_RADIUS" -eq 0 ] && [ -f "$STATUS" ]`
    # so HBR=1 short-circuits the early-exit check.
    if not re.search(r'HIGH_BLAST_RADIUS"\s*-eq\s*0', body):
        print("✗ step 4: HBR=0 short-circuit guard missing from staleness check; "
              "an HBR commit could get the cached status and miss regressions")
        return 1
    # And the message branch must explicitly cite HBR
    if not re.search(r"high-blast-radius staged files; forcing drill refresh",
                     body):
        print("✗ step 4: missing the 'forcing drill refresh' message that "
              "tells the operator WHY the cache was bypassed")
        return 1
    print("✓ step 4: HBR=1 bypasses staleness cache (forces fresh refresh)")

    # ── Step 5: NEGATIVE — warning banner shape ──
    # The warning must be visually distinct: ==== lines + drill names
    # one per line. Operators scrolling past stderr should NOT miss it.
    if "============================================" not in body:
        print("✗ step 5: warning banner missing === separator lines")
        return 1
    if not re.search(r'WARNING.*drill failures', body):
        print("✗ step 5: warning text doesn't say 'WARNING' + 'drill failures'")
        return 1
    # Drill names should be printed one per line (newline-separated)
    if not re.search(r"tr ',' '\\n'", body):
        print("✗ step 5: drill names not split per-line for visibility")
        return 1
    print("✓ step 5: warning has === banner + WARNING text + per-line drill names")

    # ── Step 6: NEGATIVE — SKIP_DRILL_STATUS escape preserved ──
    # The escape hatch must run BEFORE the HBR detection so an
    # operator's override actually overrides everything.
    skip_check_idx = body.find('SKIP_DRILL_STATUS')
    hbr_check_idx = body.find('HIGH_BLAST_RADIUS=0')
    if skip_check_idx < 0:
        print("✗ step 6: SKIP_DRILL_STATUS check missing")
        return 1
    if hbr_check_idx < 0:
        print("✗ step 6: HIGH_BLAST_RADIUS init missing")
        return 1
    if skip_check_idx > hbr_check_idx:
        print("✗ step 6: SKIP_DRILL_STATUS check appears AFTER HBR detection; "
              "operator escape might be partially bypassed")
        return 1
    # And the SKIP path must `exit 0` (not silent fall-through)
    skip_block = body[skip_check_idx:hbr_check_idx]
    if "exit 0" not in skip_block:
        print("✗ step 6: SKIP_DRILL_STATUS branch doesn't exit 0; "
              "could fall through to HBR detection")
        return 1
    print("✓ step 6: SKIP_DRILL_STATUS check runs before HBR + exits 0")

    # ── Step 7: NEGATIVE — hook ALWAYS exits 0 ──
    # Find every `exit N` in the hook body. None should be `exit 1`
    # or `exit 2`. The hook is advisory — non-zero would break the
    # contract and block commits, shifting the gate from LoopWatcher
    # to the hook (wrong layer).
    exit_codes = re.findall(r"^\s*exit\s+(\d+)", body, re.MULTILINE)
    bad = [c for c in exit_codes if c not in ("0",)]
    if bad:
        print(f"✗ step 7: hook contains non-zero exits {bad}; "
              "advisory contract broken (LoopWatcher should gate, not hook)")
        return 1
    if not exit_codes:
        print("✗ step 7: hook contains zero `exit` statements; missing fallthrough exit")
        return 1
    print(f"✓ step 7: all {len(exit_codes)} exit statements are `exit 0` "
          "(advisory contract preserved)")

    # ── Step 8: POSITIVE — invoke hook against live repo ──
    # Run with SKIP_DRILL_STATUS=1 so the drill doesn't actually fire
    # the full sweep (we just want to verify the hook exits 0).
    env = os.environ.copy()
    env["SKIP_DRILL_STATUS"] = "1"
    try:
        proc = subprocess.run(
            ["bash", str(HOOK)],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=30.0,
        )
    except subprocess.TimeoutExpired:
        print("✗ step 8: hook timed out (>30s); shouldn't happen with "
              "SKIP_DRILL_STATUS=1")
        return 1
    if proc.returncode != 0:
        print(f"✗ step 8: hook exit {proc.returncode}, expected 0\n"
              f"stderr: {proc.stderr}")
        return 1
    print(f"✓ step 8: hook exits 0 with SKIP_DRILL_STATUS=1 (in-repo invocation)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
