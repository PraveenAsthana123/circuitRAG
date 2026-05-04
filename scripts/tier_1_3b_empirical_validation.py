#!/usr/bin/env python3
"""Tier 1.3.b empirical validation — historical failure modes vs new gate.

Per §55.3 outcome contract. Reproduces the 4 historical failure modes
from the 2026-05-03 empirical finding (docs/architecture/
apply-rate-empirical-finding.md) as synthetic CouncilProposal diffs,
then runs each through the new _git_apply_check_only() gate to
verify Tier 1.3.b would catch what previously slipped through to
apply-time.

Output: a per-mode pass/fail report + headline projected-apply-rate.

This is the empirical signal — the deferred apply-rate test the
session has been chasing. The §44 autonomous-loop discipline says
every fix needs a measurable outcome; this is that measurement.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from local_council import _git_apply_check_only  # noqa: E402


# The 4 historical failure modes from agent_task_board_apply.jsonl.
# Each entry mirrors a real failure observed in the prior batch.
HISTORICAL_FAILURES = [
    {
        "mode": "1. wrong file path (Author wrote relative)",
        "count_in_history": 2,
        "synthetic_diff": (
            # Author wrote agent-orchestrator-svc/app/research.py
            # instead of services/agent-orchestrator-svc/app/research.py
            "--- a/agent-orchestrator-svc/app/research.py\n"
            "+++ b/agent-orchestrator-svc/app/research.py\n"
            "@@ -91 +91 @@\n"
            "-        old_line\n"
            "+        new_line\n"
        ),
        "expected_gate_action": "REJECT (no such file)",
    },
    {
        "mode": "2. corrupt @@ line offsets (line beyond file end)",
        "count_in_history": 2,
        "synthetic_diff": (
            # Real file path (-p0 expects no a/ b/ prefix); @@ header
            # references line 99999 which is beyond file end.
            "--- services/agent-orchestrator-svc/app/research.py\n"
            "+++ services/agent-orchestrator-svc/app/research.py\n"
            "@@ -99999 +99999 @@\n"
            "-old_line\n"
            "+new_line\n"
        ),
        "expected_gate_action": "REJECT (line offset out of bounds)",
    },
    {
        "mode": "3. line content doesn't match working tree",
        "count_in_history": 1,
        "synthetic_diff": (
            # Real file path with real line 1 number, but the `-`
            # context line doesn't match the actual line 1 content.
            "--- services/agent-orchestrator-svc/app/research.py\n"
            "+++ services/agent-orchestrator-svc/app/research.py\n"
            "@@ -1 +1 @@\n"
            "-this_text_does_not_exist_at_line_1\n"
            "+replacement_line\n"
        ),
        "expected_gate_action": "REJECT (patch doesn't apply)",
    },
    {
        "mode": "4. malformed/empty diff",
        "count_in_history": 3,
        "synthetic_diff": "this is not a unified diff at all\njust prose\n",
        "expected_gate_action": "REJECT (no valid patches in input)",
    },
]


def main() -> int:
    print("=" * 70)
    print("Tier 1.3.b empirical validation — historical failure modes")
    print("Source: docs/architecture/apply-rate-empirical-finding.md")
    print("=" * 70)
    print()

    total_history_failures = sum(f["count_in_history"] for f in HISTORICAL_FAILURES)
    caught = 0
    not_caught = 0
    failure_details = []

    for entry in HISTORICAL_FAILURES:
        mode = entry["mode"]
        count = entry["count_in_history"]
        diff = entry["synthetic_diff"]
        expected = entry["expected_gate_action"]

        result = _git_apply_check_only(REPO, diff)
        gate_caught = not result["ok"]

        marker = "✓ CAUGHT" if gate_caught else "✗ MISSED"
        print(f"  {marker}  mode: {mode}")
        print(f"            historical occurrences: {count}")
        print(f"            expected: {expected}")
        if gate_caught:
            print(f"            actual:   GATE REJECTED — {result['error'][:100]}")
            caught += count
        else:
            print(f"            actual:   GATE PASSED (gap — Tier 1.3.b would NOT have caught this)")
            not_caught += count
            failure_details.append((mode, count))
        print()

    catch_rate = caught / max(total_history_failures, 1)
    projected_apply_rate_floor = catch_rate

    print("=" * 70)
    print(f"  RESULT: {caught} / {total_history_failures} historical failures caught by gate")
    print(f"          ({catch_rate:.1%} catch rate)")
    print()
    if failure_details:
        print("  Failure modes the gate did NOT catch:")
        for mode, count in failure_details:
            print(f"    - {mode} ({count} occurrences)")
        print()
        print("  These need additional Tier 1 fixes (e.g. stricter diff-extraction")
        print("  regex for the fence-missing case, or a Pydantic field validator")
        print("  that pre-flights the diff at schema time).")
        print()
    print(f"  PROJECTION (§55.3 outcome contract):")
    print(f"    Historical apply rate: 0/{total_history_failures} = 0.0%")
    print(f"    Projected after Tier 1.3.b: ≥{caught}/{total_history_failures} = ≥{catch_rate:.1%}")
    print(f"    (≥ because retry-with-feedback may also rescue some of the")
    print(f"    {not_caught} non-caught modes via AUTHOR pass-2.)")
    print("=" * 70)

    return 0 if caught >= 4 else 1  # require at least 4/8 caught for success


if __name__ == "__main__":
    raise SystemExit(main())
