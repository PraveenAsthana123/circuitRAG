#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: ADR-016 (parallel-agent allocation pattern) structural contract.

Per §47.3 ADRs are immutable once accepted; this drill locks the
structural shape so a future "small clean-up" commit can't silently
remove a section, drop a precondition, or replace concrete reference
rows with vague prose.

Eight steps. Six negative assertions.

  1. POSITIVE: ADR-016 file exists at the canonical path
     (docs/architecture/adr/016-*.md, sequential per §47).
  2. NEGATIVE: required §47 sections all present (Status, Context,
     Decision, Consequences, Alternatives, References).
  3. NEGATIVE: Status is one of {Proposed, Accepted, Superseded,
     Deprecated} — the standard ADR enum.
  4. NEGATIVE: Decision section names the FIVE preconditions for
     parallel-agent allocation (independent files, concrete spec,
     drill exists, work large enough, output independently
     verifiable). Dropping any leaves the rule incomplete.
  5. NEGATIVE: Decision section names the THREE allocation
     patterns (A: one agent + foreground drill; B: N agents
     chunked; C: two parallel streams converging). Each maps to
     a distinct shape of work; dropping one collapses the
     pattern's expressiveness.
  6. NEGATIVE: References table cites the FOUR demonstration
     phases (5S, 6C, 6J, 6K) AND their commit hashes. Without
     the commit cross-refs, the ADR is unmoored from the code.
  7. NEGATIVE: composes-with footer references ADR-014 + ADR-015
     + the autonomous-feature-loop policy. The architectural
     lineage is invisible without these.
  8. POSITIVE: Consequences split into Positive / Negative /
     Risks accepted (the §47 contract for honesty about trade-offs).

Run: python3 mcp/tests/drill_adr_016_structure.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "architecture" / "adr" / "016-parallel-agent-allocation-for-independent-n-file-work.md"


def main() -> int:
    # ── Step 1: file exists at canonical path ──
    if not ADR.exists():
        print(f"✗ step 1: {ADR} missing")
        return 1
    body = ADR.read_text()
    if len(body) < 4000:
        print(f"✗ step 1: ADR is suspiciously short ({len(body)} chars)")
        return 1
    print(f"✓ step 1: ADR-016 exists ({len(body)} chars, "
          f"{len(body.splitlines())} lines)")

    # ── Step 2: NEGATIVE — §47 required sections ──
    required_sections = [
        "## Status",
        "## Context",
        "## Decision",
        "## Consequences",
        "## Alternatives considered",
        "## References",
    ]
    missing = [s for s in required_sections if s not in body]
    if missing:
        print(f"✗ step 2: missing §47 sections: {missing}")
        return 1
    print(f"✓ step 2: all {len(required_sections)} §47 sections present")

    # ── Step 3: NEGATIVE — Status enum ──
    status_match = re.search(r"## Status\s*\n+([^\n]+)", body)
    if not status_match:
        print("✗ step 3: Status section empty")
        return 1
    status_line = status_match.group(1).strip()
    valid_statuses = ("Proposed", "Accepted", "Superseded", "Deprecated")
    if not any(s in status_line for s in valid_statuses):
        print(f"✗ step 3: Status {status_line!r} doesn't match enum {valid_statuses}")
        return 1
    print(f"✓ step 3: Status = {status_line.split('—')[0].strip()!r}")

    # ── Step 4: NEGATIVE — FIVE preconditions in Decision ──
    # Anchor on `\n## ` per the 5Z lesson — `## ` inside a `### Heading`
    # would otherwise spuriously match.
    decision_match = re.search(
        r"## Decision\n(.*?)\n## Consequences", body, re.DOTALL
    )
    if not decision_match:
        print("✗ step 4: Decision section unbounded")
        return 1
    decision_text = decision_match.group(1).lower()
    preconditions = [
        "independent files",      # 1
        "concrete enough",         # 2 (spec is concrete)
        "drill exists",            # 3
        "amortize",                # 4 (large enough to amortize agent overhead)
        "verified independently",  # 5
    ]
    missing_pre = [p for p in preconditions if p not in decision_text]
    if missing_pre:
        print(f"✗ step 4: Decision missing preconditions: {missing_pre}")
        return 1
    print(f"✓ step 4: Decision names all 5 parallel-agent preconditions")

    # ── Step 5: NEGATIVE — THREE allocation patterns in Decision ──
    patterns = [
        "**a.",   # A — one agent + foreground drill
        "**b.",   # B — N agents chunked
        "**c.",   # C — two parallel streams converging
    ]
    missing_patterns = [p for p in patterns if p not in decision_text]
    if missing_patterns:
        print(f"✗ step 5: Decision missing allocation patterns: {missing_patterns}")
        return 1
    print(f"✓ step 5: Decision names all 3 allocation patterns (A/B/C)")

    # ── Step 6: NEGATIVE — References cites the FOUR demonstration phases ──
    refs_match = re.search(r"## References(.*?)\Z", body, re.DOTALL)
    if not refs_match:
        print("✗ step 6: References section missing")
        return 1
    refs_text = refs_match.group(1)
    required_phases = ["5S", "6C", "6J", "6K"]
    missing_phases = [p for p in required_phases if p not in refs_text]
    if missing_phases:
        print(f"✗ step 6: References missing demonstration phases: {missing_phases}")
        return 1
    # And ≥4 commit hashes (one per demonstration row)
    commit_hashes = re.findall(r"`([a-f0-9]{7,12})`", refs_text)
    if len(commit_hashes) < 4:
        print(f"✗ step 6: References cites {len(commit_hashes)} commit hashes, "
              "expected ≥4 (one per demonstration phase)")
        return 1
    print(f"✓ step 6: References cites all 4 phases + {len(commit_hashes)} commits")

    # ── Step 7: NEGATIVE — composes-with cross-refs ──
    required_cross = ["ADR-014", "ADR-015", "autonomous-feature-loop"]
    missing_cross = [c for c in required_cross if c not in body]
    if missing_cross:
        print(f"✗ step 7: missing architectural cross-refs: {missing_cross}")
        return 1
    print(f"✓ step 7: composes-with refs ADR-014 + ADR-015 + autonomous-feature-loop")

    # ── Step 8: POSITIVE — Consequences sub-sections ──
    consequences_match = re.search(
        r"## Consequences\n(.*?)\n## ", body, re.DOTALL
    )
    if not consequences_match:
        print("✗ step 8: Consequences section unbounded")
        return 1
    cons_text = consequences_match.group(1)
    required_subs = ["Positive", "Negative", "Risks accepted"]
    missing_subs = [s for s in required_subs if f"### {s}" not in cons_text]
    if missing_subs:
        print(f"✗ step 8: Consequences missing sub-sections: {missing_subs}")
        return 1
    print(f"✓ step 8: Consequences has Positive/Negative/Risks accepted")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
