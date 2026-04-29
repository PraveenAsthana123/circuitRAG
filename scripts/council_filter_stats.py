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
import importlib.util
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


# Phase 5T: alert webhook formats. Three formats cover the common
# operator targets (Slack incoming-webhook, Discord webhook, generic
# JSON for everything else — pagerduty, custom routers, etc).
WEBHOOK_FORMATS = ("generic", "slack", "discord")
DEFAULT_WEBHOOK_TIMEOUT_S = 5.0  # don't stall CI on a hung webhook


def _normalize_fired(
    fired: list[tuple],
) -> list[dict]:
    """Normalize fired-alert tuples to a list of dicts with consistent
    fields. Single-window check_alerts returns (expr, observed);
    weekly check_alerts_weekly returns (expr, week, observed). The
    builder needs one shape, so flatten here."""
    out = []
    for item in fired:
        if len(item) == 2:
            expr, observed = item
            week = None
        else:  # 3-tuple from weekly path
            expr, week, observed = item
        out.append({
            "expr": expr.raw,
            "bucket": expr.bucket,
            "op": expr.op,
            "threshold": expr.threshold,
            "observed": observed,
            "week": week,
        })
    return out


def build_webhook_payload(
    fired_normalized: list[dict],
    context: dict,
    fmt: str,
) -> dict:
    """Build the JSON payload for a given format.

    fired_normalized: list of dicts from _normalize_fired
    context: extra fields shown alongside the alerts (log_path, weekly,
        weeks, alert_week_mode, etc) — passed straight through in
        generic; rendered into prose for slack/discord
    fmt: 'generic' | 'slack' | 'discord'
    """
    if fmt not in WEBHOOK_FORMATS:
        raise ValueError(f"webhook-format must be one of {WEBHOOK_FORMATS}; got {fmt!r}")

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = len(fired_normalized)

    if fmt == "generic":
        return {
            "fired_alerts": fired_normalized,
            "context": context,
            "timestamp": timestamp,
        }

    # Shared prose for slack + discord
    summary_line = (
        f"Council filter alert ({n} expression{'s' if n != 1 else ''} fired)"
    )
    detail_lines = []
    for f in fired_normalized:
        week_tag = f"week {f['week']} " if f.get("week") else ""
        detail_lines.append(
            f"`{f['expr']}` — {week_tag}observed {f['bucket']}={f['observed']:.3f} "
            f"vs threshold {f['threshold']}"
        )

    if fmt == "slack":
        # Slack incoming-webhook format with Block Kit blocks. The
        # 'text' field is the fallback for clients that don't render
        # blocks (mobile preview, screen readers).
        return {
            "text": summary_line,
            "blocks": [
                {"type": "header", "text": {
                    "type": "plain_text", "text": summary_line}},
                *[{"type": "section", "text": {
                    "type": "mrkdwn", "text": f"*ALERT:* {line}"}}
                  for line in detail_lines],
            ],
        }

    # discord
    # Discord webhooks accept embeds. Limit to 10 (Discord's hard cap).
    color = 13369855  # red-ish — matches the ALERT semantic
    return {
        "content": summary_line,
        "embeds": [
            {"title": f"ALERT: {f['expr']}",
             "description": (
                 f"{('week ' + f['week']) if f.get('week') else 'aggregate'}, "
                 f"observed {f['bucket']}={f['observed']:.3f} "
                 f"vs threshold {f['threshold']}"
             ),
             "color": color}
            for f in fired_normalized[:10]
        ],
    }


# Phase 5U: Prometheus textfile-collector format.
# Standard risk levels we emit zero-valued samples for so dashboards
# don't blank when a level is absent in the current window.
_PROM_RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "UNKNOWN")
# Filter buckets to emit even at zero — the canonical set + 'legacy' for
# pre-5K log entries. Drill verifies we don't accidentally drop a
# category when the histogram has no entries in it.
_PROM_FILTER_BUCKETS = tuple(sorted(KNOWN_FILTERS | {"legacy"}))


def _prom_escape_label(value: str) -> str:
    """Escape a Prometheus label value per the exposition format spec.

    Order matters: backslash MUST be escaped first so it can't double-
    escape the others. Newline is `\\n`, quote is `\\\"`, backslash is
    `\\\\`. Everything else is raw."""
    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )


