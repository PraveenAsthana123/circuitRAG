#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: drill_adr020_audit_cadence's parallel-tool detection regex
matches all observed G-N.M-suffix shapes.

Phase 7II strengthened the detection regex from `G-\\d+\\s+-` (only
"G-N -" with whitespace before dash) to `G-\\d+[\\s\\.\\-:]` (any
of whitespace, dot, dash, colon). The change caught 2 previously-
silent commits (G-5.1 and G-5.2-followon).

Without a drill, the regex is forward-looking-check-prone per
ADR-017: a future "simplification" could narrow it back and the
silent-miss returns. This drill locks the structural contract by
testing the regex against a fixture set of subject shapes
observed across G-1 through G-6.

Eight steps. Six negative assertions.

  1. POSITIVE: drill_adr020_audit_cadence source loads + the
     `_discover_parallel_tool_commits` function is present.
  2. NEGATIVE: regex matches the original "feat(area): G-N -"
     shape (G-1 through G-3 used this).
  3. NEGATIVE: regex matches "feat(area): G-N.M - desc" shape
     (G-5.1 introduced this — Phase 7II added support).
  4. NEGATIVE: regex matches "feat(area): G-N.M-followon - desc"
     shape (G-5.2-followon introduced this).
  5. NEGATIVE: regex matches "feat(area): G-N: desc" shape
     (alternative colon-separator form, no dash).
  6. NEGATIVE: regex matches bare "G-N: ..." subject (no
     `feat(area):` prefix — original G-N-only path).
  7. NEGATIVE: regex does NOT match unrelated subjects like
     "fix(...): G-suffix without digit" or "G:..." (catches
     over-matching regression).
  8. POSITIVE: emit per-fixture verdict for operator visibility.

Run: python3 mcp/tests/drill_cadence_detection_regex.py
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CADENCE_DRILL = REPO / "mcp" / "tests" / "drill_adr020_audit_cadence.py"

# Subject-shape fixtures observed in this session. (subject, should_match)
FIXTURES_MUST_MATCH = [
    "feat(agentic): G-1 - first batch",
    "feat(frontend): G-2 - sidecar pages",
    "feat(scripts): G-3 - help-contract paydown",
    "feat(agentic): G-4 - agentic control plane (8 audits)",
    "feat(sidecar): G-5 - sidecar event rating surface",
    "feat(sidecar): G-5.1 + Phase 7CC - rating metadata columns",
    "feat(sidecar): G-5.2-followon - rating route + Vitest extensions",
    "feat(monitoring): G-6 + Phase 7PP - operator monitoring dashboard",
    "G-7: hypothetical bare subject",
    "G-8 - another hypothetical",
]

FIXTURES_MUST_NOT_MATCH = [
    "fix(drills): Phase 7QQ - register G-6 in cadence ratchet",
    "docs(retro): Phase 7EE - 2026-04-30 session retrospective",
    "chore(gitignore): Phase 6Z - block worktree noise",
    "G:not a real prefix",  # missing digit
    "feat(monitoring): some other change",
    "fix-up: unrelated",
]

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


