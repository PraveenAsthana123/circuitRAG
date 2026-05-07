#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: ADR-015 (ratchet pattern for discipline drift) structural contract.

Per §47.3 ADRs are immutable once accepted; this drill locks the
structural shape so a future "clean-up" commit can't silently
remove a section, reorder claims, or replace concrete decision-set
references with vague prose.

Eight steps. Six negative assertions.

  1. POSITIVE: ADR-015 file exists at the canonical path
     (docs/architecture/adr/015-*.md, sequential per §47).
  2. NEGATIVE: required §47 sections all present (Status, Context,
     Decision, Consequences, Alternatives, References).
  3. NEGATIVE: Status is one of {Proposed, Accepted, Superseded,
     Deprecated} — the standard ADR enum.
  4. NEGATIVE: Consequences split into Positive / Negative / Risks
     accepted (the §47 contract for honesty about trade-offs).
  5. NEGATIVE: at least 3 Alternatives considered. ADR-015 lists
     four (Strict, Soft percentage, Ratchet, Per-rule timestamps);
     dropping below 3 would weaken the decision-space presentation.
  6. NEGATIVE: References table cites the THREE ratchets currently
     in production (KNOWN_MISSING,
     KNOWN_MISSING_NEG_MARKER, §7 scope-extension log) AND their
     landing commits. Without these, the ADR is unmoored from
     code.
  7. NEGATIVE: composes-with footer references ADR-014 + §43 + §44.
     The ratchet pattern is a peer of ADR-014's advisory contract
     (same "don't block; log + gate growth" family); without the
     cross-ref the architectural lineage is invisible.
  8. NEGATIVE: file mentions the FIVE ratchet contract elements
     in the Decision section (snapshot drift, gate growth, reward
     shrinkage, refuse mechanical churn, document carve-out).
     Dropping any of these would leave the rule incomplete.

Run: python3 mcp/tests/drill_adr_015_structure.py
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "architecture" / "adr" / "015-ratchet-pattern-for-discipline-drift.md"


def main() -> int:
    # ── Step 1: file exists at canonical path ──
    if not ADR.exists():
        print(f"✗ step 1: {ADR} missing")
        return 1
    body = ADR.read_text()
    if len(body) < 3000:
        print(f"✗ step 1: ADR is suspiciously short ({len(body)} chars)")
        return 1
    print(f"✓ step 1: ADR-015 exists ({len(body)} chars, "
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

    # ── Step 4: NEGATIVE — Consequences sub-sections ──
    # Anchor `## ` to start of line; otherwise the pattern matches
    # INSIDE a `### Heading` line (positions 1-2-3 of `### X` are
    # `#`, `#`, ` `, which spuriously matches `## `). Multi-line
    # mode + `\n## ` is the explicit version.
    consequences_match = re.search(
        r"## Consequences\n(.*?)\n## ", body, re.DOTALL
    )
    if not consequences_match:
        print("✗ step 4: Consequences section unbounded")
        return 1
    cons_text = consequences_match.group(1)
    required_subs = ["Positive", "Negative", "Risks accepted"]
    missing_subs = [s for s in required_subs if f"### {s}" not in cons_text]
    if missing_subs:
        print(f"✗ step 4: Consequences missing sub-sections: {missing_subs}")
        return 1
    print("✓ step 4: Consequences has Positive/Negative/Risks accepted")

    # ── Step 5: NEGATIVE — ≥3 Alternatives ──
    alt_match = re.search(
        r"## Alternatives considered\n(.*?)\n## ", body, re.DOTALL
    )
    if not alt_match:
        print("✗ step 5: Alternatives section unbounded")
        return 1
    alt_text = alt_match.group(1)
    # Each alternative is a ### heading
    alt_count = len(re.findall(r"^### [A-Z]", alt_text, re.MULTILINE))
    if alt_count < 3:
        print(f"✗ step 5: only {alt_count} alternatives considered, expected ≥3")
        return 1
    print(f"✓ step 5: {alt_count} alternatives considered (decision space presented)")

    # ── Step 6: NEGATIVE — References cites all 3 ratchets + commits ──
    refs_match = re.search(r"## References(.*?)\Z", body, re.DOTALL)
    if not refs_match:
        print("✗ step 6: References section missing")
        return 1
    refs_text = refs_match.group(1)
    required_refs = [
        "KNOWN_MISSING",
        "KNOWN_MISSING_NEG_MARKER",
        "scope-extension log",
    ]
    missing_refs = [r for r in required_refs if r not in body]
    if missing_refs:
        print(f"✗ step 6: ADR doesn't reference all ratchets: {missing_refs}")
        return 1
    # Each phase row should have a commit hash (7+ hex chars)
    commit_hashes = re.findall(r"`([a-f0-9]{7,12})`", refs_text)
    if len(commit_hashes) < 3:
        print(f"✗ step 6: References table cites {len(commit_hashes)} commit hashes, "
              "expected ≥3 (one per ratchet)")
        return 1
    print(f"✓ step 6: References cites all 3 ratchets + {len(commit_hashes)} commits")

    # ── Step 7: NEGATIVE — composes-with cross-refs ──
    required_cross = ["ADR-014", "§43", "§44"]
    missing_cross = [c for c in required_cross if c not in body]
    if missing_cross:
        print(f"✗ step 7: missing architectural cross-refs: {missing_cross}")
        return 1
    print("✓ step 7: composes-with refs ADR-014 + §43 + §44 (lineage preserved)")

    # ── Step 8: NEGATIVE — Decision section names FIVE ratchet elements ──
    decision_match = re.search(
        r"## Decision\n(.*?)\n## Consequences", body, re.DOTALL
    )
    if not decision_match:
        print("✗ step 8: Decision section unbounded")
        return 1
    decision_text = decision_match.group(1).lower()
    # The five elements (mapped to keywords likely to appear)
    elements = [
        "snapshot",         # 1. snapshot the current drift set
        "gate growth",      # 2. gate growth
        "shrinkage",        # 3. reward shrinkage
        "mechanical",       # 4. refuse mechanical churn
        "document",         # 5. document the carve-out
    ]
    missing_elements = [e for e in elements if e not in decision_text]
    if missing_elements:
        print(f"✗ step 8: Decision section missing rule elements: {missing_elements}")
        return 1
    print("✓ step 8: Decision section names all 5 ratchet contract elements")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
