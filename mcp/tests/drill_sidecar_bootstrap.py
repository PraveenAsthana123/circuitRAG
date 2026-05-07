#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/sidecar_bootstrap.sh structural contract.

Eight steps. Six negative assertions.

  1. Script exists + executable.
  2. NEGATIVE: idempotent — re-running doesn't double-install
     (the git hook check, drill-status freshness check, and
     advisor.db existence check all guard re-execution).
  3. NEGATIVE: never overwrites an existing core.hooksPath
     (warns + no-ops if user already has a different hooks path).
  4. NEGATIVE: declares set -euo pipefail.
  5. NEGATIVE: invokes scripts/write_drill_status.py to seed
     LoopWatcher rule 1's input. Without this, the first commit
     after bootstrap sees a missing status and silently passes.
  6. NEGATIVE: invokes scripts/render_dashboard.py to produce
     the initial dashboard.html.
  7. NEGATIVE: prereq check covers git + python3 + pyyaml. Each
     is required by some downstream script.
  8. NEGATIVE: prints the operator's quick-start commands at the
     end (refresh dashboard, replay verdicts, drain backlog,
     prune retention). Without the cheat-sheet, the operator
     has to read 4 different runbooks.

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import os
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "sidecar_bootstrap.sh"

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
    # 1. exists + executable
    step("1. sidecar_bootstrap.sh exists + executable")
    if not SCRIPT.exists():
        fail(f"missing: {SCRIPT}")
    if not os.access(SCRIPT, os.X_OK):
        fail(f"not executable: {SCRIPT}")
    text = SCRIPT.read_text()
    if len(text) < 1500:
        fail(f"too short: {len(text)} chars")
    ok(f"script ok ({len(text)} chars)")

    # 2. idempotency guards
    step("2. NEGATIVE: idempotent (re-runs don't double-install)")
    # advisor.db existence check (skips re-init if present)
    if "[ -f \"$ADVISOR_DB\" ]" not in text:
        fail("no advisor.db existence check; re-run would re-init")
    # core.hooksPath check (skips re-set if same)
    if "scripts/git-hooks" not in text or "git config --get core.hooksPath" not in text:
        fail("no hooks-path check; re-run would re-set silently")
    # drill-status freshness check (skips re-run if recent)
    if "AGE_SECS" not in text or "3600" not in text:
        fail("no drill-status age check; re-run would always re-drill")
    ok("3 idempotency guards: advisor.db, hooksPath, drill-status age")

    # 3. don't overwrite different hooks path
    step("3. NEGATIVE: warns instead of overwriting different hooksPath")
    if "NOT overwriting" not in text and "not overwriting" not in text.lower():
        fail(
            "no warn-and-skip when hooksPath differs. Operator's existing "
            "hook config (e.g. for a different tool) would be silently "
            "stomped."
        )
    ok("warn-and-skip on different existing hooksPath")

    # 4. set -euo pipefail
    step("4. NEGATIVE: set -euo pipefail")
    if "set -euo pipefail" not in text:
        fail("missing fail-fast flags")
    ok("set -euo pipefail declared")

    # 5. drill-status invocation
    step("5. NEGATIVE: invokes write_drill_status.py to seed rule 1")
    if "write_drill_status.py" not in text:
        fail(
            "doesn't run write_drill_status.py. Without it, "
            ".loop/last_drill_outcome.json is empty + LoopWatcher "
            "rule 1 silently passes (never REJECTs on drill failure)."
        )
    ok("write_drill_status.py invoked to seed status file")

    # 6. dashboard render
    step("6. NEGATIVE: invokes render_dashboard.py for initial dashboard.html")
    if "render_dashboard.py" not in text:
        fail(
            "doesn't render the initial dashboard. Operator hits "
            "/admin/sidecar and sees the fallback ('run the renderer') "
            "message instead of actual data."
        )
    ok("render_dashboard.py invoked to produce dashboard.html")

    # 7. prereq coverage
    step("7. NEGATIVE: prereq check covers git + python3 + pyyaml")
    for tool in ["git", "python3", "yaml"]:
        if tool not in text:
            fail(f"prereq check missing {tool}")
    # The check should USE `command -v` for git/python3 (verifies on PATH)
    if "command -v git" not in text:
        fail("git prereq not verified via command -v (PATH check)")
    if "command -v python3" not in text:
        fail("python3 prereq not verified via command -v")
    # yaml check uses `python3 -c "import yaml"`
    if "import yaml" not in text:
        fail("pyyaml not import-checked")
    ok("3 prereqs verified: git, python3, pyyaml")

    # 8. quick-start cheat-sheet
    step("8. NEGATIVE: prints operator quick-start commands")
    expected_phrases = [
        "render_dashboard.py",
        "replay_verdict_log.py",
        "replay_council_against_events.py",
        "prune_council_runs.py",
    ]
    missing = [p for p in expected_phrases if p not in text]
    if missing:
        fail(
            f"quick-start missing references to: {missing}. Operator "
            f"would have to grep through 4 different runbooks to find "
            f"these commands."
        )
    if "git config --unset core.hooksPath" not in text:
        fail(
            "no instructions for disabling the hook. Operator who "
            "wants to opt out needs the exact unset command."
        )
    ok("4 follow-up commands + opt-out instruction printed")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 SIDECAR-BOOTSTRAP STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
