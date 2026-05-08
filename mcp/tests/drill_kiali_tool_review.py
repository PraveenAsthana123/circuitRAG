#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: §52 brutal tool review for Kiali integration must exist and
be indexed.

§52 mandates a 40-row review for every tool added to the request
hot path or holding production state. This drill ensures the Kiali
integration (commits d3ca211 + c8ee4fe + eab8204 + e8a6142) has
its review file AND is referenced from the index.

5 steps, 3 negative.

  1. POSITIVE: docs/architecture/tool-reviews/kiali-integration.md
              exists with the 40-row template
  2. POSITIVE: review references all 4 commits that introduced the
              Kiali integration (forensic continuity)
  3. POSITIVE: README index lists kiali-integration.md
  4. NEGATIVE: review does NOT claim 0 P1 (the anonymous-auth row
              is a real P1 — claiming 0 P1 would hide it from the
              aggregate count)
  5. NEGATIVE: review does NOT skip stakeholder-lens table (every
              tool review must address all 6 stakeholders per §52.3)

Per CLAUDE.md §43 (drill discipline; ≥3 negatives), §51 (forensic
substrate — review file is the architectural artifact), §52 (the
review is mandatory; without it, "shipped" is hollow), §57.7
(honesty — the P1 must be present; aggregate counts must be
truthful).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REVIEW = REPO / "docs" / "architecture" / "tool-reviews" / "kiali-integration.md"
INDEX = REPO / "docs" / "architecture" / "tool-reviews" / "README.md"

REQUIRED_COMMITS = ["d3ca211", "c8ee4fe", "eab8204", "e8a6142"]
REQUIRED_STAKEHOLDERS = [
    "Developer",
    "Architect",
    "Eng Manager",
    "Business User (basic)",
    "Business User (advanced)",
    "Business User (expert)",
]
REQUIRED_DIM_COUNT = 40

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def step(t: str) -> None:
    print(f"\n{BOLD}── {t} ──{NC}")


def ok(m: str) -> None:
    print(f"  {GREEN}✓ {m}{NC}")


def fail(m: str) -> None:
    print(f"  {RED}✗ {m}{NC}")
    raise SystemExit(1)


def main() -> int:
    # ── 1. review file exists with 40 rows ─────────────────────────────
    step("1. POSITIVE: kiali-integration.md exists with 40-row template")
    if not REVIEW.exists():
        fail(f"missing: {REVIEW.relative_to(REPO)}")
    text = REVIEW.read_text(encoding="utf-8")
    # Count table rows of the form "| <number> | ..." across the 6 dimension tables
    rows = re.findall(r"^\|\s+(\d+)\s+\|", text, re.MULTILINE)
    rows = [int(r) for r in rows]
    if not all(i in rows for i in range(1, REQUIRED_DIM_COUNT + 1)):
        missing = [i for i in range(1, REQUIRED_DIM_COUNT + 1) if i not in rows]
        fail(
            f"review missing dimension rows: {missing} (need 1-{REQUIRED_DIM_COUNT} per §52 template)"
        )
    ok(f"review present + all {REQUIRED_DIM_COUNT} dimension rows declared")

    # ── 2. references all 4 commits ────────────────────────────────────
    step("2. POSITIVE: review references all 4 Kiali-integration commits")
    missing_commits = [c for c in REQUIRED_COMMITS if c not in text]
    if missing_commits:
        fail(
            f"review missing commit references {missing_commits} — without these, "
            "the review can't be tied back to the code that shipped"
        )
    ok(f"all {len(REQUIRED_COMMITS)} commits referenced ({', '.join(REQUIRED_COMMITS)})")

    # ── 3. README index lists this review ─────────────────────────────
    step("3. POSITIVE: README index lists kiali-integration.md")
    if not INDEX.exists():
        fail(f"missing: {INDEX.relative_to(REPO)}")
    idx_text = INDEX.read_text(encoding="utf-8")
    if "kiali-integration.md" not in idx_text:
        fail(
            "README index does NOT reference kiali-integration.md — auditors "
            "discover reviews via the index; an unindexed review is invisible"
        )
    if "Kiali" not in idx_text:
        fail("README index has no human-readable 'Kiali' label for the row")
    ok("README index references kiali-integration.md with Kiali label")

    # ── 4. NEGATIVE: review reports the real P1 honestly ──────────────
    step("4. NEGATIVE: review does NOT claim 0 P1 (anonymous auth IS a P1)")
    triage = re.search(r"P1.*?\|\s*(\d+)\s*\|", text)
    if not triage:
        fail("review missing P1 row in Triage summary table")
    p1_count = int(triage.group(1))
    if p1_count == 0:
        fail(
            "review claims P1 = 0 — but Kiali ships with auth.strategy=anonymous "
            "which is a real P1 for shared environments. Claiming 0 hides it "
            "from the aggregate count and lets it ship to prod silently."
        )
    if "anonymous" not in text.lower():
        fail(
            "review does not mention 'anonymous' — the auth.strategy=anonymous "
            "P1 finding requires explicit naming so reviewers can grep for it"
        )
    ok(f"review honestly reports P1 = {p1_count} (anonymous auth named)")

    # ── 5. NEGATIVE: stakeholder-lens table covers all 6 stakeholders ─
    step("5. NEGATIVE: stakeholder-lens table is NOT skipped (all 6 present)")
    missing_stakeholders = [s for s in REQUIRED_STAKEHOLDERS if s not in text]
    if missing_stakeholders:
        fail(
            f"review missing stakeholder-lens rows: {missing_stakeholders}. "
            "Every tool review must address all 6 stakeholders (§52.3)."
        )
    ok(f"all {len(REQUIRED_STAKEHOLDERS)} stakeholder lenses addressed")

    print(f"\n{BOLD}{GREEN}ALL 5 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