def _load_cadence_module():
    """Import drill_adr020_audit_cadence as a module so we can
    extract its detection regex."""
    spec = importlib.util.spec_from_file_location(
        "_cadence_drill", CADENCE_DRILL,
    )
    if spec is None or spec.loader is None:
        fail(f"could not load {CADENCE_DRILL}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _extract_path_b_patterns(source: str) -> list[str]:
    """Extract the `re.match(r"...")` regex strings from the
    detection function (Path B). Two patterns expected:
    one with `feat(area):` prefix, one bare `^G-`."""
    patterns: list[str] = []
    for m in re.finditer(r're\.match\(r"([^"]+)"', source):
        patterns.append(m.group(1))
    return patterns


def _matches_any(subject: str, patterns: list[str]) -> bool:
    return any(re.match(p, subject) for p in patterns)


def main() -> int:
    step("1. POSITIVE: cadence drill source + _discover function present")
    if not CADENCE_DRILL.is_file():
        fail(f"cadence drill missing at {CADENCE_DRILL}")
    source = CADENCE_DRILL.read_text()
    if "_discover_parallel_tool_commits" not in source:
        fail("_discover_parallel_tool_commits function missing")
    patterns = _extract_path_b_patterns(source)
    if len(patterns) < 2:
        fail(
            f"expected ≥2 Path B regex patterns in detection logic; "
            f"found {len(patterns)}: {patterns}"
        )
    ok(f"loaded cadence drill; extracted {len(patterns)} Path B regex(es)")

    step("2. NEGATIVE: regex matches 'feat(area): G-N - desc' (G-1..G-4 shape)")
    target = "feat(agentic): G-4 - agentic control plane (8 audits)"
    if not _matches_any(target, patterns):
        fail(f"regex does NOT match {target!r} — G-1..G-4 shape regression")
    ok(f"matches: {target[:60]}")

    step("3. NEGATIVE: regex matches 'feat(area): G-N.M' (G-5.1 shape)")
    target = "feat(sidecar): G-5.1 + Phase 7CC - rating metadata columns"
    if not _matches_any(target, patterns):
        fail(
            f"regex does NOT match {target!r} — G-5.1 shape regression. "
            "Phase 7II's `[\\s\\.\\-:]` separator must include the dot."
        )
    ok(f"matches: {target[:60]}")

    step("4. NEGATIVE: regex matches 'feat(area): G-N.M-followon' shape")
    target = "feat(sidecar): G-5.2-followon - rating route + Vitest extensions"
    if not _matches_any(target, patterns):
        fail(
            f"regex does NOT match {target!r} — G-N.M-followon "
            "regression. Phase 7II's `[\\s\\.\\-:]` separator must "
            "include the dash."
        )
    ok(f"matches: {target[:60]}")

    step("5. NEGATIVE: regex matches 'G-N: bare-subject' shape")
    target = "G-7: hypothetical bare subject"
    if not _matches_any(target, patterns):
        fail(
            f"regex does NOT match {target!r} — bare G-N: subject "
            "regression. Path B (bare prefix) variant must support."
        )
    ok(f"matches: {target[:60]}")

    step("6. NEGATIVE: every must-match fixture is detected")
    misses = []
    for subject in FIXTURES_MUST_MATCH:
        if not _matches_any(subject, patterns):
            misses.append(subject[:60])
    if misses:
        fail(
            f"{len(misses)} must-match fixture(s) NOT detected: {misses[:3]}"
        )
    ok(f"all {len(FIXTURES_MUST_MATCH)} must-match fixtures detected")

    step("7. NEGATIVE: must-NOT-match fixtures are NOT over-matched")
    over_matched = []
    for subject in FIXTURES_MUST_NOT_MATCH:
        if _matches_any(subject, patterns):
            over_matched.append(subject[:60])
    if over_matched:
        fail(
            f"{len(over_matched)} unrelated subject(s) over-matched "
            f"by detection regex: {over_matched[:3]}. Detection now "
            "fires on commits that aren't actually parallel-tool batches."
        )
    ok(f"no over-match across {len(FIXTURES_MUST_NOT_MATCH)} unrelated fixtures")

    step("8. POSITIVE: per-fixture verdict summary")
    for subject in FIXTURES_MUST_MATCH:
        verdict = "MATCH" if _matches_any(subject, patterns) else "miss"
        ok(f"  [{verdict:5}] {subject[:65]}")
    ok("  --- must-NOT-match ---")
    for subject in FIXTURES_MUST_NOT_MATCH:
        verdict = "match" if _matches_any(subject, patterns) else "SKIP"
        ok(f"  [{verdict:5}] {subject[:65]}")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 CADENCE-DETECTION-REGEX STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (6 negative assertions: 2, 3, 4, 5, 6, 7){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
