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

Exit code: 0 by default (read-only).
              1 if any --alert-on EXPR matched (CI/cron failure hook).

Alert mode (Phase 5O):
    --alert-on <bucket><op><value>     can repeat; any match → exit 1

  bucket: filter name (skip_token, too_short, all_binary, doc_only,
          capture_error, empty_diff, legacy)
          OR meta-bucket (fired, filtered, skipped, council_errors)
  op:     >  >=  <  <=  =  !=
  value:  fraction 0.0-1.0 (interpreted as share of total entries)

Examples:
    --alert-on too_short>0.5      # too_short rate above 50%
    --alert-on filtered>0.8       # overall filter rate above 80%
    --alert-on fired<0.3          # fire rate below 30% (tuning broken?)
    --alert-on skip_token>0.2     # skip-token over-use (cost discipline)
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
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

# Phase 5O alert expression grammar.
# Meta-buckets sum the canonical filters / outcome classes and let
# operators write business-level alerts ("alert when filter rate > 80%")
# instead of having to enumerate every filter name.
META_BUCKETS = {"fired", "filtered", "skipped", "council_errors"}
# 'legacy' is a synthetic bucket for pre-5K log entries — not in
# KNOWN_FILTERS but valid in alert expressions for completeness.
ALERT_BUCKETS = KNOWN_FILTERS | META_BUCKETS | {"legacy", "unknown"}
# Order matters: longer ops first so '>=' isn't matched as '>'.
_ALERT_OPS = (">=", "<=", "!=", ">", "<", "=")
_ALERT_RE = re.compile(
    r"^(?P<bucket>[a-zA-Z_]+)\s*"
    r"(?P<op>>=|<=|!=|>|<|=)\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*$"
)

log = logging.getLogger("council_filter_stats")


@dataclass(frozen=True)
class AlertExpr:
    """Parsed --alert-on expression."""
    bucket: str       # canonical filter name OR meta-bucket name
    op: str           # one of _ALERT_OPS
    threshold: float  # fraction-of-total (0.0..1.0)
    raw: str          # original CLI string for error messages

    def evaluate(self, summary: dict) -> tuple[bool, float]:
        """Return (fired, observed_fraction).

        observed_fraction is the bucket count / total. When total is 0,
        the alert NEVER fires (avoid divide-by-zero firing on empty logs)."""
        total = summary.get("total", 0)
        if total == 0:
            return (False, 0.0)
        n = self._bucket_count(summary)
        frac = n / total
        return (self._compare(frac), frac)

    def _bucket_count(self, summary: dict) -> int:
        if self.bucket in META_BUCKETS:
            if self.bucket == "fired":
                return sum(summary.get("fired_by_risk", {}).values())
            if self.bucket == "filtered":
                return sum(summary.get("filtered_by_reason", {}).values())
            if self.bucket == "skipped":
                return sum(summary.get("skipped_by_reason", {}).values())
            if self.bucket == "council_errors":
                return int(summary.get("council_errors", 0))
        # canonical filter name (or 'legacy' / 'unknown')
        return int(summary.get("filtered_by_reason", {}).get(self.bucket, 0))

    def _compare(self, observed: float) -> bool:
        t = self.threshold
        return {
            ">":  observed >  t,
            ">=": observed >= t,
            "<":  observed <  t,
            "<=": observed <= t,
            "=":  observed == t,
            "!=": observed != t,
        }[self.op]


def parse_alert_expr(s: str) -> AlertExpr:
    """Parse one --alert-on expression. Raises ValueError on bad form.

    Strictness: bucket must be a known name (canonical filter, meta-
    bucket, 'legacy', or 'unknown'). Threshold must be 0.0..1.0
    (fractions, not raw counts — keeps the alert language consistent
    across log volumes)."""
    m = _ALERT_RE.match(s)
    if not m:
        raise ValueError(
            f"alert expression must be '<bucket><op><number>'; got {s!r}"
        )
    bucket = m.group("bucket")
    op = m.group("op")
    try:
        threshold = float(m.group("value"))
    except ValueError as exc:
        raise ValueError(f"alert {s!r}: bad threshold") from exc
    if bucket not in ALERT_BUCKETS:
        valid = ", ".join(sorted(ALERT_BUCKETS))
        raise ValueError(
            f"alert {s!r}: unknown bucket {bucket!r}. Valid: {valid}"
        )
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(
            f"alert {s!r}: threshold {threshold} out of [0.0, 1.0]"
        )
    return AlertExpr(bucket=bucket, op=op, threshold=threshold, raw=s)


