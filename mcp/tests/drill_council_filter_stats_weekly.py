#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: council_filter_stats.py --weekly mode (Phase 5M).

Phase 5L gave operators a single-window histogram. Phase 5M adds
a per-ISO-week breakdown so trends are visible: "is too_short rate
rising over the last 4 weeks?"

The trend view shares the per-entry classification with the single-
window view (extracted to classify_entry()) so the
total = fired + filtered + skipped + errors invariant holds PER WEEK,
not just globally.

Eight steps. Six negative assertions.

  1. iso_week_key parses ISO timestamps to "YYYY-Www" form.
  2. NEGATIVE: ISO YEAR boundary — a Jan 1, 2026 timestamp can fall
     into ISO week 2025-W53 (or 2026-W01 depending on weekday). The
     drill verifies we use isocalendar()'s OWN year, not the
     calendar year. Without this, year-boundary entries would
     create phantom buckets and split the trend.
  3. NEGATIVE: rows sorted newest first (string sort works for
     ISO-week keys IF zero-padded — '2026-W09' < '2026-W10').
  4. NEGATIVE: --weeks N keeps only the last N DATED weeks.
     Sparse data (gaps) doesn't pad the count; we keep the N
     populated weeks that exist.
  5. NEGATIVE: per-row invariant total = fired + filtered + skipped
     + errors. Same drill step 4 invariant from 5L, lifted to per-week.
  6. NEGATIVE: unparseable timestamp lands in 'unparseable' bucket —
     NOT lost, NOT silently dropped, NOT collapsed into a real week.
     The bucket sorts AFTER all dated weeks so it's visible but
     out of the way.
  7. NEGATIVE: empty log → empty rows list, no crash. render_weekly
     handles the empty case with a sensible message.
  8. POSITIVE: render_weekly produces a readable fixed-width table —
     header line, divider line, data rows in newest-first order.

