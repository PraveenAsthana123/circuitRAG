#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: reports/remaining_pending_tasks.json reconciliation.

Per operator priority list (item #11): "remaining_pending_tasks.json
inaccurate". This drill catches when that report drifts from drill-suite
reality.

Two failure modes the drill catches:
  1. Report claims a drill is PENDING (failing) but the drill actually
     passes live — false-pending; operator wastes time investigating
     a fixed thing.
  2. Report references a drill name that doesn't exist as a file —
     dangling reference; operator can't even reproduce the "failure".

The drill INTENTIONALLY does NOT fail when claimed-failures actually
fail live (that's the report being correct). It ONLY fails when the
report drifts from reality, in either direction.

Eight steps. Six negative.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REPORT = REPO / "reports" / "remaining_pending_tasks.json"
DRILLS_DIR = REPO / "mcp" / "tests"
PY_BIN = "/mnt/deepa/rag/.venv/bin/python"


def _run_drill(drill_name: str) -> tuple[bool, str]:
    """Returns (passed, short_status). drill_name is bare (no .py)."""
    drill_path = DRILLS_DIR / f"{drill_name}.py"
    if not drill_path.exists():
        return False, "MISSING_FILE"
    try:
        proc = subprocess.run(
            [PY_BIN, str(drill_path)],
            capture_output=True, text=True, timeout=60.0,
            cwd=str(REPO),
        )
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as exc:  # noqa: BLE001
        return False, f"RUN_ERROR: {exc}"
    return proc.returncode == 0, "PASS" if proc.returncode == 0 else "FAIL"


def main() -> int:
    print("-- 1. POSITIVE: report file exists + parseable --")
    if not REPORT.exists():
        print(f"x {REPORT.relative_to(REPO)} missing")
        return 1
    try:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"x report not valid JSON: {exc}")
        return 1
    print(f"  ok: report parses; {len(report)} top-level keys")

    print("-- 2. NEGATIVE: report has expected schema (fix_drill_* + other_drill_failures) --")
    fix_keys = [k for k in report if k.startswith("fix_drill_")]
    other = report.get("other_drill_failures", [])
    if not fix_keys and not other:
        print("x report must contain fix_drill_* keys OR other_drill_failures list")
        return 1
    if "other_drill_failures" in report and not isinstance(other, list):
        print(f"x other_drill_failures must be a list; got {type(other)}")
        return 1
    print(f"  ok: {len(fix_keys)} fix_drill_* keys + {len(other)} other_drill_failures entries")

    print("-- 3. NEGATIVE: every fix_drill_* references an EXISTING drill file --")
    # The keys are like "fix_drill_policy_engine" → drill_policy_engine.py
    dangling: list[str] = []
    for key in fix_keys:
        # "fix_drill_X" → "drill_X"
        drill_name = key[len("fix_"):]
        if not (DRILLS_DIR / f"{drill_name}.py").exists():
            dangling.append(f"{key} → {drill_name}.py (missing file)")
    if dangling:
        print(f"x {len(dangling)} dangling fix_drill_* references:")
        for d in dangling[:5]:
            print(f"    - {d}")
        return 1
    print("  ok: every fix_drill_* maps to existing drill file")

    print("-- 4. NEGATIVE: every other_drill_failures entry references an EXISTING drill --")
    dangling_other: list[str] = []
    for entry in other:
        # entries are short names; try drill_<entry>.py
        candidates = [f"drill_{entry}", entry]
        if not any((DRILLS_DIR / f"{c}.py").exists() for c in candidates):
            dangling_other.append(entry)
    if dangling_other:
        print(f"x {len(dangling_other)} dangling other_drill_failures entries:")
        for d in dangling_other[:5]:
            print(f"    - {d!r} (no drill_{d}.py or {d}.py)")
        return 1
    print("  ok: every other_drill_failures entry resolves to a drill")

    print("-- 5. NEGATIVE: claimed-PENDING fix_drill_* must STILL be failing live --")
    # If the report says fix_drill_X is PENDING but drill_X live PASSES,
    # the report is stale — operator wastes time on a fixed thing.
    false_pending: list[str] = []
    for key in fix_keys:
        if report.get(key) != "PENDING":
            continue  # Already marked DONE/etc; not claiming pending
        drill_name = key[len("fix_"):]
        passed, status = _run_drill(drill_name)
        if passed:
            false_pending.append(f"{key}={status} but drill actually PASSES live")
    if false_pending:
        print(f"x {len(false_pending)} claimed-PENDING but actually passing:")
        for fp in false_pending[:5]:
            print(f"    - {fp}")
        print()
        print("  Fix: update reports/remaining_pending_tasks.json — mark these")
        print("  as DONE or remove the entries.")
        return 1
    print("  ok: every claimed-PENDING drill actually fails (or no PENDING entries)")

    print("-- 6. NEGATIVE: claimed-failing other_drill_failures must STILL be failing --")
    # Same drift check for the other_drill_failures list.
    false_failures: list[str] = []
    for entry in other:
        # Find the drill file
        for cand in [f"drill_{entry}", entry]:
            if (DRILLS_DIR / f"{cand}.py").exists():
                passed, status = _run_drill(cand)
                if passed:
                    false_failures.append(f"{entry} ({cand}.py): claimed FAIL, actually PASS")
                break
    if false_failures:
        print(f"x {len(false_failures)} claimed-failing but actually passing:")
        for ff in false_failures[:5]:
            print(f"    - {ff}")
        print()
        print("  Fix: remove these from other_drill_failures in")
        print("  reports/remaining_pending_tasks.json (they're already fixed).")
        return 1
    print("  ok: every other_drill_failures entry actually fails (or list empty)")

    print("-- 7. POSITIVE: gated/operator-approval entries are tagged correctly --")
    # Some entries are GATED_OPERATOR_APPROVAL_REQUIRED (e.g.
    # live_empirical_retest_apply). These are NOT drill names; they
    # should be valid op-states, not drill failures. Drill enforces
    # the labeling vocabulary so future contributors don't conflate
    # "needs human approval" with "drill failing".
    valid_states = {"PENDING", "DONE", "GATED_OPERATOR_APPROVAL_REQUIRED",
                    "DEFERRED", "BLOCKED"}
    invalid_states: list[tuple[str, str]] = []
    for key, value in report.items():
        if key == "other_drill_failures":
            continue  # list, not state
        if key.startswith("_"):
            continue  # metadata convention (e.g. _reconciled_at)
        if not isinstance(value, str):
            continue
        if value not in valid_states:
            invalid_states.append((key, value))
    if invalid_states:
        print(f"x {len(invalid_states)} entries use invalid state vocabulary:")
        for k, v in invalid_states[:5]:
            print(f"    - {k}={v!r} (must be one of {sorted(valid_states)})")
        return 1
    print(f"  ok: state vocabulary clean ({len(valid_states)} allowed states)")

    print("-- 8. POSITIVE: emit reconciliation summary for operator visibility --")
    # Summary helps operators see what's actually still pending.
    pending_claimed = sum(1 for v in report.values() if v == "PENDING")
    gated = sum(
        1 for v in report.values()
        if v == "GATED_OPERATOR_APPROVAL_REQUIRED"
    )
    print("  report state:")
    print(f"    fix_drill_* keys total:        {len(fix_keys)}")
    print(f"    claimed PENDING:               {pending_claimed}")
    print(f"    GATED_OPERATOR_APPROVAL:       {gated}")
    print(f"    other_drill_failures total:    {len(other)}")
    print("  reconciliation status:")
    print(f"    dangling references:           {len(dangling) + len(dangling_other)}")
    print(f"    false-pending (drift):         {len(false_pending) + len(false_failures)}")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