def check_alerts(summary: dict, exprs: list[AlertExpr]) -> list[tuple[AlertExpr, float]]:
    """Return list of (expr, observed_fraction) for every expression
    that fired. Empty list = all alerts passed."""
    fired = []
    for expr in exprs:
        is_fired, observed = expr.evaluate(summary)
        if is_fired:
            fired.append((expr, observed))
    return fired


# Phase 5R: per-week alert aggregation modes.
# `each`      = alert fires if ANY week breaches the threshold (strictest)
# `latest`    = check only the most recent week
# `aggregate` = roll up to single summary (= no-weekly behavior)
ALERT_WEEK_MODES = ("each", "latest", "aggregate")


def _aggregate_weekly_to_summary(weekly: dict) -> dict:
    """Collapse a weekly result back into a summarize()-shaped dict.
    Used by `aggregate` mode so alert evaluation runs against the
    same shape as single-window summarize()."""
    rolled = _empty_buckets()
    for row in weekly.get("rows", []):
        rolled["total"] += row.get("total", 0)
        for risk, n in row.get("fired_by_risk", {}).items():
            rolled["fired_by_risk"][risk] = rolled["fired_by_risk"].get(risk, 0) + n
        for name, n in row.get("filtered_by_reason", {}).items():
            rolled["filtered_by_reason"][name] = rolled["filtered_by_reason"].get(name, 0) + n
        for name, n in row.get("skipped_by_reason", {}).items():
            rolled["skipped_by_reason"][name] = rolled["skipped_by_reason"].get(name, 0) + n
        rolled["council_errors"] += row.get("council_errors", 0)
    return rolled


def check_alerts_weekly(
    weekly: dict,
    exprs: list[AlertExpr],
    mode: str = "each",
) -> list[tuple[AlertExpr, str | None, float]]:
    """Per-week alert evaluation with aggregation choice. Returns a list
    of (expr, week_label_or_None, observed_fraction) for every fired
    alert.

    For `each`: week_label is the breaching week's ISO key (multiple
        entries possible per expr — one per breached week).
    For `latest`: week_label is the latest dated week's ISO key.
    For `aggregate`: week_label is None (the alert is on the rollup,
        not any individual week).

    `unparseable` rows are skipped in `each` and `latest` (we can't
    locate them on a timeline) but DO contribute to `aggregate`
    (the data exists; it just lacks a week tag).

    Empty / no-data weeks never fire (divide-by-zero safe — same
    contract as check_alerts())."""
    if mode not in ALERT_WEEK_MODES:
        raise ValueError(
            f"alert-week-mode must be one of {ALERT_WEEK_MODES}; got {mode!r}"
        )
    rows = weekly.get("rows", [])
    fired: list[tuple[AlertExpr, str | None, float]] = []

    if mode == "aggregate":
        rolled = _aggregate_weekly_to_summary(weekly)
        for expr in exprs:
            is_fired, observed = expr.evaluate(rolled)
            if is_fired:
                fired.append((expr, None, observed))
        return fired

    # 'each' and 'latest' both work per-row; differ only in WHICH rows.
    dated = [r for r in rows if r.get("week") != "unparseable"]
    if mode == "latest":
        # rows are already newest-first per summarize_by_week; latest = first dated
        candidates = dated[:1]
    else:  # each
        candidates = dated

    for row in candidates:
        # Build a summarize()-shaped dict from this row so AlertExpr.evaluate
        # works without modification. The roll-up keys (fired/filtered/skipped)
        # are already populated by summarize_by_week.
        row_summary = {
            "total": row.get("total", 0),
            "fired_by_risk": row.get("fired_by_risk", {}),
            "filtered_by_reason": row.get("filtered_by_reason", {}),
            "skipped_by_reason": row.get("skipped_by_reason", {}),
            "council_errors": row.get("council_errors", 0),
        }
        for expr in exprs:
            is_fired, observed = expr.evaluate(row_summary)
            if is_fired:
                fired.append((expr, row.get("week"), observed))
    return fired


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


def classify_entry(entry: dict) -> tuple[str, str | None]:
    """Classify a council_runs.log entry into one of four mutually-exclusive
    outcome classes. Returns (klass, sub_bucket).

    klass values (stable contract — drill_council_filter_stats step 4
    locks them):
        "fired"          — sub_bucket = risk_level (LOW/MEDIUM/HIGH/UNKNOWN)
        "council_error"  — sub_bucket = None
        "filtered"       — sub_bucket = canonical filter name (skip_token, ...)
        "skipped"        — sub_bucket = leading word of reason (no_council, ...)

    Shared by summarize() (single window) and summarize_by_week() (per
    ISO week). Without this helper the per-entry invariant could drift
    between the two views — a refactor adding a class to one path
    would silently leave the other behind.
    """
    fired = bool(entry.get("fired"))
    filtered = bool(entry.get("filtered"))
    reason = str(entry.get("reason", ""))
    if fired and not filtered:
        if reason.startswith("council_error"):
            return ("council_error", None)
        risk = entry.get("risk_level") or "UNKNOWN"
        return ("fired", str(risk))
    if filtered:
        return ("filtered", parse_filter_reason(reason))
    # fired=False, filtered=False — operator/system opt-out path.
    bucket = (reason.split(" ", 1)[0] if reason else "unknown")
    return ("skipped", bucket)


