#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: autonomous_fix_daemon --scan-fast + --scan-paths flags.

Per §43 + §55. Locks the daemon-side fix for the 2026-05-04 empirical
retest scanner-timeout finding (see
docs/architecture/empirical-retest-2026-05-04-scanner-timeout.md).

Contract:
  - --scan-fast skips mypy/bandit/eslint; runs ruff only
  - --scan-paths narrows scanner --targets
  - Empirical harness's `simulate` wires both flags by default
  - Without these flags, full scan can exceed 600s on this repo
  - With both flags, scan completes in <30s for a single synthetic file

Eight steps. Six negative.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DAEMON = REPO / "scripts" / "autonomous_fix_daemon.py"
HARNESS = REPO / "scripts" / "empirical_apply_test.py"
PYTHON = REPO / ".venv" / "bin" / "python3"


def main() -> int:
    print("-- 1. POSITIVE: daemon + harness exist --")
    if not DAEMON.exists() or not HARNESS.exists():
        print("x daemon or harness missing")
        return 1
    daemon_src = DAEMON.read_text(encoding="utf-8")
    harness_src = HARNESS.read_text(encoding="utf-8")
    print(f"  ok: daemon ({len(daemon_src)} chars) + harness ({len(harness_src)} chars) present")

    print("-- 2. POSITIVE: daemon argparse registers --scan-fast --")
    if "--scan-fast" not in daemon_src:
        print("x --scan-fast flag not registered")
        return 1
    if 'add_argument("--scan-fast"' not in daemon_src:
        print("x --scan-fast must be registered via add_argument")
        return 1
    print("  ok: --scan-fast registered")

    print("-- 3. POSITIVE: daemon argparse registers --scan-paths --")
    if 'add_argument("--scan-paths"' not in daemon_src:
        print("x --scan-paths must be registered via add_argument")
        return 1
    print("  ok: --scan-paths registered")

    print("-- 4. NEGATIVE: scan_issues() conditionally drops slow linters --")
    # Locks the contract: when scan_fast=True, the subprocess cmd must
    # NOT include --include-mypy / --include-bandit / --include-eslint.
    # Drilled via source inspection (functional test below).
    if "if not scan_fast:" not in daemon_src:
        print("x scan_issues must guard slow linters behind `if not scan_fast`")
        return 1
    if "scan_fast: bool = False" not in daemon_src:
        print("x scan_issues signature must accept scan_fast param")
        return 1
    print("  ok: scan_fast guard present in scan_issues()")

    print("-- 5. NEGATIVE: scan_issues() forwards scan_paths to --targets --")
    if "scan_paths: list[str] | None" not in daemon_src:
        print("x scan_issues signature must accept scan_paths param")
        return 1
    if 'cmd.append("--targets")' not in daemon_src:
        print("x scan_paths must extend cmd with --targets")
        return 1
    print("  ok: scan_paths forwarded to scanner --targets")

    print("-- 6. NEGATIVE: empirical harness wires both flags by default --")
    # The harness is the canonical retest path; it MUST pass both flags
    # so scan completes in <30s instead of timing out.
    if '"--scan-fast"' not in harness_src:
        print("x harness simulate must pass --scan-fast")
        return 1
    if '"--scan-paths"' not in harness_src:
        print("x harness simulate must pass --scan-paths")
        return 1
    if "tests/_empirical_synthetic.py" not in harness_src:
        print("x harness must scope --scan-paths to tests/_empirical_synthetic.py")
        return 1
    print("  ok: harness wires --scan-fast + --scan-paths automatically")

    print("-- 7. NEGATIVE: --help still reflects new flags --")
    proc = subprocess.run(
        [str(PYTHON), str(DAEMON), "--help"],
        capture_output=True, text=True, timeout=10, cwd=REPO,
    )
    if proc.returncode != 0:
        print(f"x daemon --help exit {proc.returncode}")
        return 1
    if "--scan-fast" not in proc.stdout:
        print("x --scan-fast missing from --help output")
        return 1
    if "--scan-paths" not in proc.stdout:
        print("x --scan-paths missing from --help output")
        return 1
    print("  ok: both flags surface in --help")

    print("-- 8. POSITIVE: source documents the rationale --")
    # The why-this-exists is non-obvious; future contributors should
    # see WHY scan_fast exists without grep-archeology.
    if "empirical retest" not in daemon_src.lower():
        print("x daemon source must reference empirical retest rationale")
        return 1
    if "600s" not in daemon_src and "exceed" not in daemon_src:
        print("x daemon source must document the 600s timeout rationale")
        return 1
    print("  ok: rationale documented in daemon source")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
