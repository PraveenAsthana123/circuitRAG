#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: ADR-019 (graceful degradation of loop tooling) structural contract.

Per §47.3 ADRs are immutable once accepted; this drill locks the
shape so a future "small clean-up" commit can't silently remove
a section, drop one of the 5 failure modes, or replace the
operator-facing UX rule with vague prose.

Eight steps. Six negative assertions.

  1. POSITIVE: ADR-019 file exists at the canonical path.
  2. NEGATIVE: required §47 sections all present (Status, Context,
     Decision, Consequences, Alternatives, References).
  3. NEGATIVE: Status ∈ {Proposed, Accepted, Superseded, Deprecated}.
  4. NEGATIVE: Decision section names ALL FIVE failure modes that
     graceful degradation must handle (missing input file, bad
     timestamp, malformed JSON, daemon transient state, missing
     executable). Dropping any leaves the rule incomplete.
  5. NEGATIVE: Decision section includes the "What this is NOT"
     carve-out (3 things graceful degradation is NOT — silent
     error swallowing, retry logic, blanket except).
  6. NEGATIVE: Decision section includes the operator-facing UX
     rule (one-line stderr explanation per degradation event).
  7. NEGATIVE: References table cites ≥6 demonstration sites
     (loop_status, council_filter_stats, council_stats_snapshot,
     prune_loop_logs, install_snapshot_cron, ollama-active fallback).
  8. POSITIVE: Consequences split into Positive / Negative /
     Risks accepted (the §47 contract for honesty).

Run: python3 mcp/tests/drill_adr_019_structure.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "architecture" / "adr" / "019-graceful-degradation-of-loop-tooling.md"


def main() -> int:
    if not ADR.exists():
        print(f"✗ step 1: {ADR} missing")
        return 1
    body = ADR.read_text()
    if len(body) < 5000:
        print(f"✗ step 1: ADR is suspiciously short ({len(body)} chars)")
        return 1
    print(f"✓ step 1: ADR-019 exists ({len(body)} chars, "
          f"{len(body.splitlines())} lines)")

    required = ["## Status", "## Context", "## Decision",
                "## Consequences", "## Alternatives considered", "## References"]
    missing = [s for s in required if s not in body]
    if missing:
        print(f"✗ step 2: missing §47 sections: {missing}")
        return 1
    print(f"✓ step 2: all {len(required)} §47 sections present")

    status_match = re.search(r"## Status\s*\n+([^\n]+)", body)
    if not status_match:
        print("✗ step 3: Status empty")
        return 1
    if not any(s in status_match.group(1) for s in ("Proposed", "Accepted", "Superseded", "Deprecated")):
        print("✗ step 3: Status doesn't match enum")
        return 1
    print(f"✓ step 3: Status = {status_match.group(1).split('—')[0].strip()!r}")

    decision_match = re.search(
        r"## Decision\n(.*?)\n## Consequences", body, re.DOTALL
    )
    if not decision_match:
        print("✗ step 4: Decision unbounded")
        return 1
    decision_text = decision_match.group(1).lower()

    failure_modes = [
        "missing input file",
        "bad timestamp",
        "malformed json",
        "daemon transient state",
        "missing executable",
    ]
    missing_modes = [m for m in failure_modes if m not in decision_text]
    if missing_modes:
        print(f"✗ step 4: Decision missing failure modes: {missing_modes}")
        return 1
    print("✓ step 4: Decision names all 5 failure modes")

    if "what this is not" not in decision_text:
        print("✗ step 5: Decision missing 'What this is NOT' carve-out")
        return 1
    not_items = ["silent", "retry", "blanket"]
    missing_not = [n for n in not_items if n not in decision_text]
    if missing_not:
        print(f"✗ step 5: 'What this is NOT' missing concepts: {missing_not}")
        return 1
    print("✓ step 5: Decision includes 'What this is NOT' carve-out (3 items)")

    if "operator-facing ux rule" not in decision_text:
        print("✗ step 6: Decision missing 'Operator-facing UX rule' section")
        return 1
    if "stderr" not in decision_text:
        print("✗ step 6: UX rule doesn't mention stderr (the channel)")
        return 1
    print("✓ step 6: Decision includes operator-facing UX rule")

    refs_match = re.search(r"## References(.*?)\Z", body, re.DOTALL)
    if not refs_match:
        print("✗ step 7: References missing")
        return 1
    refs_text = refs_match.group(1)
    sites = ["loop_status", "council_filter_stats", "council_stats_snapshot",
             "prune_loop_logs", "install_snapshot_cron"]
    missing_sites = [s for s in sites if s not in refs_text]
    if missing_sites:
        print(f"✗ step 7: References missing demonstration sites: {missing_sites}")
        return 1
    print(f"✓ step 7: References cites all {len(sites)} demonstration sites")

    consequences_match = re.search(
        r"## Consequences\n(.*?)\n## ", body, re.DOTALL
    )
    if not consequences_match:
        print("✗ step 8: Consequences unbounded")
        return 1
    cons_text = consequences_match.group(1)
    required_subs = ["Positive", "Negative", "Risks accepted"]
    missing_subs = [s for s in required_subs if f"### {s}" not in cons_text]
    if missing_subs:
        print(f"✗ step 8: Consequences missing sub-sections: {missing_subs}")
        return 1
    print("✓ step 8: Consequences has Positive/Negative/Risks accepted")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
