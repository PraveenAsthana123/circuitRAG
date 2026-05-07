#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: every ADR is categorisable as DOMAIN or LOOP-DISCIPLINE.

drill_cheatsheet_adr_coverage filters ADR files by FILENAME keyword
to identify "loop-discipline" ADRs that should be referenced in
the cheatsheet. ADRs that don't match any keyword are silently
treated as "not loop-discipline." This produces a hidden gap:
a new ADR-021 with a fresh keyword (e.g. "policy-as-code") is
silently excluded from the cheatsheet check; the cheatsheet
drifts without firing the drill.

Phase 7F manually extended LOOP_KEYWORDS to recognize ADR-020.
That manual step is the regression we lock against here: a new
ADR that doesn't match LOOP_KEYWORDS AND isn't an explicit domain
ADR (number in DOMAIN_ADR_NUMBERS) MUST cause this drill to fail
with a clear "categorize this ADR" message.

The drill imports LOOP_KEYWORDS from drill_cheatsheet_adr_coverage
so the two drills share one canonical reference. Domain ADRs are
explicit (DOMAIN_ADR_NUMBERS = ADRs 001-013). Future ADRs default
to loop-discipline; if the operator wants a new domain ADR, they
extend DOMAIN_ADR_NUMBERS in the same commit (the ratchet pattern
per ADR-015).

Eight steps. Five negative assertions.

  1. POSITIVE: discover NNN-*.md ADR files (>= 15 floor — drill
     cannot trivially pass by deleting the ADR catalog).
  2. NEGATIVE: every ADR file matches the canonical NNN-slug.md
     pattern. Files that don't match break drill_cheatsheet_adr_
     coverage's slug-keyword check too.
  3. NEGATIVE: every ADR is categorisable — number is in
     DOMAIN_ADR_NUMBERS (explicit domain) OR slug matches at
     least one LOOP_KEYWORDS entry. On uncategorised ADRs the
     failure message emits copy-pasteable LOOP_KEYWORDS
     candidates (2-token, 3-token, ..., full-slug prefixes) so
     the operator can pick a slice and add it in one edit.
     The same step also self-tests _suggest_keywords on a
     synthetic slug to keep the suggestion path covered even
     when no ADR is uncategorised (per ADR-017 — drills must
     exercise their failure paths, not just happy paths).
  4. NEGATIVE: no ADR is in BOTH categories (domain number AND
     loop-discipline keyword). Defense-in-depth — keeps the
     classification crisp.
  5. NEGATIVE: ADR numbering is dense (no gaps within the
     known range; missing files indicate accidental deletion).
  6. NEGATIVE: LOOP_KEYWORDS has no stale entries — every
     keyword in the set matches at least one ADR slug. A keyword
     that matches zero ADRs is dead code; either an ADR was
     renamed/deleted or the keyword was never used.
  7. POSITIVE: emit per-category ADR breakdown.
  8. POSITIVE: emit LOOP_KEYWORDS coverage map (which keyword
     matched which ADR).

Run: python3 mcp/tests/drill_adr_categorization.py
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "architecture" / "adr"
COVERAGE_DRILL = REPO / "mcp" / "tests" / "drill_cheatsheet_adr_coverage.py"

# Domain ADRs at landing time. Frozen explicitly: future ADRs
# default to loop-discipline unless operator extends this set in
# the same commit. Per ADR-015 ratchet pattern: floor stays at
# the explicit list; growth is a deliberate decision.
DOMAIN_ADR_NUMBERS = frozenset({
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,  # 001-013
    23,                                            # ADR-023 empirical RAG-config loop (2026-05-05)
    24,                                            # ADR-024 Stage-3 default-flip (2026-05-05)
    25,                                            # ADR-025 feature-flag-gated dual-write (§47.7) (2026-05-06)
    26,                                            # ADR-026 MLflow deliberate-not-now (Langfuse covers LLM obs) (2026-05-06)
    27,                                            # ADR-027 agent framework: LangGraph + custom council; CrewAI/Agno/PraisonAI rejected (2026-05-07)
    28,                                            # ADR-028 CSV-to-DB ingest write-surface contract (2026-05-07)
})

