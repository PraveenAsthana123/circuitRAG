#!/usr/bin/env python3
"""Prune old entries from .loop/*.log JSONL files for retention discipline.

Phase 2F shipped a pruner for `advisor_council_runs` (the SQLite
table). Phase 6E shipped this complementary pruner for the JSONL
log files: `watcher.log` (one row per commit verdict) and
`council_runs.log` (one row per council fire). Both grow unbounded
in long-running deployments.

Default retention: 90 days. Older entries are dropped. The pruner
preserves append-only safety via the standard tmp + os.replace
atomic-write pattern (same as Phase 5N's snapshot writer + 5U's
prom export).

Operator usage:

  # Preview what would be pruned (dry-run; safe to re-run):
  python3 scripts/prune_loop_logs.py
  python3 scripts/prune_loop_logs.py --older-than-days 30

  # Actually prune:
  python3 scripts/prune_loop_logs.py --apply
  python3 scripts/prune_loop_logs.py --older-than-days 30 --apply

  # Custom log paths:
  python3 scripts/prune_loop_logs.py --logs .loop/x.log --apply

Defaults:
  older_than_days = 90  (3 months retention)
  --apply         not set  (dry-run; safe re-run)

Schedule for production:
  cron: 0 4 * * 0          # Sundays 04:00 UTC
  command: python3 scripts/prune_loop_logs.py --apply
  redirect to: .loop/prune_logs.log

Companion to Phase 2F: prune_council_runs.py handles the SQLite
side (advisor_council_runs); this script handles the JSONL side.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

REPO = Path(__file__).resolve().parents[1]
DEFAULT_LOGS = [
    REPO / ".loop" / "watcher.log",
    REPO / ".loop" / "council_runs.log",
]
DEFAULT_RETENTION_DAYS = 90

log = logging.getLogger("prune_loop_logs")


def _parse_timestamp(s: str) -> datetime | None:
    """Parse an ISO timestamp; return None if unparseable. Tolerates
    bad rows so a single malformed entry doesn't abort the whole
    prune (per the same data-preservation principle as 5L's
    load_entries)."""
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


def split_entries(
    log_path: Path,
    cutoff: datetime,
) -> tuple[list[str], list[str]]:
    """Return (keep_lines, drop_lines). keep_lines preserves blank
    lines and unparseable rows (we don't drop data we can't classify);
    only entries with a timestamp older than cutoff are dropped.

    Each list element is the original line WITHOUT trailing newline,
    so the writer can normalize line endings on the rewrite."""
    keep: list[str] = []
    drop: list[str] = []
    if not log_path.exists():
        return keep, drop
    with log_path.open() as f:
        for raw in f:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped:
                # Blank line — preserve; doesn't cost retention budget
                keep.append(line)
                continue
            try:
                entry = json.loads(stripped)
            except json.JSONDecodeError:
                # Malformed JSON — preserve; we can't tell if it's
                # old or recent. Operator can sweep manually.
                keep.append(line)
                continue
            ts = _parse_timestamp(str(entry.get("timestamp", "")))
            if ts is None:
                # Bad timestamp — preserve (same principle as 5L:
                # don't lose data because of one malformed field)
                keep.append(line)
                continue
            if ts < cutoff:
                drop.append(line)
            else:
                keep.append(line)
    return keep, drop


def write_atomic(path: Path, lines: list[str]) -> None:
    """Write lines to `path` atomically (tmp + os.replace).

    Same pattern as Phase 5U's write_prometheus_atomic — protects
    readers (cron / dashboard) from seeing a partially-rewritten
    file. POSIX rename is atomic within a single filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        for line in lines:
            f.write(line + "\n")
    os.replace(tmp, path)


def prune_log(
    log_path: Path,
    older_than_days: int,
    apply: bool,
) -> dict:
    """Prune one log file. Returns a report dict."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    keep, drop = split_entries(log_path, cutoff)
    report = {
        "path": str(log_path),
        "exists": log_path.exists(),
        "kept": len(keep),
        "dropped": len(drop),
        "cutoff_iso": cutoff.isoformat(timespec="seconds"),
    }
    if not log_path.exists():
        report["status"] = "no-op (file does not exist)"
        return report
    if not drop:
        report["status"] = "no-op (nothing older than cutoff)"
        return report
    if not apply:
        report["status"] = "dry-run (would drop)"
        return report
    write_atomic(log_path, keep)
    report["status"] = "pruned"
    return report


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--older-than-days", type=int, default=DEFAULT_RETENTION_DAYS,
        help="drop entries older than N days (default: 90)",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="actually rewrite the log file (default: dry-run)",
    )
    parser.add_argument(
        "--logs", action="append", metavar="PATH",
        help="path to a JSONL log to prune; can repeat. "
             "Default: .loop/watcher.log + .loop/council_runs.log",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit machine-readable JSON instead of text",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.older_than_days <= 0:
        print(f"--older-than-days must be > 0; got {args.older_than_days}",
              file=sys.stderr)
        return 1

    log_paths = [Path(p) for p in args.logs] if args.logs else DEFAULT_LOGS
    reports = []
    for p in log_paths:
        report = prune_log(p, args.older_than_days, args.apply)
        reports.append(report)

    if args.json:
        print(json.dumps({"reports": reports, "applied": args.apply}, indent=2))
    else:
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"[prune_loop_logs] mode={mode} retention={args.older_than_days}d",
              file=sys.stderr)
        for r in reports:
            print(
                f"  {r['path']}: {r['kept']} kept, {r['dropped']} dropped "
                f"({r['status']})",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    sys.exit(cli())
