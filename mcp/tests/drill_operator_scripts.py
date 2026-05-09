#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: operator-facing single-command scripts.

Locks the contract for two CLIs that operators run during incidents:
  - scripts/circuitrag-status.sh — full status check with daemon
                                   restore (7 sections)
  - scripts/install_pending_tools.sh — categorized installer for the
                                       53 pending catalog tools, with
                                       isolation venv for hostile deps

8 steps, 4 negative.

  1. POSITIVE: scripts/circuitrag-status.sh exists + executable
  2. POSITIVE: status script covers 7 named sections
  3. POSITIVE: scripts/install_pending_tools.sh exists + executable
  4. POSITIVE: install script supports the 5 documented batches
              (python / binaries / github / helm / compose)
  5. NEGATIVE: install script defaults to dry-run (no --apply unless
              explicit) — protects against accidental re-runs
              breaking the main venv
  6. NEGATIVE: install script routes garak/pyrit to .venv-redteam
              (NOT main .venv) — they pin newer pydantic/numpy/scipy
              that broke rebuff/giskard/inspect_ai when installed
              into main venv
  7. NEGATIVE: install script does NOT include vigil-llm or
              counterfit (vigil-llm: PyPI typo / project moved;
              counterfit: archived, ancient h5py pin won't build py3.12)
  8. NEGATIVE: status script does NOT skip daemon restore by default
              (operator running it manually expects auto-restore;
              --no-restore is opt-in)

Per CLAUDE.md §43 (drill discipline; ≥3 negatives — 4 here),
§51 forensic substrate (the WHY of each negative is documented in
the script + this drill rejects regression), §57.5 5-question
on-call runbook (status script is the answer to "what broke"),
§57.7 honesty (defaults are operator-safe; hostile-dep tools
isolated, not silently installed).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATUS = REPO / "scripts" / "circuitrag-status.sh"
INSTALL = REPO / "scripts" / "install_pending_tools.sh"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"

REQUIRED_SECTIONS = [
    "Daemon restore",
    "Live BFF",
    "Agent-readiness",
    "Ollama",
    "rebuff / opa-gatekeeper",
    "Catalog drift",
    "Drill scoreboard",
]

REQUIRED_BATCHES = ["python", "binaries", "github", "helm", "compose"]


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    # ── 1. status script exists + executable ──────────────────────────
    step("1. POSITIVE: scripts/circuitrag-status.sh exists + executable")
    if not STATUS.exists():
        fail(f"missing: {STATUS.relative_to(REPO)}")
    if not (STATUS.stat().st_mode & 0o100):
        fail("status script not executable")
    status_text = STATUS.read_text(encoding="utf-8")
    ok(f"status script present ({len(status_text)}b)")

    # ── 2. status script covers 7 sections ────────────────────────────
    step("2. POSITIVE: status script covers 7 named sections")
    missing = [s for s in REQUIRED_SECTIONS if s not in status_text]
    if missing:
        fail(f"status script missing sections: {missing}")
    ok(f"all {len(REQUIRED_SECTIONS)} sections present")

    # ── 3. install script exists + executable ─────────────────────────
    step("3. POSITIVE: scripts/install_pending_tools.sh exists + executable")
    if not INSTALL.exists():
        fail(f"missing: {INSTALL.relative_to(REPO)}")
    if not (INSTALL.stat().st_mode & 0o100):
        fail("install script not executable")
    install_text = INSTALL.read_text(encoding="utf-8")
    ok(f"install script present ({len(install_text)}b)")

    # ── 4. install script supports 5 batches ──────────────────────────
    step("4. POSITIVE: install script supports the 5 documented batches")
    for batch in REQUIRED_BATCHES:
        if f"want_batch {batch}" not in install_text:
            fail(f"install script missing batch handler for {batch!r}")
    ok(f"all {len(REQUIRED_BATCHES)} batches handled")

    # ── 5. NEGATIVE: install script defaults to dry-run ──────────────
    step("5. NEGATIVE: install script defaults to dry-run (no --apply unless explicit)")
    if "DRY_RUN=true" not in install_text:
        fail(
            "install script does NOT default DRY_RUN=true — operator "
            "running with no flags would silently install (unsafe)"
        )
    if "--apply" not in install_text:
        fail("install script lacks --apply flag for explicit opt-in")
    ok("default DRY_RUN=true; --apply required for execution")

    # ── 6. NEGATIVE: garak/pyrit go to .venv-redteam ─────────────────
    step("6. NEGATIVE: garak/pyrit route to .venv-redteam (isolated)")
    if ".venv-redteam" not in install_text:
        fail(
            "install script does NOT use .venv-redteam — garak/pyrit "
            "pin newer pydantic/numpy/scipy that broke rebuff/giskard/"
            "inspect_ai when previously installed into main .venv"
        )
    # And the script must NOT install them into main .venv directly.
    # Look for any line that pip-installs garak/pyrit into .venv (not -redteam).
    bad_lines = []
    for line in install_text.split("\n"):
        ls = line.strip()
        if ".venv/bin/pip install" in ls and ("garak" in ls or "pyrit" in ls):
            bad_lines.append(ls)
    if bad_lines:
        fail(
            f"install script still routes garak/pyrit to main .venv: {bad_lines}. "
            "Must use .venv-redteam to avoid main-venv breakage."
        )
    ok("garak + pyrit isolated to .venv-redteam (main .venv stays compatible)")

    # ── 7. NEGATIVE: vigil-llm + counterfit dropped ──────────────────
    step("7. NEGATIVE: install script does NOT pip-install vigil-llm or counterfit")
    # Look for actual install invocation, not just mention in comments.
    install_lines = [line for line in install_text.split("\n")
                     if "pip install" in line and not line.lstrip().startswith("#")]
    bad_pkg = []
    for line in install_lines:
        if " vigil-llm" in line or "vigil-llm " in line or '"vigil-llm"' in line:
            bad_pkg.append(("vigil-llm", line.strip()))
        if "counterfit" in line and "git+" in line:
            bad_pkg.append(("counterfit", line.strip()))
    if bad_pkg:
        fail(
            f"install script still tries to install unsupported pkgs: {bad_pkg}. "
            "vigil-llm: PyPI typo. counterfit: archived, py3.12-incompatible."
        )
    ok("vigil-llm + counterfit excluded (operator-safe)")

    # ── 8. NEGATIVE: status script auto-restores by default ──────────
    step("8. NEGATIVE: status script does NOT skip daemon-restore by default")
    if "RESTORE=true" not in status_text:
        fail(
            "status script does NOT default RESTORE=true — operator "
            "running it expects daemons to come back; --no-restore is opt-in"
        )
    if "--no-restore" not in status_text:
        fail("status script lacks --no-restore opt-out flag")
    ok("default RESTORE=true; --no-restore opt-in")

    print(f"\n{BOLD}{GREEN}ALL 8 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
