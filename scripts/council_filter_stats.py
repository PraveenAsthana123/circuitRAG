#!/usr/bin/env python3
"""Group council_runs.log entries by outcome / filter reason / risk.

Operator question this script answers:
    "Of the last week's commits, how many fired the council, how many
     got filtered, and which filter is hottest?"

Reads .loop/council_runs.log (JSONL, append-only) and prints a
histogram-style breakdown:

  council outcomes (last 7d):
    total entries: 42
    fired:      18 (42.9%)
      risk=MEDIUM: 14
      risk=LOW:     3
      risk=HIGH:    1
    filtered:   24 (57.1%)
      doc_only:    11
      too_short:    8
      skip_token:   3
      legacy:       2

Phase 5K introduced canonical filter names (skip_token, too_short,
all_binary, doc_only, capture_error, empty_diff). Pre-5K log entries
used a different format and bucket as 'legacy'.

Operator usage:
    python3 scripts/council_filter_stats.py            # all-time
    python3 scripts/council_filter_stats.py --days 7   # last week
    python3 scripts/council_filter_stats.py --json     # for piping
    python3 scripts/council_filter_stats.py --log-path /custom/path

Exit code: 0 always (read-only). Stderr-only on log-file errors.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

REPO = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = REPO / ".loop" / "council_runs.log"

# Canonical filter names from git_capture.pr_review_filter_reason.
# Drill drill_filter_reason_granularity locks this set in git_capture;
# this script's parser must stay in sync.
KNOWN_FILTERS = {
    "capture_error", "empty_diff", "skip_token",
    "too_short", "all_binary", "doc_only",
}

log = logging.getLogger("council_filter_stats")


def parse_filter_reason(reason: str) -> str:
    """Extract a canonical filter bucket from a council_runs.log
    'reason' field.

    New format (Phase 5K+): 'filtered: skip_token (payload=242, ...)'
    Old format (pre-5K):    'filtered: payload_lines=242, files=3, ...'

    Returns one of KNOWN_FILTERS, 'legacy' (pre-5K format), or
    'unknown' (something we couldn't parse — shouldn't happen on
    well-formed logs but we don't crash either way)."""
    if not reason or not reason.startswith("filtered:"):
        return "unknown"
    body = reason[len("filtered:"):].lstrip()
    first = body.split(" ", 1)[0].rstrip(",;:")
    if first in KNOWN_FILTERS:
        return first
    if first.startswith("payload_lines="):
        return "legacy"
    return "unknown"


def load_entries(
    log_path: Path,
    days: int | None,
) -> Iterator[dict]:
    """Yield JSON entries from log_path. If days is set, only entries
    within that window. Malformed lines are skipped, not raised."""
    if not log_path.exists():
        return
    cutoff: datetime | None = None
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with log_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if cutoff is not None:
                ts = entry.get("timestamp")
                if ts:
                    try:
                        t = datetime.fromisoformat(ts)
                        if t.tzinfo is None:
                            t = t.replace(tzinfo=timezone.utc)
                        if t < cutoff:
                            continue
                    except ValueError:
                        # Bad timestamp — include the entry anyway.
                        # Don't silently lose data because of one malformed field.
                        pass
            yield entry


def summarize(log_path: Path, days: int | None) -> dict:
    """Roll up entries into the report shape consumed by render() / --json.

    Outcome classes (mutually exclusive — every entry lands in exactly one):
      * fired_by_risk      — fired=True, normal completion (LOW/MED/HIGH)
      * council_errors     — fired=True, reason starts 'council_error'
      * filtered_by_reason — filtered=True, bucketed by canonical filter
      * skipped_by_reason  — fired=False, filtered=False (operator opt-out
                             via --no-council, or advisor unwired). The
                             'no-council' path is intentional, not a bug.
    """
    fired_by_risk: dict[str, int] = {}
    filtered_by_reason: dict[str, int] = {}
    skipped_by_reason: dict[str, int] = {}
    council_errors = 0
    total = 0
    for entry in load_entries(log_path, days):
        total += 1
        fired = bool(entry.get("fired"))
        filtered = bool(entry.get("filtered"))
        reason = str(entry.get("reason", ""))
        if fired and not filtered:
            if reason.startswith("council_error"):
                council_errors += 1
            else:
                risk = entry.get("risk_level") or "UNKNOWN"
                fired_by_risk[risk] = fired_by_risk.get(risk, 0) + 1
        elif filtered:
            bucket = parse_filter_reason(reason)
            filtered_by_reason[bucket] = filtered_by_reason.get(bucket, 0) + 1
        else:
            # fired=False, filtered=False — operator/system opt-out path.
            # Bucket by leading reason word so 'no_council requested' and
            # 'no advisor wired' are distinguished.
            bucket = (reason.split(" ", 1)[0] if reason else "unknown")
            skipped_by_reason[bucket] = skipped_by_reason.get(bucket, 0) + 1

    return {
        "total": total,
        "fired_by_risk": fired_by_risk,
        "filtered_by_reason": filtered_by_reason,
        "skipped_by_reason": skipped_by_reason,
        "council_errors": council_errors,
        "window_days": days,
    }


def render(summary: dict) -> str:
    days = summary["window_days"]
    window = f"last {days}d" if days is not None else "all-time"
    lines = [f"council outcomes ({window}):",
             f"  total entries: {summary['total']}"]
    if summary["total"] == 0:
        lines.append("  (no entries — council hasn't run in this window)")
        return "\n".join(lines)
    fired_total = sum(summary["fired_by_risk"].values())
    filtered_total = sum(summary["filtered_by_reason"].values())
    skipped_total = sum(summary["skipped_by_reason"].values())
    pct = lambda n: f"{n / summary['total'] * 100:.1f}%"
    lines.append(f"  fired:    {fired_total:4d} ({pct(fired_total)})")
    for risk, n in sorted(summary["fired_by_risk"].items(),
                          key=lambda kv: -kv[1]):
        lines.append(f"    risk={risk}: {n}")
    lines.append(f"  filtered: {filtered_total:4d} ({pct(filtered_total)})")
    for name, n in sorted(summary["filtered_by_reason"].items(),
                          key=lambda kv: -kv[1]):
        lines.append(f"    {name}: {n}")
    if skipped_total:
        lines.append(f"  skipped:  {skipped_total:4d} ({pct(skipped_total)})")
        for name, n in sorted(summary["skipped_by_reason"].items(),
                              key=lambda kv: -kv[1]):
            lines.append(f"    {name}: {n}")
    if summary["council_errors"]:
        lines.append(f"  council errors: {summary['council_errors']}")
    return "\n".join(lines)


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-path", default=str(DEFAULT_LOG_PATH),
        help="path to council_runs.log",
    )
    parser.add_argument(
        "--days", type=int, default=None,
        help="only include entries within last N days (default: all)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit machine-readable JSON instead of text report",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    log_path = Path(args.log_path)
    if not log_path.exists():
        # Not an error — pre-bootstrap state. Render an empty report
        # so operators know the script ran.
        print(f"council_runs.log not found at {log_path}", file=sys.stderr)

    summary = summarize(log_path, args.days)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(cli())
