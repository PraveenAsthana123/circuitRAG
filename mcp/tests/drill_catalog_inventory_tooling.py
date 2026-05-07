#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/drill_catalog_summary.py + scripts/ratchet_status.py.

Phase 6J pairs two operator-facing inventory tools:

  drill_catalog_summary.py — total + tier counts + resource distribution
  ratchet_status.py        — current state of every ratchet (HEALTHY/
                             WARNING/ERROR exit codes 0/1/2)

The two compose: drill_catalog_summary's "ratchets" field comes from
delegating to ratchet_status (subprocess + JSON parse). This drill
locks both contracts — schema, exit codes, integration point.

Eight steps. Six negative assertions.

  1. POSITIVE: drill_catalog_summary.py exits 0 in both text and
     --json modes (read-only inventory; never fails).
  2. NEGATIVE: catalog_summary.total_drills equals actual count of
     mcp/tests/drill_*.py files on disk. Drift here means the
     script's discovery pattern is wrong.
  3. NEGATIVE: resource_source_counts (zero + tagged + defaulted)
     sums to total_drills. No drills silently dropped.
  4. NEGATIVE: ratchet_status.py exits 0 (HEALTHY) when all ratchets
     are clean. Currently the catalog has 0 drift; if this fires, the
     parallel stream's cleanup regressed.
  5. NEGATIVE: ratchet_status JSON output contains the required
     schema fields (ratchet_state, known_missing_count, resources_*,
     neg_*, section7_*). Without these, drill_catalog_summary's
     delegation breaks at parse time.
  6. NEGATIVE: ratchet_status exit code matches its ratchet_state
     enum: HEALTHY=0, WARNING=1, ERROR=2.
  7. NEGATIVE: catalog_summary's "ratchets" field is non-None when
     ratchet_status.py is present. Delegation works end-to-end.
  8. POSITIVE: integration consistency — catalog_summary's
     reported ratchets[ratchet_state] matches ratchet_status's
     direct invocation. Prevents silent drift between the two.

Run: python3 mcp/tests/drill_catalog_inventory_tooling.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DRILL_DIR = REPO / "mcp" / "tests"
SUMMARY_SCRIPT = REPO / "scripts" / "drill_catalog_summary.py"
RATCHET_SCRIPT = REPO / "scripts" / "ratchet_status.py"


def _run(script: Path, args: list[str], timeout_s: float = 30.0) -> tuple[int, str, str]:
    """Run a script via the current interpreter. Returns (rc, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True, text=True,
        cwd=str(REPO), timeout=timeout_s,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    if not SUMMARY_SCRIPT.exists():
        print(f"✗ pre-step: {SUMMARY_SCRIPT} missing")
        return 1
    if not RATCHET_SCRIPT.exists():
        print(f"✗ pre-step: {RATCHET_SCRIPT} missing")
        return 1

    # ── Step 1: POSITIVE — catalog_summary exits 0 in both modes ──
    rc_text, _, _ = _run(SUMMARY_SCRIPT, [])
    rc_json, json_out, _ = _run(SUMMARY_SCRIPT, ["--json"])
    if rc_text != 0 or rc_json != 0:
        print(f"✗ step 1: catalog_summary exits text={rc_text} json={rc_json}, "
              "expected both 0")
        return 1
    try:
        summary = json.loads(json_out)
    except json.JSONDecodeError as exc:
        print(f"✗ step 1: catalog_summary --json output not valid JSON: {exc}")
        return 1
    print("✓ step 1: catalog_summary exits 0 in both text + --json modes")

    # ── Step 2: NEGATIVE — total_drills matches disk count ──
    actual_count = len(list(DRILL_DIR.glob("drill_*.py")))
    if summary.get("total_drills") != actual_count:
        print(f"✗ step 2: total_drills={summary.get('total_drills')}, "
              f"actual files on disk={actual_count}")
        return 1
    print(f"✓ step 2: total_drills={actual_count} matches disk count")

    # ── Step 3: NEGATIVE — source counts sum to total ──
    sc = summary.get("resource_source_counts", {})
    sc_total = sc.get("zero", 0) + sc.get("tagged", 0) + sc.get("defaulted", 0)
    if sc_total != actual_count:
        print(f"✗ step 3: source counts (zero={sc.get('zero',0)} + "
              f"tagged={sc.get('tagged',0)} + defaulted={sc.get('defaulted',0)}) "
              f"= {sc_total}, expected {actual_count}")
        return 1
    print("✓ step 3: resource_source_counts sum to total_drills "
          "(no silent drops)")

    # ── Step 4: NEGATIVE — ratchet_status exits 0 (HEALTHY) ──
    # Currently the catalog has 0 drift across all ratchets after
    # the parallel-stream cleanup. If this fires, drift accumulated
    # somewhere — investigate before next iteration.
    rc, ratchet_out, _ = _run(RATCHET_SCRIPT, [])
    if rc != 0:
        print(f"✗ step 4: ratchet_status exit {rc}, expected 0 "
              "(HEALTHY = clean ratchets). New drift accumulated?")
        return 1
    print("✓ step 4: ratchet_status exits 0 (HEALTHY — all ratchets clean)")

    # ── Step 5: NEGATIVE — ratchet JSON has required schema ──
    rc, json_out, _ = _run(RATCHET_SCRIPT, ["--json"])
    try:
        ratchet = json.loads(json_out)
    except json.JSONDecodeError as exc:
        print(f"✗ step 5: ratchet_status --json invalid: {exc}")
        return 1
    required_keys = [
        "ratchet_state",
        "known_missing_count",
        "resources_new_drift",
        "known_missing_neg_marker_count",
        "neg_new_drift",
        "section7_allowed_paths_count",
        "section7_extra_paths",
    ]
    missing = [k for k in required_keys if k not in ratchet]
    if missing:
        print(f"✗ step 5: ratchet_status JSON missing keys: {missing}")
        return 1
    print(f"✓ step 5: ratchet_status JSON has all {len(required_keys)} required fields")

    # ── Step 6: NEGATIVE — exit code matches ratchet_state enum ──
    expected_exit = {"HEALTHY": 0, "WARNING": 1, "ERROR": 2}
    state = ratchet.get("ratchet_state")
    if state not in expected_exit:
        print(f"✗ step 6: unknown ratchet_state {state!r}; "
              f"expected one of {list(expected_exit)}")
        return 1
    if rc != expected_exit[state]:
        print(f"✗ step 6: ratchet_state={state!r} but exit={rc}, "
              f"expected {expected_exit[state]}")
        return 1
    print(f"✓ step 6: exit code matches ratchet_state enum "
          f"(state={state} → exit={rc})")

    # ── Step 7: NEGATIVE — catalog_summary delegates to ratchet_status ──
    if summary.get("ratchets") is None:
        print("✗ step 7: catalog_summary['ratchets'] is None even though "
              "ratchet_status.py exists at expected path. Delegation broken.")
        return 1
    print("✓ step 7: catalog_summary['ratchets'] populated via delegation")

    # ── Step 8: POSITIVE — integration consistency ──
    # catalog_summary's reported ratchets.ratchet_state should match
    # what ratchet_status.py reports directly. Drift between the two
    # would silently produce inconsistent operator views.
    delegated_state = summary["ratchets"].get("ratchet_state")
    if delegated_state != state:
        print(f"✗ step 8: catalog_summary reports state={delegated_state!r} "
              f"but ratchet_status direct reports state={state!r}. "
              "Inconsistent views.")
        return 1
    print(f"✓ step 8: catalog_summary + ratchet_status agree "
          f"(state={state} via both paths)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
