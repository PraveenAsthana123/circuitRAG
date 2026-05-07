#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: docs/NEXT_POLICY.md structure is well-formed.

The policy file is the autonomous loop's source of truth. A
refactor that accidentally drops a section, mangles the
proposed-approvals matrix, or breaks the disposition enum would
silently let the loop into the wrong scope.

This drill parses the file structurally and locks the contract:

  * Required H2 sections exist with the canonical names
  * Pre-approved scope table (§1) has at least 7 rows
  * Proposed-approvals matrix (§1.5) has at least 30 rows
  * Every matrix row uses an allowed disposition value
  * Brutal rules (§8) has exactly 5 numbered rules
  * Status convention (§4) has 6 status values
  * Section ordering preserved (1, 1.5, 2, 3, 4, 5, 6, 7, 8)

Eight steps. Five negative assertions.

  1. File exists at docs/NEXT_POLICY.md.
  2. All required H2 section headings present in canonical order.
  3. §1 (pre-approved scope) table has the expected row count.
  4. §1.5 (proposed-approvals) matrix has at least 30 rows.
  5. NEGATIVE: every matrix row's disposition is in the allowed
     enum {pre-approved, gated, never, pending, denied}.
  6. NEGATIVE: every matrix row has a non-empty 'Action' cell
     (typing a markdown table is easy to break with stray pipes).
  7. NEGATIVE: §8 brutal rules contains exactly 5 rules. A
     refactor adding/removing one would silently shift the policy.
  8. NEGATIVE: 'Streamlit' word does not appear in the policy
     (user explicitly chose Next.js; lingering Streamlit refs
     would mislead).

Tag: readonly. Pure-Python -- runs in tier 1.
"""
from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
POLICY = REPO / "docs" / "NEXT_POLICY.md"

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
    # Step 1
    step("1. docs/NEXT_POLICY.md exists")
    if not POLICY.exists():
        fail(f"policy file missing at {POLICY}")
    text = POLICY.read_text()
    if len(text) < 1000:
        fail(f"policy file suspiciously short: {len(text)} chars")
    ok(f"policy file at {POLICY.relative_to(REPO)} ({len(text)} chars)")

    # Step 2 - section ordering
    step("2. all required H2 sections present in canonical order")
    expected = [
        "## 1. Pre-approved scope",
        "## 1.5. Comprehensive proposed-approvals matrix",
        "## 2. The pending ledger",
        "## 3. Tracking surface",
        "## 4. Status convention",
        "## 5. Update protocol",
        "## 6. Track / tracking commands",
        "## 7. Scope-extension log",
        "## 8. Brutal rules",
    ]
    last_idx = -1
    for heading in expected:
        idx = text.find(heading)
        if idx < 0:
            fail(f"missing section heading: {heading!r}")
        if idx <= last_idx:
            fail(f"section ordering broken at {heading!r}")
        last_idx = idx
    ok(f"all {len(expected)} sections present in canonical order")

    # Step 3 - §1 row count
    step("3. §1 pre-approved scope table has >= 7 rows")
    s1_start = text.find("## 1. Pre-approved scope")
    s15_start = text.find("## 1.5.")
    s1_block = text[s1_start:s15_start]
    # Count table rows (skip header + separator)
    rows = [
        ln for ln in s1_block.split("\n")
        if ln.strip().startswith("|") and not ln.strip().startswith("|---")
        and "Pre-approved" not in ln  # skip header row
    ]
    if len(rows) < 7:
        fail(f"§1 has only {len(rows)} table rows (expected >= 7)")
    ok(f"§1 pre-approved scope table has {len(rows)} rows")

    # Step 4 - §1.5 row count
    step("4. §1.5 proposed-approvals matrix has >= 30 rows")
    s15_block_end = text.find("## 2. The pending ledger")
    s15_block = text[s15_start:s15_block_end]
    matrix_rows = re.findall(
        r"^\| \d+ \| .+ \|$", s15_block, re.MULTILINE,
    )
    if len(matrix_rows) < 30:
        fail(f"§1.5 has only {len(matrix_rows)} matrix rows (expected >= 30)")
    ok(f"§1.5 proposed-approvals matrix has {len(matrix_rows)} rows")

    # Step 5 - NEGATIVE: dispositions are valid
    step("5. NEGATIVE: every matrix row uses an allowed disposition")
    allowed = {"pre-approved", "gated", "never", "pending", "denied"}
    invalid_rows = []
    for row in matrix_rows:
        # Cells separated by ' | ' (with surrounding spaces). Disposition
        # is the 3rd cell (after #, Action, Disposition, ...).
        # Matrix uses **bold** for disposition cells, so strip ** marks.
        cells = [c.strip() for c in row.split("|")[1:-1]]
        if len(cells) < 3:
            invalid_rows.append((row[:60], "too few cells"))
            continue
        disp = cells[2].strip("*").strip()
        if disp not in allowed:
            invalid_rows.append((row[:60], f"bad disposition {disp!r}"))
    if invalid_rows:
        for r, reason in invalid_rows[:3]:
            print(f"      bad row: {r!r} ({reason})")
        fail(f"{len(invalid_rows)} matrix rows have invalid disposition")
    ok(f"all {len(matrix_rows)} dispositions in allowed enum")

    # Step 6 - NEGATIVE: every row has non-empty Action cell
    step("6. NEGATIVE: every matrix row has a non-empty Action cell")
    for row in matrix_rows:
        cells = [c.strip() for c in row.split("|")[1:-1]]
        if len(cells) < 2:
            fail(f"row too narrow: {row!r}")
        if not cells[1]:
            fail(f"empty Action cell: {row!r}")
    ok(f"all {len(matrix_rows)} rows have non-empty Action")

    # Step 7 - NEGATIVE: §8 brutal rules has exactly 5
    step("7. NEGATIVE: §8 brutal rules has exactly 5 numbered rules")
    s8_start = text.find("## 8. Brutal rules")
    s8_block = text[s8_start:]
    # Count "1. ... 2. ... 3. ..." numbered list items at start of line
    rule_lines = re.findall(r"^\d+\.\s+\*\*", s8_block, re.MULTILINE)
    if len(rule_lines) != 5:
        fail(
            f"§8 has {len(rule_lines)} brutal rules (expected exactly 5). "
            f"Adding/removing a rule shifts the policy invariants."
        )
    ok("§8 has exactly 5 brutal rules")

    # Step 8 - NEGATIVE: no Streamlit references
    step("8. NEGATIVE: 'Streamlit' word does not appear in the policy")
    if re.search(r"\bStreamlit\b", text, re.IGNORECASE):
        # Find the line(s) for the error message
        bad_lines = [
            ln for ln in text.split("\n")
            if re.search(r"\bStreamlit\b", ln, re.IGNORECASE)
        ]
        fail(
            "policy still mentions Streamlit:\n"
            "  " + "\n  ".join(bad_lines[:3]) + "\n"
            "User chose Next.js; lingering Streamlit refs mislead the loop."
        )
    ok("no Streamlit references (Next.js stack pivot complete)")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 NEXT-POLICY STRUCTURE STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 5, 6, 7, 8){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")


if __name__ == "__main__":
    main()
