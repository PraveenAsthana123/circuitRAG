#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: write_drill_status.py uses the same interpreter + PYTHONPATH
contract as run_drills.py.

Phase 5G fix: pre-commit was firing write_drill_status with
sys.executable (system Python) which doesn't have documind_core.
Drills like drill_tool_catalog_ttl import from mcp/ which needs
documind_core - they failed when run by write_drill_status but
passed via run_drills (which uses /tmp/documind-venv/bin/python +
PYTHONPATH=REPO).

This drill locks the convention so a future refactor doesn't drift
back to sys.executable.

Eight steps. Six negative assertions.

  1. write_drill_status.py exists.
  2. NEGATIVE: declares PY_BIN constant resolving the venv first
     (matches run_drills.py).
  3. NEGATIVE: PY_BIN can be overridden via PYTHON_BIN env var
     (operator escape hatch).
  4. NEGATIVE: PY_BIN falls back to sys.executable when venv
     missing (no crash on fresh box).
  5. NEGATIVE: subprocess.run uses PY_BIN, NOT sys.executable.
     The bug was specifically using sys.executable.
  6. NEGATIVE: PYTHONPATH=REPO is in the subprocess env so
     `from mcp import` and `from documind_core import` resolve.
  7. NEGATIVE: PYTHONPATH is PREPENDED (not replaced) so any
     existing PYTHONPATH the operator set remains effective.
  8. NEGATIVE: PY_BIN is /tmp/documind-venv/bin/python by
     default (matches run_drills's default).

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "write_drill_status.py"

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
    # 1. exists
    step("1. write_drill_status.py exists")
    if not SCRIPT.exists():
        fail(f"missing: {SCRIPT}")
    text = SCRIPT.read_text()
    ok(f"script present ({len(text)} chars)")

    # 2. PY_BIN constant
    step("2. NEGATIVE: declares PY_BIN constant (matches run_drills.py)")
    if "PY_BIN" not in text:
        fail(
            "no PY_BIN constant. The script must agree with "
            "run_drills.py on which Python interpreter runs the "
            "drills, or pre-commit fires drills with the wrong "
            "interpreter and gets ModuleNotFoundError."
        )
    ok("PY_BIN constant present")

    # 3. env-var override
    step("3. NEGATIVE: PYTHON_BIN env var overrides default")
    if 'os.environ.get("PYTHON_BIN"' not in text:
        fail(
            "PYTHON_BIN env var not honored. Operator running with a "
            "different venv (e.g. project-specific) needs to override "
            "without script edit."
        )
    ok("PYTHON_BIN env override supported")

    # 4. fallback to sys.executable when venv missing
    step("4. NEGATIVE: falls back to sys.executable when venv missing")
    if "sys.executable" not in text:
        fail(
            "no sys.executable fallback. On a fresh box without "
            "/tmp/documind-venv, the script must NOT crash."
        )
    # Verify it's a fallback, not the primary
    if not re.search(r"if.+\.exists\(\).+sys\.executable", text, re.DOTALL):
        fail("sys.executable is not gated behind .exists() check")
    ok("sys.executable fallback when venv missing")

    # 5. subprocess uses PY_BIN
    step("5. NEGATIVE: subprocess.run uses PY_BIN, NOT sys.executable")
    # Find the subprocess.run call(s) in run_drill
    if not re.search(r"subprocess\.run\(\s*\[\s*PY_BIN", text):
        fail(
            "subprocess.run doesn't use PY_BIN. Pre-fix bug was "
            "using sys.executable directly; regression here brings "
            "the bug back."
        )
    # Defensive: there should be NO subprocess.run([sys.executable, ...])
    # in the run_drill function specifically (the script could legitimately
    # use sys.executable for OTHER subprocess calls).
    run_drill_match = re.search(
        r"def run_drill\(.*?\n(?=\ndef |\Z)", text, re.DOTALL,
    )
    if run_drill_match and "subprocess.run([sys.executable" in run_drill_match.group(0):
        fail("run_drill() still has subprocess.run([sys.executable, ...])")
    ok("subprocess.run uses PY_BIN; no sys.executable regression in run_drill")

    # 6. PYTHONPATH=REPO in env
    step("6. NEGATIVE: PYTHONPATH=REPO in subprocess env")
    if 'env["PYTHONPATH"]' not in text and "env['PYTHONPATH']" not in text:
        fail(
            "PYTHONPATH not set in subprocess env. drills that "
            "`from mcp import` need REPO on PYTHONPATH."
        )
    if "str(REPO)" not in text:
        fail("PYTHONPATH doesn't include str(REPO)")
    ok("PYTHONPATH=REPO set in subprocess env")

    # 7. PYTHONPATH prepended (not replaced)
    step("7. NEGATIVE: PYTHONPATH PREPENDED (not replaced)")
    # Look for the env.get("PYTHONPATH", "") preserve pattern
    if not re.search(r'env\.get\(\s*["\']PYTHONPATH["\']', text):
        fail(
            "PYTHONPATH not preserved from operator env. A user "
            "with custom PYTHONPATH (e.g. their own libs) would "
            "lose it."
        )
    ok("existing PYTHONPATH preserved via env.get fallback")

    # 8. default points at /tmp/documind-venv/bin/python
    step("8. NEGATIVE: default PY_BIN points at /tmp/documind-venv/bin/python")
    if "/tmp/documind-venv/bin/python" not in text:
        fail(
            "default PY_BIN doesn't match run_drills.py's path. "
            "The two scripts MUST agree or pre-commit drills run "
            "with a different interpreter than tier-1 drills."
        )
    ok("default matches run_drills.py: /tmp/documind-venv/bin/python")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 DRILL-STATUS-INTERPRETER STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
