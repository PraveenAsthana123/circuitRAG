#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/agent-orchestrator-up.sh idempotent boot script.

The agent-orchestrator-svc has a Dockerfile but isn't in
docker-compose.yml yet. It runs as a host-side python process,
which dies whenever the parent shell rotates. The agent-readiness
page reports "B_orchestrator_up: NO" repeatedly because of this.

This boot script makes the process survive shell rotation
(setsid + nohup), uses the right venv (.venv py3.12, not .venv311
which lacks fastapi), sets the right PYTHONPATH (REPO + libs/py),
and assigns a non-colliding prometheus port (9466).

This drill prevents regression: any future "cleanup" that drops
setsid OR uses the wrong venv OR forgets PYTHONPATH/libs OR
defaults a colliding prometheus port → drill rejects.

7 steps, 4 negative.

  1. POSITIVE: scripts/agent-orchestrator-up.sh exists + executable
  2. POSITIVE: script uses .venv (py3.12 with fastapi), not .venv311
  3. POSITIVE: PYTHONPATH includes REPO_ROOT/libs/py (where
              documind_core lives)
  4. NEGATIVE: script does NOT skip setsid — without it the
              process dies on parent shell rotation (the failure
              mode this script exists to fix)
  5. NEGATIVE: DOCUMIND_PROMETHEUS_PORT NOT default (which would
              collide with retrieval-svc on :9464); MUST be 9466
              or operator-overridable
  6. NEGATIVE: script does NOT skip the idempotent kill —
              re-running without it would always fail with
              "Address already in use" silently in nohup output
  7. POSITIVE: script verifies reachability before returning
              (operator-loud failure if startup is broken)

Per CLAUDE.md §43 (drill discipline; ≥3 negatives — 3 here),
§51 forensic substrate (script comment block names the failure
modes the drill defends against), §57.1 production-grade-by-default
(orchestrator must survive shell rotation), §57.7 honesty (script
comment + drill both name "the prior 5-NO regression on
agent-readiness B_orchestrator_up").
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "agent-orchestrator-up.sh"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    # ── 1. file exists + executable ────────────────────────────────────
    step("1. POSITIVE: scripts/agent-orchestrator-up.sh exists + executable")
    if not SCRIPT.exists():
        fail(f"missing: {SCRIPT.relative_to(REPO)}")
    mode = SCRIPT.stat().st_mode
    if not (mode & 0o100):
        fail("script not executable (chmod +x)")
    text = SCRIPT.read_text(encoding="utf-8")
    ok(f"script present + executable ({len(text)}b)")

    # ── 2. uses .venv (py3.12), not .venv311 ──────────────────────────
    step("2. POSITIVE: script uses .venv (py3.12 with fastapi)")
    if "/.venv/bin/python" not in text:
        fail(
            "script does NOT use $REPO_ROOT/.venv/bin/python — "
            ".venv311 (py3.11) lacks fastapi; only .venv (py3.12) has it"
        )
    ok("script targets .venv/bin/python (py3.12 with fastapi)")

    # ── 3. PYTHONPATH includes libs/py ────────────────────────────────
    step("3. POSITIVE: PYTHONPATH includes REPO_ROOT/libs/py")
    if "libs/py" not in text:
        fail(
            "PYTHONPATH does NOT include libs/py — orchestrator imports "
            "documind_core which lives at libs/py/documind_core/. "
            "ModuleNotFoundError: No module named 'documind_core'"
        )
    ok("PYTHONPATH includes libs/py (documind_core importable)")

    # ── 4. NEGATIVE: setsid required ──────────────────────────────────
    step("4. NEGATIVE: script does NOT skip setsid (parent-shell-rotation defense)")
    if "setsid" not in text:
        fail(
            "script does NOT use setsid — uvicorn process will die when "
            "the parent shell rotates (pre-commit hooks, agent restarts, "
            "terminal close). This is the prior 5-NO regression on "
            "agent-readiness B_orchestrator_up that the script exists to fix."
        )
    if "nohup" not in text:
        fail("script does NOT use nohup — required alongside setsid for full daemonization")
    ok("setsid + nohup both present (process survives shell rotation)")

    # ── 5. NEGATIVE: prometheus port avoids :9464 collision ───────────
    step("5. NEGATIVE: DOCUMIND_PROMETHEUS_PORT does NOT default to :9464")
    if "DOCUMIND_PROMETHEUS_PORT" not in text:
        fail(
            "script does NOT set DOCUMIND_PROMETHEUS_PORT — defaults to "
            ":9464 which collides with retrieval-svc. Startup fails with "
            "OSError [Errno 98] Address already in use."
        )
    # Default value must NOT be 9464. We check the actual env-var assignment
    # line (not just text appearance — the rationale comment legitimately
    # mentions 9464 to explain the collision being avoided).
    import re as _re
    assignment = _re.search(
        r'DOCUMIND_PROMETHEUS_PORT="\$\{DOCUMIND_PROMETHEUS_PORT:-([0-9]+)\}"',
        text,
    )
    if not assignment:
        fail("DOCUMIND_PROMETHEUS_PORT not assigned with the conventional `${VAR:-default}` form")
    default_port = int(assignment.group(1))
    if default_port == 9464:
        fail(f"DOCUMIND_PROMETHEUS_PORT default is :{default_port} — colliding with retrieval-svc")
    if default_port < 9465:
        fail(f"DOCUMIND_PROMETHEUS_PORT default is :{default_port} — too low; conv is 9466 (retr=9464, infer=9465, orch=9466)")
    ok(f"DOCUMIND_PROMETHEUS_PORT default is :{default_port} (no collision with retrieval/inference)")

    # ── 6. NEGATIVE: idempotent kill before start ─────────────────────
    step("6. NEGATIVE: script does NOT skip idempotent kill of stale process")
    if "lsof" not in text and "pkill" not in text:
        fail(
            "script lacks idempotent kill (no lsof or pkill) — re-running "
            "fails silently with 'Address already in use' in nohup output"
        )
    if "kill" not in text:
        fail("script does not invoke kill at all")
    ok("script kills any stale process on the target port (idempotent)")

    # ── 7. POSITIVE: verifies reachability before returning ───────────
    step("7. POSITIVE: script verifies reachability before exit")
    if "/health/live" not in text:
        fail(
            "script does not probe /health/live before returning — "
            "operator can't tell if startup actually succeeded"
        )
    if "curl" not in text:
        fail("script lacks curl probe — no reachability verification")
    # Should also have a timeout / retry loop.
    if "for i in" not in text and "while" not in text:
        fail("script does not loop the curl probe — single attempt may race startup")
    ok("script probes /health/live in a retry loop (operator-loud failure)")

    print(f"\n{BOLD}{GREEN}ALL 7 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
