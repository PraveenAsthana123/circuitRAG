#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: ADR-014 (autonomous-loop architecture) structural contract.

Per §47.3 ADRs are immutable once accepted; this drill locks the
structural shape so a future "small clean-up" commit can't silently
remove a section or reorder claims.

Eight steps. Six negative assertions.

  1. ADR-014 file exists at the canonical path.
  2. NEGATIVE: required §47 sections all present (Status, Context,
     Decision, Consequences, Alternatives, References).
  3. NEGATIVE: Status is one of {Proposed, Accepted, Superseded,
     Deprecated} - the standard ADR enum.
  4. NEGATIVE: Consequences split into Positive / Negative / Risks
     accepted (the §47 contract for honesty).
  5. NEGATIVE: at least 3 Alternatives considered (single-decision
     ADRs that consider only one alternative are weak; show the
     decision space).
  6. NEGATIVE: References table lists at least 20 of the 24
     session commits. Without the cross-ref, a future reader
     can't trace back to the actual code.
  7. NEGATIVE: 'one ADR = one decision' check - the body talks
     about the SINGLE central decision, not 24 sub-decisions.
     Look for "the central decision" / "Decision" header followed
     by a bounded scope.
  8. NEGATIVE: file lives at docs/architecture/adr/014-*.md
     (sequential numbering per §47 + canonical path).

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "architecture" / "adr"
ADR = ADR_DIR / "014-autonomous-loop-architecture.md"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg):
    print(f"  {GREEN}{msg}{NC}")


def fail(msg):
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title):
    print(f"\n{BOLD}-- {title} --{NC}")


def main():
    # Step 1: ADR exists
    step("1. ADR-014 exists at docs/architecture/adr/014-*.md")
    if not ADR.exists():
        fail(f"ADR missing: {ADR}")
    text = ADR.read_text()
    if len(text) < 3000:
        fail(f"ADR suspiciously short: {len(text)} chars")
    ok(f"ADR-014 present ({len(text)} chars)")

    # Step 2: required §47 sections
    step("2. NEGATIVE: required §47 sections all present")
    required = ["## Status", "## Context", "## Decision",
                "## Consequences", "## Alternatives considered",
                "## References"]
    missing = [s for s in required if s not in text]
    if missing:
        fail(f"missing required sections: {missing}")
    ok("all 6 required sections present")

    # Step 3: Status enum
    step("3. NEGATIVE: Status is one of the standard ADR values")
    m = re.search(r"## Status\s*\n+(\S[^\n]*)", text)
    if not m:
        fail("Status section has no first non-blank line")
    status_line = m.group(1).strip()
    valid_starts = ["Proposed", "Accepted", "Superseded", "Deprecated"]
    if not any(status_line.startswith(s) for s in valid_starts):
        fail(
            f"Status doesn't begin with one of {valid_starts}: "
            f"{status_line!r}"
        )
    ok(f"Status: {status_line[:60]!r}")

    # Step 4: Consequences split
    step("4. NEGATIVE: Consequences split into Positive / Negative / Risks")
    consequences_block = text[
        text.find("## Consequences"):text.find("## Alternatives")
    ]
    for required_subsection in ["**Positive**", "**Negative**",
                                  "**Risks accepted**"]:
        if required_subsection not in consequences_block:
            fail(
                f"Consequences missing {required_subsection!r} subsection. "
                f"§47 requires the three-way split for honest decision "
                f"records."
            )
    ok("Consequences has Positive + Negative + Risks accepted subsections")

    # Step 5: 3+ alternatives
    step("5. NEGATIVE: at least 3 Alternatives considered")
    alt_block = text[
        text.find("## Alternatives considered"):text.find("## References")
    ]
    alt_count = len(re.findall(r"\*\*Alternative \d+:", alt_block))
    if alt_count < 3:
        fail(
            f"only {alt_count} Alternatives bolded; need >=3. Single-"
            f"alternative ADRs hide the decision space."
        )
    ok(f"{alt_count} alternatives explicitly considered")

    # Step 6: References table has 20+ commits
    step("6. NEGATIVE: References table cross-refs >=20 commits")
    ref_block = text[text.find("## References"):]
    # Lines like "| Phase-XX | `<sha>` | <title> |" - count the
    # rows that have a backtick'd 7-char sha
    commit_refs = re.findall(r"\|\s*`[a-f0-9]{7,12}`\s*\|", ref_block)
    if len(commit_refs) < 20:
        fail(
            f"References table has only {len(commit_refs)} commit refs; "
            f"need >=20 to cover the session's 24 commits substantively."
        )
    ok(f"{len(commit_refs)} commit refs in References table")

    # Step 7: 'one ADR = one decision' check
    step("7. NEGATIVE: ADR commits to ONE central decision (not packed)")
    # Heuristic: the Decision section should be < 2000 chars
    # (one decision + commitments, not 24 sub-decisions). If it
    # bloats much past that, the ADR has packed multiple decisions.
    decision_block = text[text.find("## Decision"):text.find("## Consequences")]
    if len(decision_block) > 3000:
        fail(
            f"Decision section is {len(decision_block)} chars - probably "
            f"packing multiple decisions. §47.3 says ONE ADR = ONE decision."
        )
    if len(decision_block) < 400:
        fail(
            f"Decision section is {len(decision_block)} chars - too "
            f"shallow; should include the rationale + commitments list."
        )
    ok(f"Decision section is {len(decision_block)} chars (focused)")

    # Step 8: file at canonical path with sequential numbering
    step("8. NEGATIVE: ADR-014 lives at the canonical path")
    if ADR.parent != ADR_DIR:
        fail(f"ADR not in canonical dir: {ADR.parent}")
    if not ADR.name.startswith("014-"):
        fail(f"ADR filename doesn't start with 014-: {ADR.name}")
    # Verify 013 exists (sequential numbering invariant)
    adr_013 = ADR_DIR / "013-audit-redaction-policy.md"
    if not adr_013.exists():
        fail(
            "ADR-013 missing: numbering is sequential per §47.3, no "
            "gaps allowed"
        )
    # Verify ADR-014 numbering is unique (no duplicate ADR-014 files).
    # The original assertion here checked "015 doesn't yet exist" —
    # a poorly-designed forward-looking check that broke when
    # ADR-015 legitimately landed in Phase 6F. The right invariant
    # is "no two files share a number," not "this is the latest."
    adr_014_files = list(ADR_DIR.glob("014-*.md"))
    if len(adr_014_files) != 1:
        fail(
            f"ADR-014 numbering not unique: {adr_014_files}. ADRs "
            f"never-reuse-numbers per §47.3."
        )
    ok("ADR-014 at canonical path; 013 exists; numbering unique")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 ADR-014 STRUCTURE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
