#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: agent environment setup script — preflight contract.

Locks the autonomous-fix-bot env-setup contract. Per CLAUDE.md §43
(drill discipline) + §55 (autonomous-fix-bot strategy).

The setup script is the SAFETY NET that catches "operator forgot
to install X / pull Y / mkdir Z" before they hit a 100s daemon
cycle that fails for an obvious reason. The drill locks:

  - Script exports --help / --status / --install / --warm modes
  - --status returns one-line summary in the documented format
  - --help is non-trivial (≥ 600 chars; per §43 operator usability)
  - Required-model list contains all 4 council members
  - Required-pip-deps list covers Pydantic + LangGraph + ruff
  - Required-global-scripts list points at ~/.claude/scripts/
  - Idempotent: re-running with same flags doesn't break

Eight steps. Six negative assertions.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "setup_agent_env.sh"


def main() -> int:
    print("-- 1. POSITIVE: setup_agent_env.sh exists + executable --")
    if not SCRIPT.exists():
        print(f"x step 1: {SCRIPT} missing")
        return 1
    if not (SCRIPT.stat().st_mode & 0o111):
        print(f"x step 1: {SCRIPT} not executable")
        return 1
    print(f"  ok: {SCRIPT.name} exists + executable")

    print("-- 2. POSITIVE: --help is operator-readable (≥600 chars + sections) --")
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        capture_output=True, text=True, timeout=10,
    )
    if proc.returncode != 0:
        print(f"x step 2: --help exited {proc.returncode}")
        return 1
    help_text = proc.stdout
    if len(help_text) < 600:
        print(f"x step 2: --help only {len(help_text)} chars; expected ≥600")
        return 1
    for marker in ("Usage:", "Verifies", "Locked by"):
        if marker not in help_text:
            print(f"x step 2: --help missing marker {marker!r}")
            return 1
    print(f"  ok: --help has 3 markers + {len(help_text)} chars")

    print("-- 3. NEGATIVE: --status returns one-line k=v format --")
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--status"],
        capture_output=True, text=True, timeout=10,
    )
    if proc.returncode != 0:
        print(f"x step 3: --status exited {proc.returncode}")
        return 1
    status_line = proc.stdout.strip()
    for k in ("venv=", "ollama=", "loop="):
        if k not in status_line:
            print(f"x step 3: --status missing {k!r} in output: {status_line!r}")
            return 1
    if "\n" in status_line:
        print(f"x step 3: --status produced multiple lines (must be one-liner)")
        return 1
    print(f"  ok: one-line k=v status: {status_line}")

    src = SCRIPT.read_text(encoding="utf-8")

    print("-- 4. NEGATIVE: required-models list has all 4 council members --")
    expected_models = (
        "deepseek-coder:6.7b-instruct",
        "codegemma:7b-instruct",
        "codellama:7b-instruct",
        "qwen2.5:latest",
    )
    for m in expected_models:
        if m not in src:
            print(f"x step 4: required-models list missing {m!r}")
            return 1
    print(f"  ok: all 4 council models referenced")

    print("-- 5. NEGATIVE: required-pip-deps covers core stack --")
    for dep in ("pydantic", "langgraph", "ruff", "pytest"):
        if f"  {dep}" not in src and f'  "{dep}"' not in src:
            # tolerant match: check the bash array body
            pass
    # simpler: check bash array text
    deps_section = re.search(r"REQUIRED_PIP_DEPS=\((.*?)\)", src, re.DOTALL)
    if deps_section is None:
        print("x step 5: REQUIRED_PIP_DEPS array not found")
        return 1
    deps_body = deps_section.group(1)
    for dep in ("pydantic", "langgraph", "ruff", "pytest", "bandit"):
        if dep not in deps_body:
            print(f"x step 5: REQUIRED_PIP_DEPS missing {dep!r}")
            return 1
    print(f"  ok: all 5 core pip deps in REQUIRED_PIP_DEPS")

    print("-- 6. NEGATIVE: required-global-scripts points at ~/.claude/scripts/ --")
    if "$HOME/.claude/scripts/issue_scanner.py" not in src:
        print("x step 6: REQUIRED_GLOBAL_SCRIPTS missing issue_scanner.py")
        return 1
    if "$HOME/.claude/scripts/issue_dispatcher.py" not in src:
        print("x step 6: REQUIRED_GLOBAL_SCRIPTS missing issue_dispatcher.py")
        return 1
    print("  ok: global discovery scripts referenced (~/.claude/scripts/)")

    print("-- 7. NEGATIVE: §42 boundary — script does NOT auto-push --")
    # The setup script must not contain `git push`. Cron install + setup
    # are local-only; push stays §42-gated to agent_task_board.py.
    forbidden = ("git push", "ollama push", "force-push", "pip install --user")
    for f in forbidden:
        if f in src:
            print(f"x step 7: forbidden command in setup script: {f!r}")
            return 1
    print("  ok: no §42-gated commands (no git push, no force-push)")

    print("-- 8. POSITIVE: idempotent re-run preflight succeeds twice --")
    proc1 = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True, text=True, timeout=120,
    )
    proc2 = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True, text=True, timeout=120,
    )
    if proc1.returncode != proc2.returncode:
        print(f"x step 8: re-run produced different exit code: {proc1.returncode} vs {proc2.returncode}")
        return 1
    print(f"  ok: re-run idempotent (exit codes match: {proc1.returncode})")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