def render_prometheus(summary: dict) -> str:
    """Emit summary as Prometheus textfile-collector format.

    Conventions:
      * One blank line between metrics (textfile parsers tolerate it).
      * Every metric has HELP + TYPE preceding samples.
      * Zero-valued samples are emitted for known buckets so Grafana
        panels don't blank out when a category has no entries in the
        current window.
      * 'gauge' type — these are point-in-time counts of historical
        events; gauge is correct for windowed reads of an append log.
    """
    out: list[str] = []

    out.append("# HELP council_filter_total Total council_runs.log entries observed.")
    out.append("# TYPE council_filter_total gauge")
    out.append(f"council_filter_total {int(summary.get('total', 0))}")
    out.append("")

    fired_by_risk = summary.get("fired_by_risk", {})
    out.append("# HELP council_filter_fired Successful council fires by risk level.")
    out.append("# TYPE council_filter_fired gauge")
    # Emit zeros for every standard risk; merge with any non-standard
    # risks the data carries (sorted for deterministic output).
    seen_risks = set(fired_by_risk.keys()) | set(_PROM_RISK_LEVELS)
    for risk in sorted(seen_risks):
        n = int(fired_by_risk.get(risk, 0))
        out.append(f'council_filter_fired{{risk="{_prom_escape_label(risk)}"}} {n}')
    out.append("")

    filtered_by_reason = summary.get("filtered_by_reason", {})
    out.append("# HELP council_filter_filtered Filtered (skipped) entries by canonical filter name.")
    out.append("# TYPE council_filter_filtered gauge")
    seen_filters = set(filtered_by_reason.keys()) | set(_PROM_FILTER_BUCKETS)
    for reason in sorted(seen_filters):
        n = int(filtered_by_reason.get(reason, 0))
        out.append(f'council_filter_filtered{{reason="{_prom_escape_label(reason)}"}} {n}')
    out.append("")

    skipped_by_reason = summary.get("skipped_by_reason", {})
    # Skipped buckets are open-ended (any leading word of the reason),
    # so we emit only what we actually saw rather than padding zeros.
    out.append("# HELP council_filter_skipped Operator-opt-out entries by reason.")
    out.append("# TYPE council_filter_skipped gauge")
    if skipped_by_reason:
        for reason in sorted(skipped_by_reason.keys()):
            n = int(skipped_by_reason[reason])
            out.append(f'council_filter_skipped{{reason="{_prom_escape_label(reason)}"}} {n}')
    else:
        # No samples → leave the HELP/TYPE only. Prom format permits this.
        pass
    out.append("")

    out.append("# HELP council_filter_council_errors Council errors (fired but errored).")
    out.append("# TYPE council_filter_council_errors gauge")
    out.append(f"council_filter_council_errors {int(summary.get('council_errors', 0))}")

    # Trailing newline — node_exporter's textfile parser is lenient,
    # but Prometheus format strictly requires LF-terminated final line.
    return "\n".join(out) + "\n"