def _empty_buckets() -> dict:
    """Per-window/per-week zero state."""
    return {
        "total": 0,
        "fired_by_risk": {},
        "filtered_by_reason": {},
        "skipped_by_reason": {},
        "council_errors": 0,
    }


def _accumulate(buckets: dict, klass: str, sub_bucket: str | None) -> None:
    """Update buckets in place from one classified entry."""
    buckets["total"] += 1
    if klass == "fired":
        buckets["fired_by_risk"][sub_bucket] = (
            buckets["fired_by_risk"].get(sub_bucket, 0) + 1
        )
    elif klass == "council_error":
        buckets["council_errors"] += 1
    elif klass == "filtered":
        buckets["filtered_by_reason"][sub_bucket] = (
            buckets["filtered_by_reason"].get(sub_bucket, 0) + 1
        )
    elif klass == "skipped":
        buckets["skipped_by_reason"][sub_bucket] = (
            buckets["skipped_by_reason"].get(sub_bucket, 0) + 1
        )
    # An unknown klass would be silently dropped here. classify_entry
    # never returns one, but a future refactor that adds a class without
    # updating this dispatch would lose entries — caught by the
    # drill's total-equals-sum invariant.


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
    buckets = _empty_buckets()
    for entry in load_entries(log_path, days):
        klass, sub_bucket = classify_entry(entry)
        _accumulate(buckets, klass, sub_bucket)
    return {**buckets, "window_days": days}


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


def iso_week_key(timestamp_str: str) -> str | None:
    """Return ISO-week key (e.g. '2026-W17') from an ISO timestamp,
    or None if unparseable. Use isocalendar()'s OWN year — not the
    calendar year — because ISO weeks straddle Jan 1 (a date in
    early Jan 2026 may belong to ISO week 2025-W53)."""
    if not timestamp_str:
        return None
    try:
        t = datetime.fromisoformat(timestamp_str)
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    iso_year, iso_week, _ = t.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def summarize_by_week(log_path: Path, weeks: int | None) -> dict:
    """Group entries by ISO week. Newest week first. If `weeks` is set,
    keep only the last N ISO weeks present in the data (NOT the last N
    calendar weeks — sparse weeks skipped, latest N populated weeks
    returned).

    Returns:
        {
          "rows": [
              {"week": "2026-W17", "total": 8,
               "fired": 5, "filtered": 1, "skipped": 2, "errors": 0,
               "fired_by_risk": {...}, "filtered_by_reason": {...},
               "skipped_by_reason": {...}, "council_errors": 0},
              ...
          ],
          "weeks_window": weeks,
        }
    Entries with unparseable timestamps land in week='unparseable' so
    they're visible — operators can see HOW MANY but the row sorts
    apart from real weeks."""
    by_week: dict[str, dict] = {}
    for entry in load_entries(log_path, days=None):
        week = iso_week_key(str(entry.get("timestamp", ""))) or "unparseable"
        bucket = by_week.setdefault(week, {**_empty_buckets(), "week": week})
        klass, sub_bucket = classify_entry(entry)
        _accumulate(bucket, klass, sub_bucket)

    # Sort newest first. 'unparseable' sorts last regardless.
    def _sort_key(row: dict) -> tuple[int, str]:
        return (0 if row["week"] != "unparseable" else 1, row["week"])

    rows = sorted(by_week.values(), key=_sort_key)
    # Reverse only the dated rows; pin 'unparseable' at the end.
    dated = [r for r in rows if r["week"] != "unparseable"]
    unparseable = [r for r in rows if r["week"] == "unparseable"]
    dated.sort(key=lambda r: r["week"], reverse=True)
    rows = dated + unparseable

    if weeks is not None:
        # Keep only the last N DATED rows (always preserve unparseable
        # if present so operators still see the count).
        rows = dated[:weeks] + unparseable

    # Roll-up counts per row for table rendering.
    for r in rows:
        r["fired"] = sum(r["fired_by_risk"].values())
        r["filtered"] = sum(r["filtered_by_reason"].values())
        r["skipped"] = sum(r["skipped_by_reason"].values())
        r["errors"] = r["council_errors"]

    return {"rows": rows, "weeks_window": weeks}


