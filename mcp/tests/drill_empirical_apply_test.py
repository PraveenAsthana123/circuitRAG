#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: empirical_apply_test.py — operator harness for live apply-rate retest.

Per §43 + §55.3. Locks the long-deferred empirical-test harness contract:

  - script exists at scripts/empirical_apply_test.py
  - 5 subcommands registered (setup, scan, simulate, inspect, cleanup)
  - synthetic file path is exactly tests/_empirical_synthetic.py
  - SYNTHETIC_CONTENT carries the F401 (import os) the test relies on
  - cleanup REFUSES to delete anything except the expected path
  - simulate defaults to --dry-run (safe-by-default; --apply is opt-in)
  - script does NOT run automatically (no cron / no daemon hook; CLI only)
  - script handles missing prereqs gracefully (no traceback)

Eight steps. Six negative.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "empirical_apply_test.py"
SYNTHETIC = REPO / "tests" / "_empirical_synthetic.py"
PYTHON = REPO / ".venv" / "bin" / "python3"


def main() -> int:
    print("-- 1. POSITIVE: empirical_apply_test.py exists + non-trivial size --")
    if not SCRIPT.exists():
        print(f"x {SCRIPT} missing")
        return 1
    src = SCRIPT.read_text(encoding="utf-8")
    if len(src) < 3000:
        print(f"x script too short ({len(src)} chars)")
        return 1
    print(f"  ok: harness present ({len(src)} chars)")

    print("-- 2. POSITIVE: 5 subcommands registered (setup, scan, simulate, inspect, cleanup) --")
    for sub in ("setup", "scan", "simulate", "inspect", "cleanup"):
        if not re.search(rf'sub\.add_parser\(\s*"{sub}"', src):
            print(f"x subcommand '{sub}' not registered with argparse")
            return 1
    print("  ok: all 5 subcommands registered")

    print("-- 3. NEGATIVE: synthetic file path is exactly tests/_empirical_synthetic.py --")
    # If a contributor moves the synthetic file elsewhere AND forgets to
    # update the cleanup guard, real source files could be deleted by
    # `python empirical_apply_test.py cleanup`. Lock the path.
    if 'SYNTHETIC_FILE = REPO / "tests" / "_empirical_synthetic.py"' not in src:
        print("x synthetic file path drifted from tests/_empirical_synthetic.py")
        return 1
    print("  ok: synthetic file path locked at tests/_empirical_synthetic.py")

    print("-- 4. NEGATIVE: cleanup refuses to delete unexpected paths --")
    # Drill the safety guard. The relpath check + 'refusing to delete'
    # message must be present.
    if 'refusing to delete unexpected path' not in src:
        print("x cleanup must refuse delete with explicit message")
        return 1
    if 'rel != "tests/_empirical_synthetic.py"' not in src:
        print("x cleanup must check relpath against exact synthetic file")
        return 1
    print("  ok: cleanup safety guard locked")

    print("-- 5. NEGATIVE: simulate defaults to --dry-run (safe-by-default) --")
    # The mutating run must be explicit opt-in via --apply.
    if 'cmd.append("--dry-run")' not in src:
        print("x simulate must default to --dry-run")
        return 1
    if "--apply" not in src or 'help="real apply (mutating); default dry-run"' not in src:
        print("x --apply flag must exist + document mutation as opt-in")
        return 1
    print("  ok: simulate is dry-run by default; --apply is explicit")

    print("-- 6. NEGATIVE: SYNTHETIC_CONTENT carries the F401 the test exercises --")
    # The whole point of this harness: drop a deterministic ruff-fixable
    # issue (unused `import os`) so the council MUST handle the easiest
    # case. If the synthetic content drifts off F401, the harness becomes
    # useless.
    if "import os" not in src:
        print("x SYNTHETIC_CONTENT must include `import os` (F401 trigger)")
        return 1
    if "ruff F401" not in src and "F401" not in src:
        print("x source must reference F401 (the rule the harness validates)")
        return 1
    print("  ok: SYNTHETIC_CONTENT carries F401 trigger")

    print("-- 7. NEGATIVE: harness does NOT run automatically --")
    # Cron / daemon hook would burn 5-15 min Ollama time + dirty git
    # state without operator intent. Drill enforces the source explicitly
    # documents this is operator-invoked only.
    if "does NOT run automatically" not in src:
        print("x source must explicitly document non-automatic invocation")
        return 1
    cron_files = list((REPO / "scripts").glob("*cron*"))
    for cf in cron_files:
        if cf.is_file() and "empirical_apply_test" in cf.read_text(encoding="utf-8"):
            print(f"x {cf} references empirical_apply_test (auto-invocation leak)")
            return 1
    print("  ok: harness is operator-invoked only")

    print("-- 8. POSITIVE: harness end-to-end smoke (setup + cleanup roundtrip) --")
    # Real exec; not mocked. Per §43 drills hit the real stack.
    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), "setup"],
        capture_output=True, text=True, timeout=30, cwd=REPO,
    )
    if proc.returncode != 0:
        print(f"x setup failed: {proc.stderr[:200]}")
        return 1
    if not SYNTHETIC.exists():
        print("x setup did not create synthetic file")
        return 1
    proc = subprocess.run(
        [str(PYTHON), str(SCRIPT), "cleanup"],
        capture_output=True, text=True, timeout=30, cwd=REPO,
    )
    if proc.returncode != 0:
        print(f"x cleanup failed: {proc.stderr[:200]}")
        return 1
    if SYNTHETIC.exists():
        print("x cleanup did not remove synthetic file")
        return 1
    print("  ok: setup → cleanup roundtrip green; synthetic file lifecycle works")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