def render_prometheus_weekly(weekly: dict) -> str:
    """Emit per-week prom samples — same metrics as render_prometheus,
    each with an extra `week` label.

    Conventions:
      * Metric NAMES match the single-window output (council_filter_total,
        _fired, _filtered, _skipped, _council_errors). Operators can roll
        up across weeks with `sum without (week) (council_filter_filtered)`.
      * Zero-padding for KNOWN_FILTERS + standard risks happens PER WEEK
        that has entries. Weeks with no entries don't appear at all
        (would create phantom data points in Grafana).
      * 'unparseable' rows: we emit them under week="unparseable" so
        operators can see the count and decide whether to fix the
        upstream timestamp source.
      * Output rows are deterministic-sorted: newest week first, then
        risk/reason alphabetical inside each week.
    """
    out: list[str] = []

    rows = weekly.get("rows", [])
    if not rows:
        # Empty — emit only the metadata blocks so the file is still
        # scrapable and dashboards don't 404.
        for metric, help_text in [
            ("council_filter_total", "Total council_runs.log entries by ISO week."),
            ("council_filter_fired", "Successful council fires by week + risk level."),
            ("council_filter_filtered", "Filtered entries by week + canonical filter."),
            ("council_filter_skipped", "Operator-opt-out entries by week + reason."),
            ("council_filter_council_errors", "Council errors by week."),
        ]:
            out.append(f"# HELP {metric} {help_text}")
            out.append(f"# TYPE {metric} gauge")
            out.append("")
        return "\n".join(out) + "\n"

    # ── total ──
    out.append("# HELP council_filter_total Total council_runs.log entries by ISO week.")
    out.append("# TYPE council_filter_total gauge")
    for r in rows:
        week_lbl = _prom_escape_label(r["week"])
        out.append(f'council_filter_total{{week="{week_lbl}"}} {int(r.get("total", 0))}')
    out.append("")

    # ── fired by risk ──
    out.append("# HELP council_filter_fired Successful council fires by week + risk level.")
    out.append("# TYPE council_filter_fired gauge")
    for r in rows:
        week_lbl = _prom_escape_label(r["week"])
        risks = r.get("fired_by_risk", {})
        seen = set(risks.keys()) | set(_PROM_RISK_LEVELS)
        for risk in sorted(seen):
            n = int(risks.get(risk, 0))
            risk_lbl = _prom_escape_label(risk)
            out.append(
                f'council_filter_fired{{week="{week_lbl}",risk="{risk_lbl}"}} {n}'
            )
    out.append("")

    # ── filtered by reason ──
    out.append("# HELP council_filter_filtered Filtered entries by week + canonical filter.")
    out.append("# TYPE council_filter_filtered gauge")
    for r in rows:
        week_lbl = _prom_escape_label(r["week"])
        reasons = r.get("filtered_by_reason", {})
        seen = set(reasons.keys()) | set(_PROM_FILTER_BUCKETS)
        for reason in sorted(seen):
            n = int(reasons.get(reason, 0))
            reason_lbl = _prom_escape_label(reason)
            out.append(
                f'council_filter_filtered{{week="{week_lbl}",reason="{reason_lbl}"}} {n}'
            )
    out.append("")

    # ── skipped by reason (open-ended; observed-only, no zero pad) ──
    out.append("# HELP council_filter_skipped Operator-opt-out entries by week + reason.")
    out.append("# TYPE council_filter_skipped gauge")
    for r in rows:
        week_lbl = _prom_escape_label(r["week"])
        reasons = r.get("skipped_by_reason", {})
        for reason in sorted(reasons.keys()):
            n = int(reasons[reason])
            reason_lbl = _prom_escape_label(reason)
            out.append(
                f'council_filter_skipped{{week="{week_lbl}",reason="{reason_lbl}"}} {n}'
            )
    out.append("")

    # ── council_errors ──
    out.append("# HELP council_filter_council_errors Council errors by week.")
    out.append("# TYPE council_filter_council_errors gauge")
    for r in rows:
        week_lbl = _prom_escape_label(r["week"])
        n = int(r.get("council_errors", 0))
        out.append(f'council_filter_council_errors{{week="{week_lbl}"}} {n}')

    return "\n".join(out) + "\n"