MIN_ADRS = 15

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}{msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}-- {title} --{NC}")


def _suggest_keywords(slug: str) -> list[str]:
    """Suggest candidate LOOP_KEYWORDS extensions for a given slug.

    Returned candidates are token prefixes of the slug, ordered
    shortest-first (2-token, 3-token, 4-token, ...). Existing
    LOOP_KEYWORDS entries skew toward 2-token (e.g. "parallel-tool",
    "drill-audit") with occasional 3-token ("sweep-before-commit")
    and rare 4-token ("three-way-work-allocation"). Operator picks
    the right slice for the new ADR.

    Always includes the full slug as the last candidate (catch-all).
    """
    tokens = slug.split("-")
    out: list[str] = []
    seen: set[str] = set()
    for n in range(2, max(len(tokens) + 1, 3)):
        if n > len(tokens):
            continue
        candidate = "-".join(tokens[:n])
        if candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    if slug not in seen:
        out.append(slug)
    return out


def _import_loop_keywords() -> tuple[str, ...]:
    """Import LOOP_KEYWORDS from drill_cheatsheet_adr_coverage so
    both drills share one canonical reference. Falls back to a
    direct file load (no need to add the drills directory to
    sys.path)."""
    spec = importlib.util.spec_from_file_location(
        "_coverage_drill", COVERAGE_DRILL,
    )
    if spec is None or spec.loader is None:
        fail(f"could not import LOOP_KEYWORDS from {COVERAGE_DRILL}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    keywords = getattr(mod, "LOOP_KEYWORDS", None)
    if keywords is None or not isinstance(keywords, tuple):
        fail(
            "drill_cheatsheet_adr_coverage.LOOP_KEYWORDS missing or "
            "wrong type — expected module-level tuple"
        )
    return keywords


def main() -> int:
    step("1. POSITIVE: discover ADR files (>= MIN_ADRS floor)")
    adr_files: list[tuple[int, str, Path]] = []
    for path in sorted(ADR_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        m = re.match(r"^(\d{3})-(.+)\.md$", path.name)
        if not m:
            # Non-canonical names handled by step 2.
            continue
        adr_files.append((int(m.group(1)), m.group(2), path))
    if len(adr_files) < MIN_ADRS:
        fail(
            f"only {len(adr_files)} ADRs discovered; floor is {MIN_ADRS}. "
            "Drill cannot trivially pass by deleting ADR files."
        )
    ok(f"discovered {len(adr_files)} ADR files in {ADR_DIR.relative_to(REPO)}/")

    step("2. NEGATIVE: every ADR file matches NNN-slug.md pattern")
    bad_names: list[str] = []
    for path in sorted(ADR_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        if not re.match(r"^\d{3}-[a-z0-9-]+\.md$", path.name):
            bad_names.append(path.name)
    if bad_names:
        fail(
            f"{len(bad_names)} ADR file(s) with non-canonical names: "
            f"{bad_names[:3]}. Use NNN-slug-with-hyphens.md format."
        )
    ok(f"all {len(adr_files)} ADRs match NNN-slug.md pattern")

    LOOP_KEYWORDS = _import_loop_keywords()

    step("3. NEGATIVE: every ADR is categorisable (DOMAIN or LOOP-DISCIPLINE)")
    uncategorised: list[tuple[int, str]] = []
    for num, slug, path in adr_files:
        is_domain = num in DOMAIN_ADR_NUMBERS
        is_loop = any(kw in slug for kw in LOOP_KEYWORDS)
        if not is_domain and not is_loop:
            uncategorised.append((num, slug))
    if uncategorised:
        # Emit copy-pasteable extension hints for each uncategorised
        # ADR. The operator picks one path (LOOP_KEYWORDS extension
        # OR DOMAIN_ADR_NUMBERS extension); the drill makes both
        # mechanical.
        msg_lines = [f"{len(uncategorised)} ADR(s) uncategorised:"]
        for num, slug in uncategorised:
            suggestions = _suggest_keywords(slug)
            msg_lines.append(f"  ADR-{num:03d} '{slug}'")
            msg_lines.append(
                "    To classify as LOOP-DISCIPLINE, add ONE of these "
                "to LOOP_KEYWORDS in drill_cheatsheet_adr_coverage.py:"
            )
            for cand in suggestions:
                msg_lines.append(f"      \"{cand}\",")
            msg_lines.append(
                f"    OR to classify as DOMAIN, add {num} to "
                f"DOMAIN_ADR_NUMBERS in drill_adr_categorization.py."
            )
        fail("\n  ".join(msg_lines))
    # Sanity-check the suggestion helper on a synthetic slug so the
    # code path is exercised even on a clean run (otherwise the
    # suggestion logic is forward-looking-check-prone per ADR-017).
    test_slug = "policy-as-code-for-llm-tools"
    test_suggestions = _suggest_keywords(test_slug)
    if not test_suggestions or test_slug not in test_suggestions:
        fail(
            f"_suggest_keywords self-test failed: "
            f"{test_slug} -> {test_suggestions}"
        )
    if "policy-as" not in test_suggestions:
        fail(
            f"_suggest_keywords self-test missing 2-token prefix: "
            f"{test_slug} -> {test_suggestions}"
        )
    ok(
        f"all {len(adr_files)} ADRs categorised; "
        f"_suggest_keywords self-test ok ({len(test_suggestions)} candidates)"
    )

    step("4. NEGATIVE: no ADR is in both categories (defense-in-depth)")
    both: list[tuple[int, str]] = []
    for num, slug, path in adr_files:
        is_domain = num in DOMAIN_ADR_NUMBERS
        is_loop = any(kw in slug for kw in LOOP_KEYWORDS)
        if is_domain and is_loop:
            both.append((num, slug))
    if both:
        fail(
            f"{len(both)} ADR(s) in BOTH categories: {both}. "
            "Operator decision required — pick one."
        )
    ok("no ADR is double-classified")

    step("5. NEGATIVE: ADR numbering is dense (no missing files within range)")
    numbers = sorted(num for num, _, _ in adr_files)
    expected = list(range(numbers[0], numbers[-1] + 1))
    missing = [n for n in expected if n not in numbers]
    if missing:
        fail(
            f"{len(missing)} ADR number(s) missing in [{numbers[0]:03d}, "
            f"{numbers[-1]:03d}]: {[f'{n:03d}' for n in missing[:5]]}"
        )
    ok(
        f"ADR numbering dense: {numbers[0]:03d}-{numbers[-1]:03d} "
        f"({len(numbers)} files, no gaps)"
    )

    step("6. NEGATIVE: every LOOP_KEYWORDS entry matches at least one ADR")
    coverage: dict[str, list[int]] = {kw: [] for kw in LOOP_KEYWORDS}
    for num, slug, path in adr_files:
        for kw in LOOP_KEYWORDS:
            if kw in slug:
                coverage[kw].append(num)
    dead_keywords = [kw for kw, nums in coverage.items() if not nums]
    if dead_keywords:
        fail(
            f"{len(dead_keywords)} LOOP_KEYWORDS entries match no ADR: "
            f"{dead_keywords}. Either an ADR was renamed/deleted, or "
            "the keyword was added speculatively. Remove or rename."
        )
    ok(
        f"all {len(LOOP_KEYWORDS)} LOOP_KEYWORDS entries cover at least "
        "one ADR"
    )

    step("7. POSITIVE: per-category ADR breakdown")
    domain_count = sum(1 for n, _, _ in adr_files if n in DOMAIN_ADR_NUMBERS)
    loop_count = len(adr_files) - domain_count
    ok(
        f"category counts: DOMAIN={domain_count} (numbers in "
        f"{min(DOMAIN_ADR_NUMBERS):03d}-{max(DOMAIN_ADR_NUMBERS):03d}), "
        f"LOOP-DISCIPLINE={loop_count}"
    )

    step("8. POSITIVE: LOOP_KEYWORDS coverage map")
    for kw in LOOP_KEYWORDS:
        covered = coverage.get(kw, [])
        if covered:
            adrs_repr = ", ".join(f"ADR-{n:03d}" for n in sorted(covered))
            ok(f"  {kw:<32s} -> {adrs_repr}")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 ADR-CATEGORIZATION STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 2, 3, 4, 5, 6){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
