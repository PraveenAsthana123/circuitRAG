#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: ADR-017 (forward-looking checks anti-pattern) structural contract.

Per §47.3 ADRs are immutable once accepted; this drill locks the
shape so a future "small clean-up" commit can't silently remove
a section, drop a demonstration row, or replace concrete examples
with vague prose.

Eight steps. Six negative assertions.

  1. POSITIVE: ADR-017 file exists at the canonical path
     (docs/architecture/adr/017-*.md, sequential per §47).
  2. NEGATIVE: required §47 sections all present (Status, Context,
     Decision, Consequences, Alternatives, References).
  3. NEGATIVE: Status is one of {Proposed, Accepted, Superseded,
     Deprecated} — the standard ADR enum.
  4. NEGATIVE: Decision section presents BOTH halves of the rule:
     (a) the anti-pattern (forward-looking checks) AND (b) the
     discipline that catches it (sweep-before-commit). Dropping
     either leaves the rule incomplete.
  5. NEGATIVE: Decision section names the FIVE high-blast-radius
     surfaces that trigger the sweep-before-commit discipline
     (sidecar/, sidecar-advisor/, mcp/server*.py, ADR files,
     scripts, drill files). These are the load-bearing scope.
  6. NEGATIVE: References table cites the FOUR demonstration
     phases (5Z, 5Y/6F, 6G) AND their commit hashes. Without
     the cross-refs, the ADR is unmoored from code.
  7. NEGATIVE: composes-with footer references ADR-014 + ADR-015
     + ADR-016. The architectural lineage of this safety
     discipline must be visible.
  8. POSITIVE: Consequences split into Positive / Negative /
     Risks accepted (the §47 contract for honesty about
     trade-offs).

Run: python3 mcp/tests/drill_adr_017_structure.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "architecture" / "adr" / "017-forward-looking-checks-and-sweep-before-commit-discipline.md"


def main() -> int:
    # ── Step 1: file exists ──
    if not ADR.exists():
        print(f"✗ step 1: {ADR} missing")
        return 1
    body = ADR.read_text()
    if len(body) < 4000:
        print(f"✗ step 1: ADR is suspiciously short ({len(body)} chars)")
        return 1
    print(f"✓ step 1: ADR-017 exists ({len(body)} chars, "
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
        print(f"✗ step 3: Status doesn't match enum {valid_statuses}")
        return 1
    print(f"✓ step 3: Status = {status_line.split('—')[0].strip()!r}")

    # ── Step 4: NEGATIVE — Decision presents BOTH halves ──
    decision_match = re.search(
        r"## Decision\n(.*?)\n## Consequences", body, re.DOTALL
    )
    if not decision_match:
        print("✗ step 4: Decision section unbounded")
        return 1
    decision_text = decision_match.group(1).lower()
    halves = ["anti-pattern", "discipline"]
    missing_halves = [h for h in halves if h not in decision_text]
    if missing_halves:
        print(f"✗ step 4: Decision missing halves: {missing_halves}")
        return 1
    # Both must be marked as bold-decision points
    if "**anti-pattern: forward-looking" not in decision_text:
        print("✗ step 4: Decision doesn't bold-mark the anti-pattern statement")
        return 1
    if "**discipline:" not in decision_text:
        print("✗ step 4: Decision doesn't bold-mark the discipline statement")
        return 1
    print("✓ step 4: Decision presents both halves "
          "(anti-pattern + discipline)")

    # ── Step 5: NEGATIVE — FIVE HBR surfaces in Decision ──
    # Each surface should appear in the high-blast-radius list:
    hbr_surfaces = [
        "sidecar/",                         # 1 frontend sidecar
        "sidecar-advisor/",                 # 2 advisor service
        "mcp/server",                       # 3 MCP servers
        "adr/",                             # 4 ADR files
        "drill_*.py",                       # 5 drill changes
    ]
    missing_hbr = [s for s in hbr_surfaces if s.lower() not in decision_text]
    if missing_hbr:
        print(f"✗ step 5: Decision missing HBR surfaces: {missing_hbr}")
        return 1
    print("✓ step 5: Decision lists all 5 HBR surfaces "
          "for sweep-before-commit")

    # ── Step 6: NEGATIVE — References cites the demonstration phases ──
    refs_match = re.search(r"## References(.*?)\Z", body, re.DOTALL)
    if not refs_match:
        print("✗ step 6: References section missing")
        return 1
    refs_text = refs_match.group(1)
    # The four demonstrations: 5Z (twice — different drills), 6F, 6G
    required_phases = ["5Z", "6F", "6G"]
    missing_phases = [p for p in required_phases if p not in refs_text]
    if missing_phases:
        print(f"✗ step 6: References missing demonstration phases: {missing_phases}")
        return 1
    commit_hashes = re.findall(r"`([a-f0-9]{7,12})`", refs_text)
    if len(commit_hashes) < 3:
        print(f"✗ step 6: References cites {len(commit_hashes)} commit hashes, "
              "expected ≥3 (one per demonstration phase)")
        return 1
    print(f"✓ step 6: References cites all {len(required_phases)} phases "
          f"+ {len(commit_hashes)} commits")

    # ── Step 7: NEGATIVE — composes-with cross-refs ──
    required_cross = ["ADR-014", "ADR-015", "ADR-016"]
    missing_cross = [c for c in required_cross if c not in body]
    if missing_cross:
        print(f"✗ step 7: missing architectural cross-refs: {missing_cross}")
        return 1
    print("✓ step 7: composes-with refs ADR-014 + ADR-015 + ADR-016")

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
    print("✓ step 8: Consequences has Positive/Negative/Risks accepted")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
