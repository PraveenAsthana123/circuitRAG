#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/run_filter_pipeline.sh — pipeline orchestrator (Phase 5X).

Phase 5X composes 5N snapshot + 5U prom export + 5O alerts/5T webhook
into one cron-friendly call. The drill exercises ONLY --dry-run mode
(safe: no subscripts execute) plus structural inspection of the
script body.

Nine steps. Seven negative assertions.

  1. POSITIVE: --dry-run prints all 3 step commands when given the
     flags that activate each step.
  2. NEGATIVE: unknown flag exits 2 (bad usage, not silent success).
  3. NEGATIVE: no-args run is ACTIVE by default (NOT dry-run). The
     install_snapshot_cron.sh script is dry-run by default for safety;
     this orchestrator is the OPPOSITE because cron expects ACTIVE
     behavior. Drill verifies: no --dry-run means no [DRY-RUN] tag.
  4. NEGATIVE: --skip-snapshot suppresses ONLY the snapshot step.
     The other steps still appear (or skip with their own messages).
  5. NEGATIVE: each step uses correct PYTHON_BIN. Default is
     /mnt/deepa/rag/.venv/bin/python; PYTHON_BIN env override changes
     all 3 step commands.
  6. NEGATIVE: --alert-on accumulates (repeat-flag pattern). Two
     --alert-on args produce TWO --alert-on args in the alerts
     step's command line.
  7. NEGATIVE: --prometheus-out arg threads through to the prom
     step's --prometheus-out flag. Without this, the orchestrator
     wouldn't compose with 5U's prom output.
  8. NEGATIVE: missing --prometheus-out skips the prom step
     gracefully (with explanatory stderr message). The step is
     OPTIONAL; cron lines without prom shouldn't fail.
  9. NEGATIVE: default env file can supply COUNCIL_STATS_WEBHOOK
     without embedding secrets in the cron line.

Run: python3 mcp/tests/drill_run_filter_pipeline.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "run_filter_pipeline.sh"


