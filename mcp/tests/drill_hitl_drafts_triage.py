# RESOURCES: pg
"""
Drill: scripts/hitl_drafts_triage.py — read-only triage report.

Per CLAUDE.md §38 (governance gates), §43 (drill discipline),
§47.7 operational autonomy boundary, §52 row 4 (operator API gap).

577+ pending governance.action_drafts rows are operator-decision
territory. The triage SCRIPT is read-only autonomous-doable; the
triage DECISIONS are operator territory. This drill locks the
read-only invariant + the report shape.

Locks (positive):
  L1. fetch_drafts + build_report + classify_age + classify_reason
      are public callables
  L2. classify_age returns documented buckets (< 1 day / < 7 days /
      < 30 days / >= 30 days STALE)
  L3. build_report returns markdown with the documented sections
  L4. Round-trip via real DB returns sane drafts list

Locks (negative — ≥3 per §43):
  N1. Read-only contract: source has NO INSERT/UPDATE/DELETE
      against governance.action_drafts (would violate §38)

  N2. fetch_drafts handles PG unreachable gracefully (returns
      empty list + gap_reason; NEVER raises)

  N3. build_report handles empty drafts list → "ALL CLEAR" report,
      not a crash

  N4. CLI output is markdown by default (operator-readable);
      JSON requires explicit --json flag (machine-readable)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

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
    import hitl_drafts_triage  # noqa: E402

    # ===================================================================
    # Step 1 — public API exists
    # ===================================================================
    step("1. hitl_drafts_triage exposes fetch_drafts + build_report + classifiers")
    for name in ("fetch_drafts", "build_report", "classify_age",
                 "classify_reason", "server_from_tool"):
        if not callable(getattr(hitl_drafts_triage, name, None)):
            fail(f"missing public callable: {name}")
    ok("all 5 public callables present")

    # ===================================================================
    # Step 2 — classify_age returns documented buckets
    # ===================================================================
    step("2. classify_age returns documented age buckets")
    cases = [
        (60, "< 1 day"),
        (3600 * 23, "< 1 day"),
        (3600 * 25, "< 7 days"),
        (86400 * 6, "< 7 days"),
        (86400 * 8, "< 30 days"),
        (86400 * 29, "< 30 days"),
        (86400 * 31, ">= 30 days (STALE)"),
        (86400 * 365, ">= 30 days (STALE)"),
    ]
    for age, expected in cases:
        got = hitl_drafts_triage.classify_age(age)
        if got != expected:
            fail(f"age={age}s: expected {expected!r}, got {got!r}")
    ok(f"all {len(cases)} age classifications correct")

    # ===================================================================
    # Step 3 — server_from_tool extracts prefix
    # ===================================================================
    step("3. server_from_tool extracts the prefix")
    cases = [
        ("hr.leave_request", "hr"),
        ("itsm.incident_create", "itsm"),
        ("paperclip.snapshot", "paperclip"),
        ("noprefix", "?"),
        ("", "?"),
    ]
    for tool, expected in cases:
        got = hitl_drafts_triage.server_from_tool(tool)
        if got != expected:
            fail(f"tool={tool!r}: expected {expected!r}, got {got!r}")
    ok(f"all {len(cases)} server-extraction cases correct")

    # ===================================================================
    # Step 4 — build_report on empty list → 'ALL CLEAR'
    # ===================================================================
    step("4. NEGATIVE: build_report with empty drafts → 'ALL CLEAR' (not crash)")
    rep = hitl_drafts_triage.build_report([], None)
    if "ALL CLEAR" not in rep:
        fail("empty drafts should produce 'ALL CLEAR' report")
    if "# HITL Drafts Triage Report" not in rep:
        fail("report missing title header")
    ok("empty drafts → 'ALL CLEAR' markdown report")

    # ===================================================================
    # Step 5 — build_report on PG-down (gap reason) → 'UNAVAILABLE'
    # ===================================================================
    step("5. NEGATIVE: build_report with gap_reason → 'UNAVAILABLE' header")
    rep = hitl_drafts_triage.build_report([], "postgres unreachable")
    if "UNAVAILABLE" not in rep:
        fail("gap_reason should produce 'UNAVAILABLE' report")
    if "postgres unreachable" not in rep:
        fail("report should embed the gap_reason text")
    ok("gap_reason → 'UNAVAILABLE' report with embedded reason")

    # ===================================================================
    # Step 6 — build_report on synthetic non-empty list
    # ===================================================================
    step("6. build_report renders synthetic drafts with all sections")
    import datetime as dt
    synth = [
        {
            "draft_id": "DRILL-1", "tool": "hr.leave_request",
            "reason": "cb_open", "status": "pending",
            "created_at": dt.datetime.now() - dt.timedelta(hours=2),
            "age": dt.timedelta(hours=2),
        },
        {
            "draft_id": "DRILL-2", "tool": "itsm.incident_lookup",
            "reason": "ConnectError", "status": "pending",
            "created_at": dt.datetime.now() - dt.timedelta(days=5),
            "age": dt.timedelta(days=5),
        },
    ]
    rep = hitl_drafts_triage.build_report(synth, None)
    expected_sections = (
        "# HITL Drafts Triage Report",
        "## Summary",
        "## By originating server",
        "## By failure reason",
        "## Stale drafts",
        "## Recommended operator actions",
    )
    for sect in expected_sections:
        if sect not in rep:
            fail(f"missing section: {sect}")
    # Stale-only section may not include synthetic drafts since both are
    # < 30d — but the by-server table should
    if (
        "DRILL-1" not in rep
        and "DRILL-2" not in rep
        and "`hr`" not in rep
    ):
        fail("server breakdown missing 'hr'")
    ok(f"all {len(expected_sections)} sections present in synthetic-input report")

    # ===================================================================
    # Step 7 — fetch_drafts returns (list, gap) tuple shape
    # ===================================================================
    step("7. fetch_drafts returns (list, gap_reason) tuple")
    rows, gap = hitl_drafts_triage.fetch_drafts()
    if not isinstance(rows, list):
        fail(f"fetch_drafts should return list, got {type(rows)}")
    if gap is not None and not isinstance(gap, str):
        fail(f"gap_reason should be str | None, got {type(gap)}")
    ok(f"shape OK: {len(rows)} rows, gap={'set' if gap else 'None'}")

    # ===================================================================
    # Step 8 — NEGATIVE: read-only contract on source
    # ===================================================================
    step("8. NEGATIVE: source has NO INSERT/UPDATE/DELETE on action_drafts")
    src = (REPO / "scripts" / "hitl_drafts_triage.py").read_text(encoding="utf-8")
    forbidden = (
        "INSERT INTO governance.action_drafts",
        "UPDATE governance.action_drafts",
        "DELETE FROM governance.action_drafts",
    )
    leaks = [v for v in forbidden if v in src]
    if leaks:
        fail(f"source has write SQL: {leaks} — would violate §38")
    ok("read-only contract holds; no write SQL against action_drafts")

    # ===================================================================
    # Step 9 — NEGATIVE: CLI default is markdown; --json is opt-in
    # ===================================================================
    step("9. NEGATIVE: CLI default markdown; --json requires explicit flag")
    # Markdown default
    result_md = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "hitl_drafts_triage.py")],
        capture_output=True, text=True, timeout=15,
    )
    if "# HITL Drafts Triage Report" not in result_md.stdout:
        fail(f"markdown default missing title; got: {result_md.stdout[:200]}")
    # JSON opt-in
    result_json = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "hitl_drafts_triage.py"),
         "--json"],
        capture_output=True, text=True, timeout=15,
    )
    if not result_json.stdout.strip().startswith("{"):
        fail(f"--json should produce JSON; got: {result_json.stdout[:100]}")
    ok("default=markdown; --json=JSON; both run cleanly")

    print(f"\n{GREEN}{BOLD}ALL 9 STEPS PASSED{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