def render_weekly(weekly: dict) -> str:
    """Fixed-width table of one row per ISO week, newest first."""
    rows = weekly["rows"]
    weeks = weekly["weeks_window"]
    header = (f"council outcomes by week"
              f"{f' (last {weeks} weeks)' if weeks else ''}:")
    if not rows:
        return f"{header}\n  (no entries)"
    lines = [
        header,
        f"  {'week':<14} {'total':>6} {'fired':>6} {'filtered':>9} "
        f"{'skipped':>8} {'errors':>7}",
        f"  {'-' * 14} {'-' * 6} {'-' * 6} {'-' * 9} {'-' * 8} {'-' * 7}",
    ]
    for r in rows:
        lines.append(
            f"  {r['week']:<14} {r['total']:>6} {r['fired']:>6} "
            f"{r['filtered']:>9} {r['skipped']:>8} {r['errors']:>7}"
        )
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
        "--weekly", action="store_true",
        help="group entries by ISO week (one row per week, newest first)",
    )
    parser.add_argument(
        "--weeks", type=int, default=None,
        help="with --weekly, keep only the last N DATED weeks "
             "(unparseable timestamps always shown if present)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit machine-readable JSON instead of text report",
    )
    parser.add_argument(
        "--alert-on", action="append", default=[],
        metavar="EXPR",
        help="alert expression like 'too_short>0.5'; can repeat. "
             "Any match → exit 1 (CI/cron failure hook). "
             "Buckets: filter names, fired, filtered, skipped, "
             "council_errors. Threshold is a 0.0–1.0 fraction.",
    )
    parser.add_argument(
        "--alert-week-mode", choices=ALERT_WEEK_MODES, default="each",
        help="when --weekly is used, choose the aggregation: "
             "'each' (alert if any week breaches; strictest, default), "
             "'latest' (most recent week only), "
             "'aggregate' (rollup; same as no --weekly).",
    )
    args = parser.parse_args()

    # Parse every --alert-on up front so a typo fails fast (before
    # we walk the log file). argparse would have surfaced a
    # parse_known errors here, but we get a cleaner error message
    # by failing in our own parser.
    alert_exprs: list[AlertExpr] = []
    for raw in args.alert_on:
        try:
            alert_exprs.append(parse_alert_expr(raw))
        except ValueError as exc:
            print(f"--alert-on: {exc}", file=sys.stderr)
            return 1

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    log_path = Path(args.log_path)
    if not log_path.exists():
        # Not an error — pre-bootstrap state. Render an empty report
        # so operators know the script ran.
        print(f"council_runs.log not found at {log_path}", file=sys.stderr)

    if args.weekly:
        if args.days is not None:
            print("--days is ignored with --weekly; use --weeks N",
                  file=sys.stderr)
        weekly = summarize_by_week(log_path, args.weeks)
        if args.json:
            print(json.dumps(weekly, indent=2))
        else:
            print(render_weekly(weekly))

        # Phase 5R: per-week alert evaluation. Three modes share the
        # same exit/print contract as single-window — report first,
        # alerts second, exit 1 if any fire.
        if alert_exprs:
            fired = check_alerts_weekly(weekly, alert_exprs, args.alert_week_mode)
            if fired:
                for expr, week, observed in fired:
                    week_tag = f"week {week} " if week else ""
                    print(
                        f"ALERT: {expr.raw} "
                        f"({week_tag}{expr.bucket}={observed:.3f} "
                        f"vs threshold {expr.threshold})",
                        file=sys.stderr,
                    )
                return 1
            print(
                f"alerts: {len(alert_exprs)} expression(s) all passed "
                f"(mode={args.alert_week_mode})",
                file=sys.stderr,
            )
        return 0

    summary = summarize(log_path, args.days)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(render(summary))

    # ── Alert evaluation ─────────────────────────────────────────
    # Run AFTER the report so operators always see the breakdown,
    # even when an alert is going to fire and exit nonzero. The
    # report is the data; the alert is the verdict.
    if alert_exprs:
        fired = check_alerts(summary, alert_exprs)
        if fired:
            for expr, observed in fired:
                print(
                    f"ALERT: {expr.raw} "
                    f"(observed {expr.bucket}={observed:.3f} "
                    f"vs threshold {expr.threshold})",
                    file=sys.stderr,
                )
            return 1
        print(f"alerts: {len(alert_exprs)} expression(s) all passed",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(cli())
