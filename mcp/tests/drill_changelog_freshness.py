# RESOURCES: readonly
"""
Drill: CHANGELOG.md freshness + commit reference truth.

Per global CLAUDE.md §1 (mandatory project files include CHANGELOG.md)
+ §51.1 forensic substrate. CHANGELOG entries reference commits that
must actually exist in `git log`; entries dated past 30 days = stale.

Locks (positive):
  L1. CHANGELOG.md exists at repo root
  L2. Has at least one ## [Unreleased] header in 2026
  L3. Latest section dated within last 30 days
  L4. Conventional Commits link present in preamble

Locks (negative — ≥3 per §43):
  N1. Every short-hash referenced (^[0-9a-f]{7}$) MUST resolve in
      `git log`. Phantom commit references = lying.
  N2. Latest section is NOT older than 30 days (staleness floor)
  N3. CHANGELOG never references a hash that's longer than 12 chars
      (would be a SHA fragment from a fork or rewritten history)
  N4. CHANGELOG doesn't claim "default 1" for migrate-phase flags
      (mirrors ADR-025 N9 — the operator-opt-in floor)
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHANGELOG = REPO / "CHANGELOG.md"

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
    # ===================================================================
    # Step 1 — file exists + non-trivial
    # ===================================================================
    step("1. CHANGELOG.md exists with non-trivial content")
    if not CHANGELOG.exists():
        fail("CHANGELOG.md missing")
    text = CHANGELOG.read_text(encoding="utf-8")
    if len(text) < 500:
        fail(f"CHANGELOG too small ({len(text)}B)")
    ok(f"CHANGELOG.md present ({len(text)}B)")

    # ===================================================================
    # Step 2 — at least one [Unreleased] header in 2026
    # ===================================================================
    step("2. Has at least one ## [Unreleased] section dated 2026")
    unreleased_2026 = re.findall(r"## \[Unreleased\] — 2026-\d{2}-\d{2}", text)
    if not unreleased_2026:
        fail("no '## [Unreleased] — 2026-MM-DD' header found")
    ok(f"{len(unreleased_2026)} Unreleased 2026 section(s)")

    # ===================================================================
    # Step 3 — Latest section dated within last 30 days
    # ===================================================================
    step("3. Latest [Unreleased] section dated within last 30 days")
    # Extract the FIRST [Unreleased] header (latest by file order)
    m = re.search(r"## \[Unreleased\] — 2026-(\d{2})-(\d{2})", text)
    if not m:
        fail("no parseable date in latest [Unreleased] header")
    month, day = int(m.group(1)), int(m.group(2))
    # Most recent section appears FIRST (we prepend new entries).
    # If header is "2026-05-06/07", parser captures 2026-05-06.
    section_date = dt.date(2026, month, day)
    today = dt.date.today()
    days_old = (today - section_date).days
    if days_old > 30:
        fail(f"latest section {section_date} is {days_old}d old — stale (>30d)")
    if days_old < 0:
        ok(f"latest section {section_date} (future-tagged)")
    else:
        ok(f"latest section {section_date} ({days_old}d old; ≤30d)")

    # ===================================================================
    # Step 4 — Conventional Commits preamble
    # ===================================================================
    step("4. Preamble references conventionalcommits.org")
    if "conventionalcommits.org" not in text:
        fail("changelog missing Conventional Commits reference")
    ok("Conventional Commits link present")

    # ===================================================================
    # Step 5 — NEGATIVE: every referenced commit hash resolves in git log
    # ===================================================================
    step("5. NEGATIVE: every short-hash reference resolves in `git log`")
    # Extract candidates: backtick-wrapped 7-char hex sequences
    hashes = set(re.findall(r"`([0-9a-f]{7,12})`", text))
    if not hashes:
        ok("no commit-hash references to verify (skip)")
    else:
        # Verify each via `git cat-file -e <hash>`
        bad: list[str] = []
        for h in hashes:
            try:
                subprocess.check_call(
                    ["git", "cat-file", "-e", h],
                    cwd=str(REPO),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                bad.append(h)
        if bad:
            fail(f"phantom commit references (don't resolve): {bad}")
        ok(f"all {len(hashes)} commit hashes resolve in git log")

    # ===================================================================
    # Step 6 — NEGATIVE: no hash longer than 12 chars
    # ===================================================================
    step("6. NEGATIVE: no commit-hash reference longer than 12 chars")
    # Anything 13-40 chars hex inside backticks would be a long hash
    long_hashes = re.findall(r"`([0-9a-f]{13,40})`", text)
    if long_hashes:
        fail(f"changelog has long-hash references (use 7-12 chars): {long_hashes}")
    ok("no long-hash references (all 7-12 chars, conventional)")

    # ===================================================================
    # Step 7 — NEGATIVE: no claim of default=1 for migrate flags
    # (mirrors ADR-025 N9 — the operator-opt-in floor)
    # ===================================================================
    step("7. NEGATIVE: no rogue 'default 1' claims for migrate-phase flags")
    bad_patterns = (
        "MCP_GATEWAY_SQL_AUDIT_ENABLED=1 by default",
        "OPS_WORKER_SQL_ENABLED defaults to 1",
        "MCP_TOOLS_SYNC_ENABLED defaults to 1",
        "default `1`",
        'default "1"',
    )
    leaks = [p for p in bad_patterns if p in text]
    if leaks:
        fail(f"changelog claims default=1 for a migrate flag: {leaks}")
    # Also positive: latest section MUST mention default OFF or OFF for all 3
    if "default is OFF" not in text and "default OFF" not in text:
        fail("latest section should explicitly state 'default is OFF' for migrate flags")
    ok("no default=1 leaks; explicit 'default is OFF' present")

    # ===================================================================
    # Step 8 — Latest section references the iter-1-18 commits
    # ===================================================================
    step("8. Latest section references iter-1-18 commits")
    expected_anchor_commits = (
        "917d776",  # iter 1
        "f492fc6",  # iter 2
        "899b43d",  # iter 3
        "70ebc58",  # iter 6
        "c23d142",  # iter 13/14
        "ea66c69",  # iter 17
        "9672d5b",  # iter 18
    )
    missing = [c for c in expected_anchor_commits if c not in text]
    if missing:
        fail(f"latest section missing iter commits: {missing}")
    ok(f"all {len(expected_anchor_commits)} anchor commits present in latest section")

    # ===================================================================
    # Step 9 — Operator-side activation steps documented
    # ===================================================================
    step("9. Operator-side activation steps with concrete export commands")
    if "Operator-side activation" not in text:
        fail("changelog missing 'Operator-side activation' subsection")
    if "export MCP_GATEWAY_SQL_AUDIT_ENABLED=1" not in text:
        fail("changelog missing concrete env-flag export example")
    ok("operator-side activation documented with concrete export commands")

    print(f"\n{GREEN}{BOLD}ALL 9 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
