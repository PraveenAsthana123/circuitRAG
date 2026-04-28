#!/usr/bin/env python3
"""Daily council outcome snapshot — append-only JSONL for long-term trends.

Phase 5L/M let operators ask "what's last week's filter rate?" by
parsing the full .loop/council_runs.log every time. That's fine for
short windows but doesn't scale: as the log grows, every dashboard
read pays O(n). And after log rotation / pruning, history vanishes.

Phase 5N closes both gaps with a cron-friendly daily snapshot:

  cron: 5 0 * * * /tmp/documind-venv/bin/python /mnt/deepa/rag/scripts/council_stats_snapshot.py

Each run computes one row for a target date (default: yesterday in
UTC) and APPENDS it to .loop/council_stats_daily.jsonl. Append-only
writes are crash-safe; dedup happens at READ time via the
read_snapshots() helper, which keeps the latest snapshot_taken_at
for each date.

One snapshot row:

    {
      "date": "2026-04-28",
      "iso_week": "2026-W18",
      "total": 13,
      "fired": 9,
      "filtered": 1,
      "skipped": 2,
      "council_errors": 1,
      "fired_by_risk": {"MEDIUM": 8, "LOW": 1},
      "filtered_by_reason": {"legacy": 1},
      "skipped_by_reason": {"no_council": 2},
      "snapshot_taken_at": "2026-04-29T00:05:00+00:00"
    }

Operator usage:

    python3 scripts/council_stats_snapshot.py                 # yesterday
    python3 scripts/council_stats_snapshot.py --date 2026-04-28
    python3 scripts/council_stats_snapshot.py --read          # dump deduped snapshots
    python3 scripts/council_stats_snapshot.py --read --json   # JSON pipe

Exit code: 0 on success, 1 on bad args (e.g. malformed --date).
Missing council_runs.log is NOT an error — we record an all-zero row
so trends survive bootstrap state.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Strict date format: exactly YYYY-MM-DD with dashes and zero-padded.
# date.fromisoformat alone accepts '20260428' on Python 3.11+; we want
# the dashed canonical form so log scans + dashboard queries are
# consistent.
_DATE_ARG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REPO = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = REPO / ".loop" / "council_runs.log"
DEFAULT_SNAPSHOT_PATH = REPO / ".loop" / "council_stats_daily.jsonl"

log = logging.getLogger("council_stats_snapshot")


def _load_stats():
    """Lazily load council_filter_stats so we reuse classify_entry +
    iso_week_key + parse_filter_reason without copy-paste drift."""
    p = REPO / "scripts" / "council_filter_stats.py"
    spec = importlib.util.spec_from_file_location("_stats_for_snapshot", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_stats_for_snapshot"] = mod
    spec.loader.exec_module(mod)
    return mod


def parse_date_arg(s: str) -> date:
    """Parse a STRICT YYYY-MM-DD CLI arg.

    Two-stage strictness so we accept ONLY the canonical dashed form:
      1. _DATE_ARG_RE: dashes + zero-padded (rejects '2026-4-28',
         '20260428', '2026/04/28').
      2. date.fromisoformat: validates the calendar (rejects 2026-13-01).

    Raises ValueError on bad format — argparse renders it."""
    if not _DATE_ARG_RE.match(s):
        raise ValueError(f"date must be YYYY-MM-DD with dashes; got {s!r}")
    return date.fromisoformat(s)


def take_snapshot(
    log_path: Path,
    target_date: date,
) -> dict:
    """Compute the snapshot row for `target_date`. Returns the row dict
    (NOT yet written). Caller appends to the snapshot file.

    A missing log_path is NOT an error — return a zeroed row. This
    lets the cron tick survive bootstrap state without alerts.
    """
    stats = _load_stats()

    # We can't reuse summarize() directly because its window is
    # 'last N days' not 'a specific calendar date'. Walk entries
    # ourselves and filter on UTC date prefix.
    target_str = target_date.isoformat()
    fired_by_risk: dict[str, int] = {}
    filtered_by_reason: dict[str, int] = {}
    skipped_by_reason: dict[str, int] = {}
    council_errors = 0
    total = 0

    if log_path.exists():
        with log_path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = str(entry.get("timestamp", ""))
                # Match by UTC calendar date prefix. Timestamps are
                # ISO 8601 with "+00:00" suffix; the date prefix is
                # always the first 10 characters.
                if ts[:10] != target_str:
                    continue
                klass, sub_bucket = stats.classify_entry(entry)
                total += 1
                if klass == "fired":
                    fired_by_risk[sub_bucket] = fired_by_risk.get(sub_bucket, 0) + 1
                elif klass == "council_error":
                    council_errors += 1
                elif klass == "filtered":
                    filtered_by_reason[sub_bucket] = filtered_by_reason.get(sub_bucket, 0) + 1
                elif klass == "skipped":
                    skipped_by_reason[sub_bucket] = skipped_by_reason.get(sub_bucket, 0) + 1

    iso_year, iso_week, _ = target_date.isocalendar()
    iso_week_key = f"{iso_year}-W{iso_week:02d}"

    return {
        "date": target_str,
        "iso_week": iso_week_key,
        "total": total,
        "fired": sum(fired_by_risk.values()),
        "filtered": sum(filtered_by_reason.values()),
        "skipped": sum(skipped_by_reason.values()),
        "council_errors": council_errors,
        "fired_by_risk": fired_by_risk,
        "filtered_by_reason": filtered_by_reason,
        "skipped_by_reason": skipped_by_reason,
        "snapshot_taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def append_snapshot(snapshot_path: Path, row: dict) -> None:
    """Append a snapshot row as one JSON line. Creates parent dir if
    missing (first-run safe)."""
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with snapshot_path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def read_snapshots(snapshot_path: Path) -> list[dict]:
    """Read all snapshots and dedup by date — keep the latest
    snapshot_taken_at per calendar date. Newest date first.

    Append-only writes mean two cron runs on the same day produce
    two rows; the read-time dedup keeps the second one (which saw
    more entries). Operators always see one row per date."""
    if not snapshot_path.exists():
        return []
    by_date: dict[str, dict] = {}
    with snapshot_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = str(row.get("date", ""))
            if not d:
                continue
            existing = by_date.get(d)
            if existing is None:
                by_date[d] = row
            else:
                # Keep the snapshot with the LATER snapshot_taken_at.
                a = str(existing.get("snapshot_taken_at", ""))
                b = str(row.get("snapshot_taken_at", ""))
                if b > a:  # ISO timestamps sort lexicographically
                    by_date[d] = row
    # Newest date first
    return sorted(by_date.values(), key=lambda r: r["date"], reverse=True)


def render_snapshots(snapshots: list[dict]) -> str:
    """Fixed-width table, newest date first."""
    if not snapshots:
        return "council outcome daily snapshots:\n  (no snapshots yet)"
    lines = [
        "council outcome daily snapshots:",
        f"  {'date':<11} {'iso_week':<10} {'total':>6} {'fired':>6} "
        f"{'filtered':>9} {'skipped':>8} {'errors':>7}",
        f"  {'-' * 11} {'-' * 10} {'-' * 6} {'-' * 6} {'-' * 9} {'-' * 8} {'-' * 7}",
    ]
    for r in snapshots:
        lines.append(
            f"  {r['date']:<11} {r['iso_week']:<10} {r['total']:>6} "
            f"{r['fired']:>6} {r['filtered']:>9} "
            f"{r['skipped']:>8} {r['council_errors']:>7}"
        )
    return "\n".join(lines)


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-path", default=str(DEFAULT_LOG_PATH),
        help="path to council_runs.log",
    )
    parser.add_argument(
        "--snapshot-path", default=str(DEFAULT_SNAPSHOT_PATH),
        help="path to council_stats_daily.jsonl",
    )
    parser.add_argument(
        "--date", type=parse_date_arg, default=None,
        help="snapshot this date (YYYY-MM-DD); default = yesterday UTC",
    )
    parser.add_argument(
        "--read", action="store_true",
        help="read & print existing snapshots (deduped) instead of taking a new one",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit JSON instead of table",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    snapshot_path = Path(args.snapshot_path)

    if args.read:
        rows = read_snapshots(snapshot_path)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            print(render_snapshots(rows))
        return 0

    target = args.date or (datetime.now(timezone.utc).date() - timedelta(days=1))
    log_path = Path(args.log_path)
    row = take_snapshot(log_path, target)
    append_snapshot(snapshot_path, row)

    if args.json:
        print(json.dumps(row, indent=2))
    else:
        print(
            f"snapshot {row['date']} ({row['iso_week']}) → "
            f"total={row['total']} fired={row['fired']} "
            f"filtered={row['filtered']} skipped={row['skipped']} "
            f"errors={row['council_errors']} → {snapshot_path}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(cli())
