#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: every script in scripts/ responds cleanly to `--help` (Phase 6Q).

Operator usability invariant: an operator picking up an unfamiliar
script should be able to type `<script> --help` and get a usable
description in <3 seconds. Scripts that crash on --help, hang, or
emit nothing fail the operator at exactly the moment they need help.

Phase 6Q drills the catalog: every committed script under scripts/
must exit 0 within 5s when invoked with --help. Per ADR-015 ratchet
pattern, scripts that currently don't are grandfathered in
KNOWN_NO_HELP; new scripts must conform.

Eight steps. Six negative assertions.

  1. POSITIVE: ≥10 scripts found in scripts/ (sanity).
  2. NEGATIVE: every conformant Python script (per
     KNOWN_NO_HELP) exits 0 on --help. Catches regression on
     scripts that previously had --help and dropped it.
  3. NEGATIVE: every conformant shell script exits 0 on --help
     (same regression-catch).
  4. NEGATIVE: --help output is non-trivial (≥40 chars stderr+stdout).
     Empty --help is technically zero-exit but useless to operators.
  5. NEGATIVE: --help completes within 5s. Slower means operator
     waits for trivial info.
  6. NEGATIVE: KNOWN_NO_HELP set has no NEW additions vs the
     committed set. New scripts must conform; only the
     grandfathered list shrinks (or stays).
  7. NEGATIVE: every entry in KNOWN_NO_HELP corresponds to a real
     file in scripts/. Stale entries (file deleted) signal stale
     ratchet that should be cleaned up.
  8. POSITIVE: catalog growth is observable — script count is
     reported so future operators see how the surface grows.

Run: python3 mcp/tests/drill_scripts_have_help.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "scripts"
PY_BIN = "/mnt/deepa/rag/.venv/bin/python"

# Ratchet per ADR-015: scripts that currently don't conform to the
# --help contract. New scripts MUST conform; this set should only
# shrink. When you add a script, add --help support OR add an
# explicit entry here with rationale.
KNOWN_NO_HELP = {
    "migrate.py",            # subcommand-style; needs explicit --help wiring
    "seed_demo.py",          # demo-only; arg-free invocation
    "smoke_test.py",         # smoke runner; arg-free invocation
    "gen-dev-keys.sh",       # accepts --help but exits 1 (legacy shape)
    "golden-demo.sh",        # demo-only
    "install_snapshot_cron.sh",  # custom mode dispatch (--dry-run / --apply etc); --help → exit 2 by design
    "run_filter_pipeline.sh",    # custom mode dispatch
    "scheduled_kaggle_ingest.sh", # cron-style invocation
}


def _help_runs(path: Path) -> tuple[bool, str, float]:
    """Return (ok, output, duration_s)."""
    import time
    interp = [PY_BIN] if path.suffix == ".py" else []
    cmd = interp + [str(path), "--help"]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5.0, cwd=str(REPO),
        )
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after 5s", 5.0
    except (FileNotFoundError, PermissionError, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}", time.monotonic() - t0
    duration = time.monotonic() - t0
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output, duration


def main() -> int:
    if not SCRIPTS_DIR.exists():
        print(f"✗ pre-step: {SCRIPTS_DIR} missing")
        return 1

    py_scripts = sorted(SCRIPTS_DIR.glob("*.py"))
    sh_scripts = sorted(SCRIPTS_DIR.glob("*.sh"))
    all_scripts = py_scripts + sh_scripts

    # ── Step 1: POSITIVE — sanity ──
    if len(all_scripts) < 10:
        print(f"✗ step 1: only {len(all_scripts)} scripts found, expected ≥10")
        return 1
    print(f"✓ step 1: {len(all_scripts)} scripts in scripts/ "
          f"({len(py_scripts)} py + {len(sh_scripts)} sh)")

    # ── Step 2 + 3 + 4 + 5: combined help-runs check ──
    nonconformers: list[tuple[str, str]] = []
    slow: list[tuple[str, float]] = []
    sparse: list[tuple[str, int]] = []
    for s in all_scripts:
        if s.name in KNOWN_NO_HELP:
            continue
        ok, output, duration = _help_runs(s)
        if not ok:
            nonconformers.append((s.name, output[:200]))
        elif duration > 5.0:
            slow.append((s.name, duration))
        elif len(output.strip()) < 40:
            sparse.append((s.name, len(output)))

    if nonconformers:
        py_fails = [n for n, _ in nonconformers if n.endswith(".py")]
        sh_fails = [n for n, _ in nonconformers if n.endswith(".sh")]
        if py_fails:
            print(f"✗ step 2: {len(py_fails)} Python scripts fail --help: "
                  f"{py_fails[:3]}")
            return 1
        if sh_fails:
            print(f"✗ step 3: {len(sh_fails)} shell scripts fail --help: "
                  f"{sh_fails[:3]}")
            return 1
    print(f"✓ step 2: every conformant Python script exits 0 on --help")
    print(f"✓ step 3: every conformant shell script exits 0 on --help")

    if sparse:
        print(f"✗ step 4: {len(sparse)} scripts emit <40 chars on --help: "
              f"{sparse[:3]}")
        return 1
    print(f"✓ step 4: every --help output ≥40 chars (operator-readable)")

    if slow:
        print(f"✗ step 5: {len(slow)} scripts take >5s on --help: {slow[:3]}")
        return 1
    print(f"✓ step 5: every --help completes within 5s")

    # ── Step 6: NEGATIVE — KNOWN_NO_HELP doesn't grow ──
    actual_nonconformers = set()
    for s in all_scripts:
        ok, _, _ = _help_runs(s)
        if not ok:
            actual_nonconformers.add(s.name)
    new_drift = actual_nonconformers - KNOWN_NO_HELP
    if new_drift:
        print(f"✗ step 6: {len(new_drift)} NEW scripts fail --help "
              f"(not in KNOWN_NO_HELP): {sorted(new_drift)}. "
              "Add --help support OR add explicit ratchet entry.")
        return 1
    print(f"✓ step 6: 0 new --help drift; "
          f"{len(actual_nonconformers & KNOWN_NO_HELP)} grandfathered")

    # ── Step 7: NEGATIVE — KNOWN_NO_HELP entries correspond to real files ──
    on_disk = {s.name for s in all_scripts}
    stale = KNOWN_NO_HELP - on_disk
    if stale:
        print(f"✗ step 7: {len(stale)} KNOWN_NO_HELP entries don't exist "
              f"on disk: {sorted(stale)}. Stale ratchet — clean up.")
        return 1
    print(f"✓ step 7: every KNOWN_NO_HELP entry corresponds to real file "
          f"({len(KNOWN_NO_HELP)} grandfathered)")

    # ── Step 8: POSITIVE — observable growth ──
    conformant = len(all_scripts) - len(actual_nonconformers)
    print(f"✓ step 8: catalog observable — {conformant}/{len(all_scripts)} "
          f"scripts conform; {len(KNOWN_NO_HELP)} grandfathered")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
