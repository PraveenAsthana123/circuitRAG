#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: scripts/council_stats_snapshot.py — daily snapshot contract.

Phase 5N records one snapshot row per calendar date in an
append-only JSONL file. Long-term trends survive log rotation, and
read cost is O(snapshots) instead of O(council_runs).

This drill locks the contract:
  * snapshot_row counts entries from the target UTC date only
  * append-only writes never truncate (crash-safe)
  * read_snapshots dedups by date, keeping latest snapshot_taken_at
  * missing council_runs.log → zero row (cron-safe)
  * malformed --date arg rejected (don't write garbage)

Eight steps. Six negative assertions.

  1. take_snapshot computes correct counts for entries on the target
     UTC date (mixed outcomes — fired/filtered/skipped/error).
  2. NEGATIVE: entries from OTHER dates are NOT counted. Without
     this, a '--date 2026-04-28' run would leak yesterday's entries
     into today's snapshot. Drill drops in a 'previous day' entry.
  3. NEGATIVE: missing council_runs.log → zero row, no crash. The
     pre-bootstrap path; cron must survive day 1.
  4. NEGATIVE: append_snapshot creates the parent directory if
     it doesn't exist. First cron run must not fail on missing
     .loop/ directory.
  5. NEGATIVE: append_snapshot APPENDS — does not truncate. A
     second snapshot for the same date adds a second line; the
     read-time dedup picks the latest one. Drill verifies BOTH
     lines are on disk after two appends.
  6. NEGATIVE: read_snapshots dedups by date — latest
     snapshot_taken_at wins. The pattern is JSONL append + read-
     dedup; without dedup, each cron-fire would inflate the table.
  7. NEGATIVE: ISO week derived from target_date matches
     iso_week_key on the same day. The two paths must agree —
     drift between them would split daily and weekly views.
  8. NEGATIVE: parse_date_arg rejects malformed dates. argparse
     surfaces the error; we don't write a snapshot row with a
     garbage 'date' field.

Run: python3 mcp/tests/drill_council_stats_snapshot.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_snapshot():
    p = REPO / "scripts" / "council_stats_snapshot.py"
    spec = importlib.util.spec_from_file_location("_snap_drill_5N", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_snap_drill_5N"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_stats():
    p = REPO / "scripts" / "council_filter_stats.py"
    spec = importlib.util.spec_from_file_location("_stats_for_5N_drill", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_stats_for_5N_drill"] = mod
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
    snap = _load_snapshot()

    # ── Step 1: take_snapshot computes correct mixed-outcome row ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        target = date(2026, 4, 28)
        entries = [
            # 4 entries on target date with mixed outcomes
            _entry("2026-04-28T10:00:00+00:00"),  # fired MEDIUM
            _entry("2026-04-28T11:00:00+00:00", risk_level="LOW"),  # fired LOW
            _entry("2026-04-28T12:00:00+00:00", fired=False, filtered=True,
                   reason="filtered: skip_token (payload=200, files=3)"),
            _entry("2026-04-28T13:00:00+00:00", fired=False, filtered=False,
                   reason="no_council requested"),
        ]
        log_path = _write_log(tmpdir, entries)
        row = snap.take_snapshot(log_path, target)
        if row["date"] != "2026-04-28":
            print(f"✗ step 1: row['date']={row['date']!r}, expected '2026-04-28'")
            return 1
        if row["total"] != 4:
            print(f"✗ step 1: total={row['total']}, expected 4")
            return 1
        if row["fired"] != 2 or row["filtered"] != 1 or row["skipped"] != 1:
            print(f"✗ step 1: counts wrong — fired={row['fired']}, "
                  f"filtered={row['filtered']}, skipped={row['skipped']}")
            return 1
        if row["fired_by_risk"] != {"MEDIUM": 1, "LOW": 1}:
            print(f"✗ step 1: fired_by_risk wrong: {row['fired_by_risk']}")
            return 1
        if row["filtered_by_reason"] != {"skip_token": 1}:
            print(f"✗ step 1: filtered_by_reason wrong: {row['filtered_by_reason']}")
            return 1
        print("✓ step 1: target-date row correctly counts mixed outcomes")

    # ── Step 2: NEGATIVE — other-date entries excluded ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        target = date(2026, 4, 28)
        entries = [
            # Target date: 2 entries
            _entry("2026-04-28T10:00:00+00:00"),
            _entry("2026-04-28T11:00:00+00:00"),
            # Previous day: 5 entries that MUST NOT count
            _entry("2026-04-27T10:00:00+00:00"),
            _entry("2026-04-27T11:00:00+00:00"),
            _entry("2026-04-27T12:00:00+00:00"),
            _entry("2026-04-27T13:00:00+00:00"),
            _entry("2026-04-27T14:00:00+00:00"),
            # Next day: 1 entry that MUST NOT count
            _entry("2026-04-29T01:00:00+00:00"),
        ]
        log_path = _write_log(tmpdir, entries)
        row = snap.take_snapshot(log_path, target)
        if row["total"] != 2:
            print(f"✗ step 2: total={row['total']}, expected 2 (other-date entries leaked)")
            return 1
        print("✓ step 2: only target-date entries counted "
              "(prev-day + next-day excluded)")

    # ── Step 3: NEGATIVE — missing council_runs.log is safe ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        missing = tmpdir / "does-not-exist.log"
        target = date(2026, 4, 28)
        try:
            row = snap.take_snapshot(missing, target)
        except Exception as exc:
            print(f"✗ step 3: missing log crashed: {type(exc).__name__}: {exc}")
            return 1
        if row["total"] != 0:
            print(f"✗ step 3: missing log → total={row['total']}, expected 0")
            return 1
        if row["date"] != "2026-04-28":
            print(f"✗ step 3: row['date']={row['date']!r}, expected '2026-04-28'")
            return 1
        # iso_week must still be populated even when log is missing —
        # we know what week the target date is in.
        if not row["iso_week"]:
            print("✗ step 3: iso_week empty, expected ISO key")
            return 1
        print("✓ step 3: missing log → zero row with date+iso_week populated (cron-safe)")

    # ── Step 4: NEGATIVE — append_snapshot creates parent dir ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        # Path with non-existent parent directory
        snap_path = tmpdir / "deeply" / "nested" / "council_stats_daily.jsonl"
        if snap_path.parent.exists():
            print(f"✗ step 4: parent {snap_path.parent} unexpectedly exists")
            return 1
        row = snap.take_snapshot(tmpdir / "missing.log", date(2026, 4, 28))
        try:
            snap.append_snapshot(snap_path, row)
        except Exception as exc:
            print(f"✗ step 4: append crashed on missing parent: "
                  f"{type(exc).__name__}: {exc}")
            return 1
        if not snap_path.exists():
            print(f"✗ step 4: snapshot file not created at {snap_path}")
            return 1
        print("✓ step 4: append_snapshot creates parent dir (first-cron-run safe)")

    # ── Step 5: NEGATIVE — append doesn't truncate ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        snap_path = tmpdir / "snap.jsonl"
        target = date(2026, 4, 28)
        row1 = snap.take_snapshot(tmpdir / "no-log.log", target)
        # Mutate snapshot_taken_at to differ between the two writes
        row1["snapshot_taken_at"] = "2026-04-29T01:00:00+00:00"
        row2 = dict(row1)
        row2["snapshot_taken_at"] = "2026-04-29T05:00:00+00:00"
        row2["total"] = 999  # different content
        snap.append_snapshot(snap_path, row1)
        snap.append_snapshot(snap_path, row2)
        # Both lines must be on disk (no truncate)
        lines = snap_path.read_text().strip().splitlines()
        if len(lines) != 2:
            print(f"✗ step 5: file has {len(lines)} lines, expected 2 "
                  "(append must not truncate)")
            return 1
        # And the original row1 line must be intact (not overwritten)
        first = json.loads(lines[0])
        if first.get("snapshot_taken_at") != "2026-04-29T01:00:00+00:00":
            print("✗ step 5: first line was overwritten")
            return 1
        print("✓ step 5: append_snapshot is append-only (2 lines for 2 writes)")

    # ── Step 6: NEGATIVE — read_snapshots dedups by date ──
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        snap_path = tmpdir / "snap.jsonl"
        # Three snapshots for same date with different snapshot_taken_at
        rows = [
            {"date": "2026-04-28", "iso_week": "2026-W18", "total": 1,
             "fired": 1, "filtered": 0, "skipped": 0, "council_errors": 0,
             "snapshot_taken_at": "2026-04-29T01:00:00+00:00"},
            {"date": "2026-04-28", "iso_week": "2026-W18", "total": 5,
             "fired": 5, "filtered": 0, "skipped": 0, "council_errors": 0,
             "snapshot_taken_at": "2026-04-29T03:00:00+00:00"},
            {"date": "2026-04-28", "iso_week": "2026-W18", "total": 13,
             "fired": 9, "filtered": 1, "skipped": 2, "council_errors": 1,
             "snapshot_taken_at": "2026-04-29T05:00:00+00:00"},
            # Different date — should also be in result
            {"date": "2026-04-27", "iso_week": "2026-W17", "total": 8,
             "fired": 8, "filtered": 0, "skipped": 0, "council_errors": 0,
             "snapshot_taken_at": "2026-04-28T01:00:00+00:00"},
        ]
        with snap_path.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        deduped = snap.read_snapshots(snap_path)
        if len(deduped) != 2:
            print(f"✗ step 6: deduped {len(deduped)} rows, expected 2 "
                  "(one per unique date)")
            return 1
        # The 2026-04-28 row must be the LATEST one (total=13)
        d28 = [r for r in deduped if r["date"] == "2026-04-28"][0]
        if d28["total"] != 13:
            print(f"✗ step 6: deduped 2026-04-28 row has total={d28['total']}, "
                  "expected 13 (latest snapshot_taken_at should win)")
            return 1
        # Newest date first
        if deduped[0]["date"] != "2026-04-28":
            print(f"✗ step 6: dedup order wrong: {[r['date'] for r in deduped]}")
            return 1
        print("✓ step 6: read_snapshots dedups by date, latest snapshot_taken_at wins")

    # ── Step 7: NEGATIVE — iso_week consistency with iso_week_key ──
    stats = _load_stats()
    boundary_dates = [
        date(2024, 12, 29),  # ISO 2024-W52
        date(2024, 12, 30),  # ISO 2025-W01
        date(2026, 1, 1),    # ISO 2026-W01 (Thursday)
        date(2026, 4, 28),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for d in boundary_dates:
            row = snap.take_snapshot(tmpdir / "no.log", d)
            # Build a ts at noon UTC on that date and ask iso_week_key
            ts = datetime(d.year, d.month, d.day, 12, 0, 0,
                          tzinfo=UTC).isoformat()
            expected = stats.iso_week_key(ts)
            if row["iso_week"] != expected:
                print(f"✗ step 7: snapshot iso_week={row['iso_week']!r} for "
                      f"{d}, but iso_week_key says {expected!r}. Drift "
                      "between snapshot and weekly views breaks trend.")
                return 1
        print(f"✓ step 7: snapshot iso_week matches iso_week_key on "
              f"{len(boundary_dates)} dates (incl ISO year boundary)")

    # ── Step 8: NEGATIVE — parse_date_arg rejects malformed input ──
    bad_inputs = ["2026-13-40", "not-a-date", "20260428", "2026/04/28",
                  "2026-4-28", ""]
    for bad in bad_inputs:
        try:
            snap.parse_date_arg(bad)
        except ValueError:
            continue
        print(f"✗ step 8: parse_date_arg({bad!r}) accepted; should raise")
        return 1
    # And a good one parses
    good = snap.parse_date_arg("2026-04-28")
    if good != date(2026, 4, 28):
        print(f"✗ step 8: parse_date_arg('2026-04-28') = {good!r}")
        return 1
    print(f"✓ step 8: parse_date_arg rejects {len(bad_inputs)} bad forms, "
          "accepts canonical YYYY-MM-DD")

    print("\nALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