def render_prometheus_snapshots(snapshots: list[dict]) -> str:
    """Emit date-keyed prom samples from a list of daily snapshot rows
    (the shape produced by scripts/council_stats_snapshot.py).

    Each row has its own classification roll-up already (fired_by_risk,
    filtered_by_reason, skipped_by_reason, council_errors). We don't
    re-classify — we just project.

    Conventions match render_prometheus_weekly:
      * Same metric NAMES as single-window output
      * Zero-padding for KNOWN_FILTERS + standard risks PER DATE that
        has a snapshot row (no phantom-padding for absent dates).
      * Skipped buckets stay observed-only (no canonical set).
      * Date label is the snapshot's ISO date string (YYYY-MM-DD).
    """
    out: list[str] = []

    if not snapshots:
        # Empty — emit only metadata so dashboards don't 404
        for metric, help_text in [
            ("council_filter_total", "Total council_runs.log entries by snapshot date."),
            ("council_filter_fired", "Successful council fires by date + risk level."),
            ("council_filter_filtered", "Filtered entries by date + canonical filter."),
            ("council_filter_skipped", "Operator-opt-out entries by date + reason."),
            ("council_filter_council_errors", "Council errors by date."),
        ]:
            out.append(f"# HELP {metric} {help_text}")
            out.append(f"# TYPE {metric} gauge")
            out.append("")
        return "\n".join(out) + "\n"

    # ── total ──
    out.append("# HELP council_filter_total Total council_runs.log entries by snapshot date.")
    out.append("# TYPE council_filter_total gauge")
    for snap in snapshots:
        date_lbl = _prom_escape_label(str(snap.get("date", "")))
        out.append(f'council_filter_total{{date="{date_lbl}"}} {int(snap.get("total", 0))}')
    out.append("")

    # ── fired by risk ──
    out.append("# HELP council_filter_fired Successful council fires by date + risk level.")
    out.append("# TYPE council_filter_fired gauge")
    for snap in snapshots:
        date_lbl = _prom_escape_label(str(snap.get("date", "")))
        risks = snap.get("fired_by_risk", {})
        seen = set(risks.keys()) | set(_PROM_RISK_LEVELS)
        for risk in sorted(seen):
            n = int(risks.get(risk, 0))
            risk_lbl = _prom_escape_label(risk)
            out.append(
                f'council_filter_fired{{date="{date_lbl}",risk="{risk_lbl}"}} {n}'
            )
    out.append("")

    # ── filtered by reason ──
    out.append("# HELP council_filter_filtered Filtered entries by date + canonical filter.")
    out.append("# TYPE council_filter_filtered gauge")
    for snap in snapshots:
        date_lbl = _prom_escape_label(str(snap.get("date", "")))
        reasons = snap.get("filtered_by_reason", {})
        seen = set(reasons.keys()) | set(_PROM_FILTER_BUCKETS)
        for reason in sorted(seen):
            n = int(reasons.get(reason, 0))
            reason_lbl = _prom_escape_label(reason)
            out.append(
                f'council_filter_filtered{{date="{date_lbl}",reason="{reason_lbl}"}} {n}'
            )
    out.append("")

    # ── skipped (open-ended; observed-only) ──
    out.append("# HELP council_filter_skipped Operator-opt-out entries by date + reason.")
    out.append("# TYPE council_filter_skipped gauge")
    for snap in snapshots:
        date_lbl = _prom_escape_label(str(snap.get("date", "")))
        reasons = snap.get("skipped_by_reason", {})
        for reason in sorted(reasons.keys()):
            n = int(reasons[reason])
            reason_lbl = _prom_escape_label(reason)
            out.append(
                f'council_filter_skipped{{date="{date_lbl}",reason="{reason_lbl}"}} {n}'
            )
    out.append("")

    # ── council_errors ──
    out.append("# HELP council_filter_council_errors Council errors by date.")
    out.append("# TYPE council_filter_council_errors gauge")
    for snap in snapshots:
        date_lbl = _prom_escape_label(str(snap.get("date", "")))
        n = int(snap.get("council_errors", 0))
        out.append(f'council_filter_council_errors{{date="{date_lbl}"}} {n}')

    return "\n".join(out) + "\n"