Run: python3 mcp/tests/drill_council_filter_stats_weekly.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_stats():
    p = REPO / "scripts" / "council_filter_stats.py"
    spec = importlib.util.spec_from_file_location("_stats_drill_5M", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_stats_drill_5M"] = mod
    spec.loader.exec_module(mod)
    return mod


def _entry(timestamp: str, *, fired: bool = True, filtered: bool = False,
           reason: str = "council_completed risk=MEDIUM",
           risk_level: str = "MEDIUM") -> dict:
    return {"timestamp": timestamp, "fired": fired, "filtered": filtered,
            "reason": reason, "risk_level": risk_level}


def _write_log(tmpdir: Path, entries: list[dict]) -> Path:
    p = tmpdir / "council_runs.log"
    with p.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return p


def main() -> int:
    stats = _load_stats()

    # ── Step 1: iso_week_key parses ISO timestamps ──
    cases = [
        # (timestamp, expected ISO key)
        ("2026-04-28T16:54:12+00:00", "2026-W18"),
        ("2026-01-01T00:00:00+00:00", "2026-W01"),  # Jan 1 2026 is Thursday → W01
        ("2025-06-15T12:00:00+00:00", "2025-W24"),
    ]
    for ts, expected in cases:
        got = stats.iso_week_key(ts)
        if got != expected:
            print(f"✗ step 1: iso_week_key({ts!r}) → {got!r}, expected {expected!r}")
            return 1
    print(f"✓ step 1: {len(cases)} ISO timestamps parsed to YYYY-Www form")

    # ── Step 2: NEGATIVE — ISO year boundary ──
    # 2024-12-30 is a Monday → ISO week 2025-W01 (Dec 30 2024 belongs
    # to ISO YEAR 2025 because the Thursday of that week falls in 2025).
    # 2024-12-29 is a Sunday → ISO week 2024-W52 (still in 2024).
    # If we used .year instead of isocalendar()[0], both would map to
    # 2024-Wxx, splitting the boundary into phantom buckets.
    boundary_cases = [
        ("2024-12-29T12:00:00+00:00", "2024-W52"),  # Sunday — last week of 2024
        ("2024-12-30T12:00:00+00:00", "2025-W01"),  # Monday — first ISO week of 2025
        ("2026-01-04T12:00:00+00:00", "2026-W01"),  # Sunday — week 1 of 2026
    ]
    for ts, expected in boundary_cases:
        got = stats.iso_week_key(ts)
        if got != expected:
            print(f"✗ step 2: ISO year boundary fail: {ts!r} → {got!r}, "
                  f"expected {expected!r}. We must use isocalendar()'s "
                  "iso-year, not datetime.year, or year-boundary entries "
                  "create phantom buckets.")
            return 1
    print(f"✓ step 2: {len(boundary_cases)} ISO year boundaries handled correctly")

    # ── Step 3: NEGATIVE — rows sorted newest first ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        entries = [
            _entry("2026-04-15T10:00:00+00:00"),  # 2026-W16
            _entry("2026-04-08T10:00:00+00:00"),  # 2026-W15
            _entry("2026-04-22T10:00:00+00:00"),  # 2026-W17
            _entry("2026-04-28T10:00:00+00:00"),  # 2026-W18
        ]
        log_path = _write_log(tmpdir, entries)
        weekly = stats.summarize_by_week(log_path, weeks=None)
        weeks = [r["week"] for r in weekly["rows"]]
        expected = ["2026-W18", "2026-W17", "2026-W16", "2026-W15"]
        if weeks != expected:
            print(f"✗ step 3: rows order {weeks}, expected {expected}")
            return 1
        print(f"✓ step 3: {len(weeks)} weeks sorted newest first {weeks}")

    # ── Step 4: NEGATIVE — --weeks N keeps last N DATED weeks ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        entries = [
            _entry("2026-04-08T10:00:00+00:00"),  # W15
            _entry("2026-04-15T10:00:00+00:00"),  # W16
            _entry("2026-04-22T10:00:00+00:00"),  # W17
            _entry("2026-04-28T10:00:00+00:00"),  # W18
        ]
        log_path = _write_log(tmpdir, entries)
        weekly = stats.summarize_by_week(log_path, weeks=2)
        weeks = [r["week"] for r in weekly["rows"]]
        if weeks != ["2026-W18", "2026-W17"]:
            print(f"✗ step 4: --weeks 2 returned {weeks}, "
                  "expected ['2026-W18', '2026-W17']")
            return 1
        # Also make sure --weeks N=0 returns no rows (boundary)
        zero = stats.summarize_by_week(log_path, weeks=0)
        if zero["rows"]:
            print(f"✗ step 4b: --weeks 0 returned {len(zero['rows'])} rows, expected 0")
            return 1
        print("✓ step 4: --weeks N keeps last N dated weeks; N=0 returns 0 rows")

    # ── Step 5: NEGATIVE — per-row invariant ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        entries = [
            # 4 entries in W18, mixed outcomes
            _entry("2026-04-28T10:00:00+00:00"),  # fired MEDIUM
            _entry("2026-04-28T11:00:00+00:00", risk_level="LOW"),  # fired LOW
            _entry("2026-04-28T12:00:00+00:00", fired=False, filtered=True,
                   reason="filtered: skip_token (payload=200, files=3)"),  # filtered
            _entry("2026-04-28T13:00:00+00:00", fired=False, filtered=False,
                   reason="no_council requested"),  # skipped
            # 1 entry in W17, error path
            _entry("2026-04-22T10:00:00+00:00",
                   reason="council_error: ImportError"),  # council_error
        ]
        log_path = _write_log(tmpdir, entries)
        weekly = stats.summarize_by_week(log_path, weeks=None)
        for r in weekly["rows"]:
            sub_total = r["fired"] + r["filtered"] + r["skipped"] + r["errors"]
            if sub_total != r["total"]:
                print(f"✗ step 5: row {r['week']} total={r['total']}, "
                      f"sum={sub_total}. Per-week invariant broken.")
                return 1
        # Also check across-rows total = sum of per-row totals
        global_total = sum(r["total"] for r in weekly["rows"])
        if global_total != len(entries):
            print(f"✗ step 5b: across-rows total={global_total}, "
                  f"expected {len(entries)}. Some entries silently dropped.")
            return 1
        print(f"✓ step 5: per-week invariant total = fired+filtered+skipped+errors "
              f"holds for {len(weekly['rows'])} weeks; global preserved")

    # ── Step 6: NEGATIVE — unparseable timestamps land in 'unparseable' ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        entries = [
            _entry("2026-04-28T10:00:00+00:00"),  # 2026-W18
            _entry("not-a-timestamp"),            # unparseable
            _entry(""),                            # empty timestamp → unparseable
            _entry("2026-04-22T10:00:00+00:00"),  # 2026-W17
        ]
        log_path = _write_log(tmpdir, entries)
        weekly = stats.summarize_by_week(log_path, weeks=None)
        weeks = [r["week"] for r in weekly["rows"]]
        if weeks != ["2026-W18", "2026-W17", "unparseable"]:
            print(f"✗ step 6: unparseable handling wrong: {weeks}, "
                  "expected ['2026-W18', '2026-W17', 'unparseable']")
            return 1
        unparseable_row = [r for r in weekly["rows"] if r["week"] == "unparseable"][0]
        if unparseable_row["total"] != 2:
            print(f"✗ step 6: unparseable row total={unparseable_row['total']}, "
                  "expected 2 (one bad timestamp + one empty)")
            return 1
        # And --weeks 1 should keep BOTH the latest dated week AND unparseable
        weekly_w1 = stats.summarize_by_week(log_path, weeks=1)
        weeks = [r["week"] for r in weekly_w1["rows"]]
        if weeks != ["2026-W18", "unparseable"]:
            print(f"✗ step 6: --weeks 1 dropped 'unparseable': {weeks}")
            return 1
        print("✓ step 6: unparseable bucket visible, sorted last, preserved across --weeks N")

    # ── Step 7: NEGATIVE — empty log is safe ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        log_path = tmpdir / "council_runs.log"
        log_path.write_text("")
        weekly = stats.summarize_by_week(log_path, weeks=None)
        if weekly["rows"]:
            print(f"✗ step 7: empty log returned {len(weekly['rows'])} rows, expected 0")
            return 1
        rendered = stats.render_weekly(weekly)
        if "no entries" not in rendered:
            print(f"✗ step 7: render_weekly empty case missing message: {rendered!r}")
            return 1
        print("✓ step 7: empty log → 0 rows, render_weekly handles gracefully")

    # ── Step 8: POSITIVE — render_weekly produces readable table ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        entries = [
            _entry("2026-04-28T10:00:00+00:00"),
            _entry("2026-04-22T10:00:00+00:00"),
        ]
        log_path = _write_log(tmpdir, entries)
        weekly = stats.summarize_by_week(log_path, weeks=None)
        rendered = stats.render_weekly(weekly)
        # Required pieces of a readable table:
        required = ["week", "total", "fired", "filtered",
                    "skipped", "errors", "2026-W18", "2026-W17",
                    "---"]   # divider line
        for token in required:
            if token not in rendered:
                print(f"✗ step 8: rendered table missing {token!r}\n{rendered}")
                return 1
        # Newest week appears before older week in the rendered output.
        if rendered.index("2026-W18") > rendered.index("2026-W17"):
            print("✗ step 8: rendered table not in newest-first order")
            return 1
        print("✓ step 8: render_weekly produces table with header + divider + sorted rows")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
