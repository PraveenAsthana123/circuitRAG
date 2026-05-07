# RESOURCES: readonly
"""
Drill: README.md Snapshot section currency + metric-truth.

Per CLAUDE.md §51.1 (forensic substrate) + §51.2 (README snapshot
pattern). Every project's root README.md MUST have a "Snapshot"
section with date+location+metrics+trust signals+standards. The
metrics MUST be verifiable via the documented commands; staleness
silently rots the snapshot's trust value.

Locks (positive):
  L1. README.md exists at repo root
  L2. Has a "## Snapshot" section near the top
  L3. Snapshot header has a YYYY-MM-DD date in the year 2026 (current)
  L4. Snapshot header includes location (Linux x86_64 / dev-host)
  L5. Lists drill count, ADR count, runbook count via verify commands

Locks (negative — ≥3 per §43):
  N1. Drill count in README ≤ actual drill count on disk (stale =
      under-count is acceptable; over-count = lying)
  N2. ADR count in README ≤ actual ADR count on disk (same logic)
  N3. Runbook count in README ≤ actual runbook count on disk
  N4. Snapshot date is NOT older than 30 days (otherwise the
      whole snapshot is by definition stale)
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
README = REPO / "README.md"

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


def _count_glob(pattern: str) -> int:
    """Count files via shell glob (matches the README's verification command)."""
    out = subprocess.run(
        ["bash", "-c", f"ls {pattern} 2>/dev/null | wc -l"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    try:
        return int(out.stdout.strip())
    except ValueError:
        return 0


def main() -> int:
    # ===================================================================
    # Step 1 — README exists
    # ===================================================================
    step("1. README.md exists at repo root")
    if not README.exists():
        fail("README.md missing")
    text = README.read_text(encoding="utf-8")
    if len(text) < 1000:
        fail(f"README too small ({len(text)}B)")
    ok(f"README.md present ({len(text)}B)")

    # ===================================================================
    # Step 2 — Snapshot section exists near the top
    # ===================================================================
    step("2. Snapshot section near the top of README")
    if "## Snapshot" not in text:
        fail("missing '## Snapshot' section")
    snapshot_idx = text.index("## Snapshot")
    if snapshot_idx > 4000:
        fail(f"Snapshot section is at byte {snapshot_idx} — should be near top")
    ok(f"## Snapshot at byte {snapshot_idx}")

    # ===================================================================
    # Step 3 — Date is YYYY-MM-DD in 2026 (current year)
    # ===================================================================
    step("3. Snapshot header has 2026 YYYY-MM-DD date")
    snapshot_block = text[snapshot_idx:snapshot_idx + 500]
    m = re.search(r"\((\d{4})-(\d{2})-(\d{2})", snapshot_block)
    if not m:
        fail(f"no YYYY-MM-DD found in snapshot header: {snapshot_block[:200]}")
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year != 2026:
        fail(f"snapshot date year={year} — expected 2026 (current)")
    ok(f"snapshot header has date {year}-{month:02d}-{day:02d}")

    # ===================================================================
    # Step 4 — Date NOT older than 30 days
    # ===================================================================
    step("4. NEGATIVE: snapshot date NOT older than 30 days (staleness floor)")
    snapshot_date = dt.date(year, month, day)
    today = dt.date.today()
    days_old = (today - snapshot_date).days
    if days_old > 30:
        fail(f"snapshot date {snapshot_date} is {days_old}d old — stale (>30d)")
    if days_old < 0:
        # Future date — fine for a Just-updated snapshot
        ok(f"snapshot date {snapshot_date} (future-tagged for next-session continuity)")
    else:
        ok(f"snapshot date {snapshot_date} is {days_old}d old (≤30d)")

    # ===================================================================
    # Step 5 — Location field present
    # ===================================================================
    step("5. Snapshot header includes location")
    location_keywords = ("Linux", "x86_64", "dev-host", "praveen-dev", "MDT", "UTC")
    if not any(kw in snapshot_block for kw in location_keywords):
        fail(f"snapshot header missing location keyword: {snapshot_block[:200]}")
    ok("location keyword present in snapshot header")

    # ===================================================================
    # Step 6 — NEGATIVE: drill count in README ≤ actual count
    # ===================================================================
    step("6. NEGATIVE: drill count in README ≤ actual drill count on disk")
    actual_drills = _count_glob("mcp/tests/drill_*.py")
    # Find the drill count line
    m = re.search(r"\*\*Drills\*\*.*?\*\*(\d+)\*\*", text)
    if not m:
        fail("README has no '**Drills**' metric line")
    readme_drills = int(m.group(1))
    if readme_drills > actual_drills:
        fail(f"README claims {readme_drills} drills but only {actual_drills} on disk — over-count = stale")
    if readme_drills < actual_drills - 50:
        fail(f"README claims {readme_drills} but {actual_drills} on disk — gap >50; update needed")
    ok(f"README claims {readme_drills} drills; actual is {actual_drills} (gap={actual_drills-readme_drills})")

    # ===================================================================
    # Step 7 — NEGATIVE: ADR count in README ≤ actual count
    # ===================================================================
    step("7. NEGATIVE: ADR count in README ≤ actual ADR count on disk")
    # Count only numbered ADRs (0NN-*.md), not README.md
    actual_adrs = _count_glob("docs/architecture/adr/0*.md")
    m = re.search(r"\*\*ADRs\*\*.*?\*\*(\d+)\*\*", text)
    if not m:
        fail("README has no '**ADRs**' metric line")
    readme_adrs = int(m.group(1))
    if readme_adrs > actual_adrs:
        fail(f"README claims {readme_adrs} ADRs but only {actual_adrs} on disk — over-count = lying")
    ok(f"README claims {readme_adrs} ADRs; actual is {actual_adrs}")

    # ===================================================================
    # Step 8 — NEGATIVE: runbook count in README ≤ actual count
    # ===================================================================
    step("8. NEGATIVE: runbook count in README ≤ actual on disk")
    actual_runbooks = _count_glob("docs/runbooks/*.md")
    m = re.search(r"\*\*Runbooks\*\*.*?\*\*(\d+)\*\*", text)
    if not m:
        fail("README has no '**Runbooks**' metric line")
    readme_rbs = int(m.group(1))
    if readme_rbs > actual_runbooks:
        fail(f"README claims {readme_rbs} runbooks but only {actual_runbooks} on disk")
    ok(f"README claims {readme_rbs} runbooks; actual is {actual_runbooks}")

    # ===================================================================
    # Step 9 — Trust signals block lists verify-stack
    # ===================================================================
    step("9. Trust signals block references verify-stack.sh")
    if "verify-stack.sh" not in text:
        fail("README Trust Signals block missing verify-stack.sh reference")
    if "ruff check" not in text:
        fail("README missing ruff trust signal")
    if "mypy" not in text:
        fail("README missing mypy trust signal")
    ok("verify-stack + ruff + mypy all referenced as trust signals")

    print(f"\n{GREEN}{BOLD}ALL 9 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