def _run(args: list[str], env_override: dict | None = None,
         timeout_s: float = 10.0) -> tuple[int, str, str]:
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    proc = subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True, text=True,
        cwd=str(REPO), env=env, timeout=timeout_s,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    if not SCRIPT.exists():
        print(f"✗ pre-step: {SCRIPT} missing")
        return 1
    SCRIPT.read_text()

    # ── Step 1: --dry-run prints all 3 step commands ──
    rc, _, err = _run([
        "--dry-run",
        "--prometheus-out", "/tmp/test.prom",
        "--webhook", "https://hooks.example.com/x",
        "--alert-on", "filtered>0.5",
    ])
    if rc != 0:
        print(f"✗ step 1: --dry-run exit {rc}, expected 0")
        return 1
    if "[DRY-RUN] [snapshot]" not in err:
        print(f"✗ step 1: missing snapshot dry-run line. stderr:\n{err}")
        return 1
    if "[DRY-RUN] [prometheus]" not in err:
        print(f"✗ step 1: missing prometheus dry-run line. stderr:\n{err}")
        return 1
    if "[DRY-RUN] [alerts]" not in err:
        print(f"✗ step 1: missing alerts dry-run line. stderr:\n{err}")
        return 1
    print("✓ step 1: --dry-run prints all 3 step commands when flags activate them")

    # ── Step 2: NEGATIVE — unknown flag exits 2 ──
    rc, _, err = _run(["--garbage-flag"])
    if rc != 2:
        print(f"✗ step 2: unknown flag exit {rc}, expected 2")
        return 1
    if "unknown flag" not in err.lower():
        print("✗ step 2: missing 'unknown flag' message")
        return 1
    print("✓ step 2: unknown flag exits 2 (typo-safe CI)")

    # ── Step 3: NEGATIVE — active by default (NOT dry-run) ──
    # Run with --skip-snapshot --skip-prometheus and no --alert-on
    # so nothing actually executes, but verify there's no [DRY-RUN]
    # in the output. The active-by-default contract differs from
    # install_snapshot_cron.sh's dry-run-by-default.
    rc, _, err = _run(["--skip-snapshot", "--skip-prometheus"])
    if rc != 0:
        print(f"✗ step 3: no-op exit {rc}, expected 0")
        return 1
    if "[DRY-RUN]" in err:
        print("✗ step 3: no --dry-run flag, but output has [DRY-RUN]. "
              "Active-by-default contract broken.")
        return 1
    print("✓ step 3: active by default (no [DRY-RUN] without explicit flag)")

    # ── Step 4: NEGATIVE — --skip-snapshot suppresses ONLY snapshot ──
    rc, _, err = _run([
        "--dry-run",
        "--skip-snapshot",
        "--prometheus-out", "/tmp/test.prom",
        "--alert-on", "filtered>0.5",
    ])
    if rc != 0:
        print(f"✗ step 4: --skip-snapshot exit {rc}, expected 0")
        return 1
    # snapshot step should NOT have a DRY-RUN command line; it should
    # have the (skipped per --skip-snapshot) message
    if "[DRY-RUN] [snapshot]" in err:
        print("✗ step 4: --skip-snapshot did not suppress snapshot step")
        return 1
    if "(skipped per --skip-snapshot)" not in err:
        print("✗ step 4: missing skip-snapshot explanation message")
        return 1
    # But other steps must still be present
    if "[DRY-RUN] [prometheus]" not in err:
        print("✗ step 4: --skip-snapshot wrongly suppressed prometheus")
        return 1
    if "[DRY-RUN] [alerts]" not in err:
        print("✗ step 4: --skip-snapshot wrongly suppressed alerts")
        return 1
    print("✓ step 4: --skip-snapshot suppresses only snapshot; others still fire")

    # ── Step 5: NEGATIVE — PYTHON_BIN env override ──
    custom = "/some/custom/python3.42"
    rc, _, err = _run([
        "--dry-run",
        "--prometheus-out", "/tmp/x.prom",
        "--alert-on", "filtered>0.5",
    ], env_override={"PYTHON_BIN": custom})
    if rc != 0:
        print(f"✗ step 5: PYTHON_BIN run exit {rc}")
        return 1
    # All 3 step commands must use the custom interpreter
    custom_count = err.count(custom)
    if custom_count < 3:
        print(f"✗ step 5: PYTHON_BIN={custom!r} appeared {custom_count}× in "
              "step commands, expected ≥3 (one per step)")
        return 1
    # And the default must NOT appear in step commands
    default_in_steps = re.search(
        r"\[DRY-RUN\] \[(?:snapshot|prometheus|alerts)\]:.*?/mnt/deepa/rag/\.venv/bin/python",
        err,
    )
    if default_in_steps:
        print(f"✗ step 5: default interpreter still in step commands: "
              f"{default_in_steps.group(0)}")
        return 1
    print(f"✓ step 5: PYTHON_BIN={custom!r} appears in all 3 step commands "
          "(default suppressed)")

    # ── Step 6: NEGATIVE — --alert-on accumulates ──
    rc, _, err = _run([
        "--dry-run",
        "--alert-on", "filtered>0.5",
        "--alert-on", "too_short>0.3",
        "--alert-on", "skip_token>0.2",
    ])
    if rc != 0:
        print(f"✗ step 6: multi-alert run exit {rc}")
        return 1
    # The alerts step's command should contain three --alert-on args
    alerts_line = next(
        (ln for ln in err.splitlines() if "[DRY-RUN] [alerts]" in ln),
        None,
    )
    if not alerts_line:
        print("✗ step 6: no alerts line in dry-run output")
        return 1
    on_count = alerts_line.count("--alert-on")
    if on_count != 3:
        print(f"✗ step 6: alerts line has {on_count} --alert-on args, "
              f"expected 3. Line: {alerts_line!r}")
        return 1
    print("✓ step 6: --alert-on accumulates (3 args → 3 --alert-on in alerts cmd)")

    # ── Step 7: NEGATIVE — --prometheus-out threads through ──
    sentinel = "/tmp/totally-unique-prom-path-5X.prom"
    rc, _, err = _run([
        "--dry-run",
        "--prometheus-out", sentinel,
    ])
    if rc != 0:
        print(f"✗ step 7: --prometheus-out run exit {rc}")
        return 1
    prom_line = next(
        (ln for ln in err.splitlines() if "[DRY-RUN] [prometheus]" in ln),
        None,
    )
    if not prom_line:
        print("✗ step 7: no prometheus dry-run line")
        return 1
    if sentinel not in prom_line:
        print(f"✗ step 7: --prometheus-out value {sentinel!r} not in prom command")
        return 1
    if "--prometheus-out" not in prom_line:
        print("✗ step 7: --prometheus-out flag missing from prom command")
        return 1
    print("✓ step 7: --prometheus-out value threads through to prom step command")

    # ── Step 8: NEGATIVE — missing --prometheus-out skips gracefully ──
    rc, _, err = _run([
        "--dry-run",
        # No --prometheus-out, no --skip-prometheus
    ])
    if rc != 0:
        print(f"✗ step 8: missing --prometheus-out exit {rc}, expected 0")
        return 1
    if "[DRY-RUN] [prometheus]" in err:
        print("✗ step 8: prom step ran without --prometheus-out path")
        return 1
    # Must have an explanation message
    if "no --prometheus-out path given" not in err:
        print(f"✗ step 8: missing graceful-skip message for prometheus. stderr:\n{err}")
        return 1
    print("✓ step 8: missing --prometheus-out skips prom step gracefully (cron-safe)")

    # ── Step 9: NEGATIVE — env file supplies webhook without cron secret ──
    with tempfile.NamedTemporaryFile("w", delete=False) as fh:
        fh.write('COUNCIL_STATS_WEBHOOK="https://hooks.example.com/from-env-file"\n')
        env_file = fh.name
    try:
        rc, _, err = _run([
            "--dry-run",
            "--alert-on", "filtered>0.5",
        ], env_override={"COUNCIL_STATS_ENV_FILE": env_file})
        if rc != 0:
            print(f"✗ step 9: env-file dry-run exit {rc}")
            return 1
        alerts_line = next(
            (ln for ln in err.splitlines() if "[DRY-RUN] [alerts]" in ln),
            None,
        )
        if not alerts_line:
            print("✗ step 9: no alerts line in dry-run output")
            return 1
        if "--webhook https://hooks.example.com/from-env-file" not in alerts_line:
            print(f"✗ step 9: env-file webhook missing from alerts cmd. Line: {alerts_line!r}")
            return 1
    finally:
        os.unlink(env_file)
    print("✓ step 9: default env file can supply webhook without embedding cron secrets")

    print("\nALL 9 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
