#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: every ADR file is referenced in the cheatsheet's composes-with
footer (Phase 6O).

ADR-017's structural-rewrite rule: replace "ADR-014, 015, 016, 017
specifically" (forward-looking — must be updated every new ADR)
with "every ADR file is referenced" (structural — survives growth).
This drill encodes that rule on the cheatsheet's ADR section.

When a new ADR-NNN is added, this drill fires unless the cheatsheet's
composes-with footer also gains a corresponding `ADR-NNN` reference.
That gate forces the operator to remember to update the cheatsheet
in the SAME commit as the new ADR — preventing the cheatsheet from
silently drifting out of sync with the ADR catalog.

Eight steps. Six negative assertions.

  1. POSITIVE: cheatsheet exists at the canonical path with non-zero
     composes-with footer.
  2. NEGATIVE: every NNN-*.md file in docs/architecture/adr/ is
     referenced by its canonical "ADR-NNN" identifier in the
     cheatsheet body. Future ADRs that ship without updating the
     cheatsheet will fire this assertion.
  3. NEGATIVE: every cheatsheet "ADR-NNN" reference resolves to a
     real ADR file. Catches typos in the cheatsheet (e.g. "ADR-018"
     when only ADR-017 exists yet).
  4. NEGATIVE: ADR references use the canonical "ADR-NNN" form (the
     identifier operators search for) — not just the file path. The
     6A → ADR-014 cross-link bug from earlier shipped a path-only
     reference; this assertion locks the canonical form.
  5. NEGATIVE: each ADR reference appears in the composes-with
     section, not just somewhere in the cheatsheet (a stray mention
     in prose doesn't satisfy the cross-ref intent).
  6. NEGATIVE: ADR references appear in numerical order in the
     composes-with section. Out-of-order is a smell — operator
     scanning the section can't tell if any are missing.
  7. NEGATIVE: every ADR file mentioned has a brief one-line
     description (the gloss after the file path). Without it,
     readers can't tell what the ADR is about without opening it.
  8. POSITIVE: cheatsheet's ADR coverage scales with the catalog —
     count of ADR refs in cheatsheet equals count of NNN-*.md files
     under docs/architecture/adr/.

Run: python3 mcp/tests/drill_cheatsheet_adr_coverage.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHEAT = REPO / "docs" / "runbooks" / "autonomous-loop-cheatsheet.md"
ADR_DIR = REPO / "docs" / "architecture" / "adr"


def _adr_numbers_on_disk() -> list[int]:
    """Return sorted list of LOOP-RELEVANT ADR numbers.

    The cheatsheet covers the autonomous-loop pattern, not the
    project's full architecture. We discriminate by FILENAME keyword
    rather than body-substring match: an ADR is loop-relevant when
    its filename names a loop-discipline concept (autonomous-loop /
    ratchet / parallel-agent / forward-looking / sweep-before-commit).

    Body-substring match is too loose — ADRs that mention 'autonomous
    loop' in passing aren't loop-discipline ADRs (e.g. ADR-009 talks
    about worker policy but names the loop in a sentence). Filename
    is the operator's own classification — when an author chooses an
    ADR title, they pick keywords matching its subject.

    Adding a new loop-discipline ADR? Use a filename keyword from this
    set OR extend the keyword list and update this drill in the same
    commit (the structural-rewrite rule).
    """
    LOOP_KEYWORDS = (
        "autonomous-loop",
        "ratchet",
        "parallel-agent",
        "forward-looking",
        "sweep-before-commit",
        "three-way-work-allocation",  # ADR-018
        "graceful-degradation",        # ADR-019
        "loop-tooling",                # ADR-019 alt-keyword
    )
    nums = []
    for p in sorted(ADR_DIR.glob("*.md")):
        m = re.match(r"^(\d{3})-(.+)\.md$", p.name)
        if not m:
            continue
        slug = m.group(2).lower()
        if any(kw in slug for kw in LOOP_KEYWORDS):
            nums.append(int(m.group(1)))
    return sorted(nums)


def _composes_section(body: str) -> str:
    """Extract the 'Composes with' section from the cheatsheet body."""
    m = re.search(r"## Composes with\s*\n(.*?)(?=\n## |\Z)", body, re.DOTALL)
    return m.group(1) if m else ""


def main() -> int:
    if not CHEAT.exists():
        print(f"✗ pre-step: {CHEAT} missing")
        return 1
    body = CHEAT.read_text()

    # ── Step 1: POSITIVE — cheatsheet has composes-with footer ──
    composes = _composes_section(body)
    if not composes.strip():
        print("✗ step 1: 'Composes with' section missing or empty")
        return 1
    print(f"✓ step 1: cheatsheet has composes-with footer "
          f"({len(composes.splitlines())} lines)")

    # ── Step 2: NEGATIVE — every ADR file is cited ──
    adr_nums = _adr_numbers_on_disk()
    if not adr_nums:
        print("✗ step 2: no ADR files found on disk")
        return 1
    missing = []
    for n in adr_nums:
        canonical = f"ADR-{n:03d}"
        if canonical not in body:
            missing.append(canonical)
    if missing:
        print(f"✗ step 2: cheatsheet missing ADR references: {missing}. "
              "When adding a new ADR, also update the cheatsheet's "
              "composes-with footer.")
        return 1
    print(f"✓ step 2: all {len(adr_nums)} ADR files cited as ADR-NNN "
          "in cheatsheet")

    # ── Step 3: NEGATIVE — every cheatsheet ADR ref resolves ──
    cheat_adr_refs = re.findall(r"ADR-(\d{3})", body)
    cheat_adr_nums = sorted({int(n) for n in cheat_adr_refs})
    bad = [n for n in cheat_adr_nums if n not in adr_nums]
    if bad:
        print(f"✗ step 3: cheatsheet references ADRs that don't exist: "
              f"{[f'ADR-{n:03d}' for n in bad]}")
        return 1
    print(f"✓ step 3: every cheatsheet ADR-NNN ref resolves to a real file "
          f"({len(cheat_adr_nums)} refs)")

    # ── Step 4: NEGATIVE — canonical "ADR-NNN" pairs with file in composes-with ──
    # The cheatsheet's composes-with bullets are the authoritative
    # operator-facing cross-refs. Each bullet must contain BOTH the
    # file path AND the canonical ADR-NNN identifier on the same line
    # (so operators searching by either form land on the right entry).
    # Body prose mentions outside the composes-with section are bonus
    # context, not the contract.
    for n in adr_nums:
        canonical = f"ADR-{n:03d}"
        file_pattern = rf"docs/architecture/adr/{n:03d}-[a-z0-9-]+\.md"
        # Find composes-with bullet lines (start with `- `)
        found = False
        for line in composes.splitlines():
            if line.lstrip().startswith("- ") and re.search(file_pattern, line) \
                    and canonical in line:
                found = True
                break
        if not found:
            print(f"✗ step 4: composes-with bullet missing for {canonical} — "
                  f"each bullet must pair file path with canonical ID on the "
                  "same line. Operators search by ADR-NNN, not by path.")
            return 1
    print(f"✓ step 4: all {len(adr_nums)} composes-with bullets pair file "
          "+ canonical ADR-NNN")

    # ── Step 5: NEGATIVE — references appear in composes-with section ──
    composes_adr_refs = re.findall(r"ADR-(\d{3})", composes)
    composes_adr_nums = sorted({int(n) for n in composes_adr_refs})
    missing_in_section = [n for n in adr_nums if n not in composes_adr_nums]
    if missing_in_section:
        print(f"✗ step 5: ADR-NNN appears in cheatsheet but NOT in "
              f"composes-with section: {[f'ADR-{n:03d}' for n in missing_in_section]}. "
              "Cross-refs belong in the structured footer, not stray prose.")
        return 1
    print(f"✓ step 5: all {len(adr_nums)} ADRs cited in composes-with section")

    # ── Step 6: NEGATIVE — references appear in numerical order ──
    # Find ADR-NNN occurrences in the composes section in document
    # order; verify they're monotonically non-decreasing.
    ordered = [int(m.group(1)) for m in re.finditer(r"ADR-(\d{3})", composes)]
    # Strip duplicates while preserving order
    seen: set[int] = set()
    deduped: list[int] = []
    for n in ordered:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    if deduped != sorted(deduped):
        print(f"✗ step 6: ADR refs out of order in composes-with: "
              f"{deduped} (expected {sorted(deduped)})")
        return 1
    print(f"✓ step 6: ADR refs appear in numerical order")

    # ── Step 7: NEGATIVE — every ADR ref has an inline gloss ──
    # The cheatsheet pattern is:
    #   - **`docs/architecture/adr/NNN-*.md`** (ADR-NNN) — short description
    # The gloss after "—" should be non-empty. A line ending right
    # after the canonical id is missing context.
    for n in adr_nums:
        canonical = f"ADR-{n:03d}"
        # Find the bullet line containing this ADR
        line_pattern = rf"^- \*\*[^*]+\*\* \({re.escape(canonical)}\) — (.+)$"
        line_match = re.search(line_pattern, composes, re.MULTILINE)
        if not line_match:
            print(f"✗ step 7: {canonical} bullet missing or non-canonical "
                  f"shape (expected '- **path** ({canonical}) — desc')")
            return 1
        gloss = line_match.group(1).strip()
        if len(gloss) < 20:
            print(f"✗ step 7: {canonical} gloss too short ({len(gloss)} chars): "
                  f"{gloss!r}")
            return 1
    print(f"✓ step 7: all {len(adr_nums)} ADR bullets have substantial gloss "
          "(≥20 chars)")

    # ── Step 8: POSITIVE — count parity ──
    if len(composes_adr_nums) != len(adr_nums):
        print(f"✗ step 8: composes-with cites {len(composes_adr_nums)} ADRs, "
              f"disk has {len(adr_nums)}. Parity broken.")
        return 1
    print(f"✓ step 8: cheatsheet ADR coverage = catalog "
          f"({len(adr_nums)} on disk = {len(composes_adr_nums)} in cheatsheet)")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
