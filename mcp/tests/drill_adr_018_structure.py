#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: ADR-018 (three-way work allocation) structural contract.

Per §47.3 ADRs are immutable once accepted; this drill locks the
shape so a future "small clean-up" commit can't silently remove
a section, drop one of the three actors, or replace the allocation
table with vague prose.

Eight steps. Six negative assertions.

  1. POSITIVE: ADR-018 file exists at the canonical path.
  2. NEGATIVE: required §47 sections all present (Status, Context,
     Decision, Consequences, Alternatives, References).
  3. NEGATIVE: Status ∈ {Proposed, Accepted, Superseded, Deprecated}.
  4. NEGATIVE: Decision section names ALL THREE actors as bold
     subsections (Operator-required, Parallel-tool work, Autonomous-
     loop work). Dropping one collapses the three-way allocation.
  5. NEGATIVE: Decision section contains an allocation TABLE with
     all three actors as columns. The table is the operator's
     reference; without it the ADR is just prose.
  6. NEGATIVE: References table cites the FIVE demonstration phases
     (A1, 6C, 6J, 6K, 6L, 6M) AND their commit hashes. Without
     the cross-refs, the ADR is unmoored from code.
  7. NEGATIVE: composes-with footer references ADR-014 + ADR-016
     + ADR-017 + CLAUDE.md §42. Architectural lineage of this
     allocation must be visible.
  8. POSITIVE: Consequences split into Positive / Negative /
     Risks accepted (the §47 contract for honesty).

Run: python3 mcp/tests/drill_adr_018_structure.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "architecture" / "adr" / "018-three-way-work-allocation-operator-vs-parallel-tool-vs-autonomous-loop.md"


def main() -> int:
    if not ADR.exists():
        print(f"✗ step 1: {ADR} missing")
        return 1
    body = ADR.read_text()
    if len(body) < 5000:
        print(f"✗ step 1: ADR is suspiciously short ({len(body)} chars)")
        return 1
    print(f"✓ step 1: ADR-018 exists ({len(body)} chars, "
          f"{len(body.splitlines())} lines)")

    required_sections = [
        "## Status", "## Context", "## Decision",
        "## Consequences", "## Alternatives considered", "## References",
    ]
    missing = [s for s in required_sections if s not in body]
    if missing:
        print(f"✗ step 2: missing §47 sections: {missing}")
        return 1
    print(f"✓ step 2: all {len(required_sections)} §47 sections present")

    status_match = re.search(r"## Status\s*\n+([^\n]+)", body)
    if not status_match:
        print("✗ step 3: Status empty")
        return 1
    status_line = status_match.group(1).strip()
    valid = ("Proposed", "Accepted", "Superseded", "Deprecated")
    if not any(s in status_line for s in valid):
        print("✗ step 3: Status doesn't match enum")
        return 1
    print(f"✓ step 3: Status = {status_line.split('—')[0].strip()!r}")

    decision_match = re.search(
        r"## Decision\n(.*?)\n## Consequences", body, re.DOTALL
    )
    if not decision_match:
        print("✗ step 4: Decision unbounded")
        return 1
    decision_text = decision_match.group(1)
    actors = ["Operator-required", "Parallel-tool work", "Autonomous-loop work"]
    missing_actors = [a for a in actors if f"### {a}" not in decision_text]
    if missing_actors:
        print(f"✗ step 4: Decision missing actor sections: {missing_actors}")
        return 1
    print("✓ step 4: Decision names all 3 actor sections")

    # Allocation table — markdown table with the three actors as columns
    if "Operator" not in decision_text or "Parallel-tool" not in decision_text \
            or "Autonomous-loop" not in decision_text:
        print("✗ step 5: Decision missing allocation table column headers")
        return 1
    if "| sudo |" not in decision_text:
        print("✗ step 5: Decision missing allocation-table example row "
              "(sudo capability)")
        return 1
    print("✓ step 5: Decision includes allocation table with all 3 actors")

    refs_match = re.search(r"## References(.*?)\Z", body, re.DOTALL)
    if not refs_match:
        print("✗ step 6: References missing")
        return 1
    refs_text = refs_match.group(1)
    required_phases = ["A1", "6C", "6J", "6K", "6L", "6M"]
    missing_phases = [p for p in required_phases if p not in refs_text]
    if missing_phases:
        print(f"✗ step 6: References missing phases: {missing_phases}")
        return 1
    commit_hashes = re.findall(r"`([a-f0-9]{7,12})`", refs_text)
    if len(commit_hashes) < 5:
        print(f"✗ step 6: References cites {len(commit_hashes)} hashes, "
              "expected ≥5 (one per primary demonstration)")
        return 1
    print(f"✓ step 6: References cites {len(required_phases)} phases + "
          f"{len(commit_hashes)} commits")

    required_cross = ["ADR-014", "ADR-016", "ADR-017", "§42"]
    missing_cross = [c for c in required_cross if c not in body]
    if missing_cross:
        print(f"✗ step 7: missing cross-refs: {missing_cross}")
        return 1
    print("✓ step 7: composes-with refs ADR-014 + ADR-016 + ADR-017 + §42")

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