def _load_read_snapshots():
    """Lazily load council_stats_snapshot.read_snapshots — single
    source of truth for dedup-by-date logic. importlib keeps this
    file standalone (no package-level coupling)."""
    p = Path(__file__).resolve().parent / "council_stats_snapshot.py"
    spec = importlib.util.spec_from_file_location("_snap_for_prom", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.read_snapshots


def write_prometheus_atomic(path: Path, content: str) -> None:
    """Write `content` to `path` atomically: write `<path>.tmp`, then
    rename. node_exporter's textfile collector has a known race where
    it reads a partially-written file mid-write; atomic rename avoids
    that. POSIX rename is atomic within a single filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


def post_webhook(
    url: str,
    payload: dict,
    timeout_s: float = DEFAULT_WEBHOOK_TIMEOUT_S,
) -> tuple[bool, str]:
    """Best-effort POST. Returns (success, error_msg).

    Never raises — all network exceptions captured as error_msg.
    Webhook failures must NOT change the script's exit code; the
    alerts already fired (exit 1), and a notification miss shouldn't
    flip the verdict. Operators discover the miss via stderr."""
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            status = resp.status
            if 200 <= status < 300:
                return (True, f"HTTP {status}")
            return (False, f"HTTP {status}")
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace").strip()
        except OSError:
            body = ""
        msg = f"HTTP {exc.code}: {exc.reason}"
        if body:
            msg += f" — {body[:200]}"
        return (False, msg)
    except URLError as exc:
        reason = str(exc.reason)
        return (False, f"URLError: {reason} (host={Request(url).host})")
    except (OSError, ValueError) as exc:
        return (False, f"{type(exc).__name__}: {exc}")


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
    parser.add_argument(
        "--webhook", default=os.environ.get("COUNCIL_STATS_WEBHOOK"),
        metavar="URL",
        help="POST fired alerts to this webhook URL (or env COUNCIL_STATS_WEBHOOK). "
             "Best-effort: webhook failure does NOT change the exit code.",
    )
    parser.add_argument(
        "--webhook-format", choices=WEBHOOK_FORMATS, default="generic",
        help="payload shape (default: generic JSON). slack uses Block Kit; "
             "discord uses embeds.",
    )
    parser.add_argument(
        "--prometheus", action="store_true",
        help="emit Prometheus textfile-collector format instead of "
             "text/JSON. Combine with --prometheus-out to write atomically.",
    )
    parser.add_argument(
        "--prometheus-out", default=None, metavar="PATH",
        help="write prometheus output to PATH (atomic via tmp+rename). "
             "Use with cron/node_exporter textfile collector.",
    )
    parser.add_argument(
        "--from-snapshot", action="store_true",
        help="with --prometheus, read .loop/council_stats_daily.jsonl "
             "(written by council_stats_snapshot.py) and emit date-keyed "
             "samples — long-term history that survives log rotation.",
    )
    parser.add_argument(
        "--snapshot-source", default=None, metavar="PATH",
        help="override snapshot file path (default: .loop/council_stats_daily.jsonl). "
             "Only meaningful with --from-snapshot.",
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

    def _maybe_post_webhook(fired_tuples: list[tuple], context: dict) -> None:
        """If --webhook is set and any alert fired, POST best-effort.
        Logs success/failure to stderr; never changes exit code."""
        if not args.webhook or not fired_tuples:
            return
        normalized = _normalize_fired(fired_tuples)
        try:
            payload = build_webhook_payload(normalized, context, args.webhook_format)
        except ValueError as exc:
            print(f"webhook: payload build failed: {exc}", file=sys.stderr)
            return
        ok, msg = post_webhook(args.webhook, payload)
        if ok:
            print(f"webhook: posted {len(normalized)} alert(s) "
                  f"({args.webhook_format}) → {msg}", file=sys.stderr)
        else:
            print(f"webhook: POST failed ({msg}); alerts still fired",
                  file=sys.stderr)

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    log_path = Path(args.log_path)
    if not log_path.exists():
        # Not an error — pre-bootstrap state. Render an empty report
        # so operators know the script ran.
        print(f"council_runs.log not found at {log_path}", file=sys.stderr)

    # Prometheus output mode — short-circuits the human-readable
    # report and the alert pipeline. Operators wanting alerts on prom
    # data should consume the metrics from a Grafana / Alertmanager
    # rule, not from this script's exit code.
    if args.prometheus:
        if args.json:
            print("--json ignored when --prometheus is set", file=sys.stderr)
        if alert_exprs:
            print("--alert-on ignored when --prometheus is set "
                  "(use Alertmanager on the metrics instead)",
                  file=sys.stderr)
        # Phase 5W: --from-snapshot is mutually exclusive with --weekly
        # because the snapshot already pre-aggregates per UTC date —
        # adding a week label on top would double-key the data.
        if args.from_snapshot and args.weekly:
            print("--from-snapshot is mutually exclusive with --weekly "
                  "(snapshot is already per-day; pick one lens)",
                  file=sys.stderr)
            return 1
        if args.snapshot_source and not args.from_snapshot:
            print("--snapshot-source has no effect without --from-snapshot",
                  file=sys.stderr)

        if args.from_snapshot:
            # Phase 5W: read snapshots and emit date-keyed samples.
            snap_path = Path(args.snapshot_source) if args.snapshot_source \
                else REPO / ".loop" / "council_stats_daily.jsonl"
            read_snapshots = _load_read_snapshots()
            snapshots = read_snapshots(snap_path)
            prom_text = render_prometheus_snapshots(snapshots)
        elif args.weekly:
            # Phase 5V: per-week labels. Same metric NAMES as the
            # single-window output so dashboards can roll up via
            # `sum without (week) (council_filter_filtered)`.
            weekly = summarize_by_week(log_path, args.weeks)
            prom_text = render_prometheus_weekly(weekly)
        else:
            summary = summarize(log_path, args.days)
            prom_text = render_prometheus(summary)

        if args.prometheus_out:
            write_prometheus_atomic(Path(args.prometheus_out), prom_text)
            print(f"prometheus: wrote {args.prometheus_out}", file=sys.stderr)
        else:
            sys.stdout.write(prom_text)
        return 0

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
                _maybe_post_webhook(fired, {
                    "log_path": str(log_path),
                    "weekly": True,
                    "weeks": args.weeks,
                    "alert_week_mode": args.alert_week_mode,
                })
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
            _maybe_post_webhook(fired, {
                "log_path": str(log_path),
                "weekly": False,
                "days": args.days,
            })
            return 1
        print(f"alerts: {len(alert_exprs)} expression(s) all passed",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(cli())
