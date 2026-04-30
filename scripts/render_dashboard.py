#!/usr/bin/env python3
"""Render a self-contained HTML dashboard for the Sidecar Advisor.

Reads:
  * advisor.db (Phase 1A events + Phase 2E council_runs)
  * .loop/watcher.log    (Phase 4B verdicts)
  * .loop/council_runs.log (Phase 2A2 capture-and-review log)

Writes a static HTML page to stdout. Operator pipes wherever:

    python3 scripts/render_dashboard.py > .loop/dashboard.html
    xdg-open .loop/dashboard.html

  Or refresh + serve:
    while sleep 30; do
      python3 scripts/render_dashboard.py > .loop/dashboard.html
    done

Pre-approved alternative to a Next.js UI in services/frontend/
(which is gated per §1 row 18 of NEXT_POLICY). Same data, no
scope extension needed.

Sections rendered:
  * Stats cards (total events, useful, not_useful, rated_pct)
  * Recent events table (last 20)
  * Recent verdicts table (last 20 lines from watcher.log)
  * Recent council runs (last 20 lines from council_runs.log)
  * Memory patterns ranked by use_count
"""
from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO / "advisor.db"
DEFAULT_WATCHER_LOG = REPO / ".loop" / "watcher.log"
DEFAULT_COUNCIL_LOG = REPO / ".loop" / "council_runs.log"


def _read_recent_events(db_path: Path, limit: int = 20) -> list[dict]:
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, created_at, event_type, source, "
                "model_used, advisor_output, user_rating, duration_s "
                "FROM advisor_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error:
        return []


def _read_stats(db_path: Path) -> dict:
    if not db_path.exists():
        return {"total_events": 0, "useful": 0, "not_useful": 0, "rated_pct": 0.0,
                "council_runs_total": 0, "patterns_total": 0}
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM advisor_events"
            ).fetchone()["n"]
            useful = conn.execute(
                "SELECT COUNT(*) AS n FROM advisor_events WHERE user_rating='useful'"
            ).fetchone()["n"]
            not_useful = conn.execute(
                "SELECT COUNT(*) AS n FROM advisor_events WHERE user_rating='not_useful'"
            ).fetchone()["n"]
            council_runs = 0
            try:
                council_runs = conn.execute(
                    "SELECT COUNT(*) AS n FROM advisor_council_runs"
                ).fetchone()["n"]
            except sqlite3.Error:
                pass
            patterns = 0
            try:
                patterns = conn.execute(
                    "SELECT COUNT(*) AS n FROM advisor_memory"
                ).fetchone()["n"]
            except sqlite3.Error:
                pass
            return {
                "total_events": total,
                "useful": useful,
                "not_useful": not_useful,
                "rated_pct": (
                    round(100 * (useful + not_useful) / total, 1)
                    if total else 0.0
                ),
                "council_runs_total": council_runs,
                "patterns_total": patterns,
            }
    except sqlite3.Error:
        return {"total_events": 0, "useful": 0, "not_useful": 0, "rated_pct": 0.0,
                "council_runs_total": 0, "patterns_total": 0}


def _read_log_tail(log_path: Path, limit: int = 20) -> list[dict]:
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text().strip().splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _read_patterns(db_path: Path, limit: int = 20) -> list[dict]:
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT pattern_kind, pattern_text, confidence, "
                "use_count, last_used_at FROM advisor_memory "
                "ORDER BY use_count DESC, confidence DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error:
        return []


def _e(s) -> str:
    """HTML-escape any value to prevent XSS from event content."""
    return html.escape(str(s)) if s is not None else ""


# ── Rendering ───────────────────────────────────────────────────
_CSS = """
body { font-family: ui-monospace, Menlo, Consolas, monospace;
       margin: 24px; background: #f6f7f9; color: #16162a; }
h1, h2 { color: #1b1b32; }
.cards { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }
.card { background: white; border-radius: 8px; padding: 16px;
        min-width: 140px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
.card .v { font-size: 28px; font-weight: bold; color: #16162a; }
.card .l { font-size: 12px; color: #666; text-transform: uppercase; }
table { width: 100%; border-collapse: collapse; background: white;
        border-radius: 8px; overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,.1); margin-bottom: 24px; }
th, td { text-align: left; padding: 8px 12px; font-size: 13px; }
th { background: #16162a; color: white; }
tr:nth-child(even) { background: #f6f7f9; }
.verdict-APPROVE { color: #2d8a2d; font-weight: bold; }
.verdict-HOLD    { color: #d68900; font-weight: bold; }
.verdict-REJECT  { color: #c43a3a; font-weight: bold; }
.risk-LOW    { color: #2d8a2d; }
.risk-MEDIUM { color: #d68900; }
.risk-HIGH   { color: #c43a3a; }
.note { font-size: 12px; color: #666; margin-top: 4px; }
.empty { color: #999; font-style: italic; padding: 12px; }
"""


def render_html(
    *,
    db_path: Path = DEFAULT_DB,
    watcher_log_path: Path = DEFAULT_WATCHER_LOG,
    council_log_path: Path = DEFAULT_COUNCIL_LOG,
) -> str:
    stats = _read_stats(db_path)
    events = _read_recent_events(db_path)
    verdicts = _read_log_tail(watcher_log_path)
    council_logs = _read_log_tail(council_log_path)
    patterns = _read_patterns(db_path)

    rendered_at = datetime.now(UTC).isoformat(timespec="seconds")

    parts: list[str] = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'>",
        "<title>Sidecar Advisor Dashboard</title>",
        f"<style>{_CSS}</style>",
        "</head><body>",
        "<h1>Sidecar Advisor Dashboard</h1>",
        f"<p class='note'>Rendered at {_e(rendered_at)} from "
        f"<code>{_e(db_path)}</code></p>",

        # Stats cards
        "<div class='cards'>",
        f"<div class='card'><div class='v'>{stats['total_events']}</div>"
        f"<div class='l'>Total events</div></div>",
        f"<div class='card'><div class='v'>{stats['useful']}</div>"
        f"<div class='l'>Useful</div></div>",
        f"<div class='card'><div class='v'>{stats['not_useful']}</div>"
        f"<div class='l'>Not useful</div></div>",
        f"<div class='card'><div class='v'>{stats['rated_pct']}%</div>"
        f"<div class='l'>Rated %</div></div>",
        f"<div class='card'><div class='v'>{stats['council_runs_total']}</div>"
        f"<div class='l'>Council runs</div></div>",
        f"<div class='card'><div class='v'>{stats['patterns_total']}</div>"
        f"<div class='l'>Memory patterns</div></div>",
        "</div>",
    ]

    # Recent events
    parts.append("<h2>Recent events</h2>")
    if not events:
        parts.append("<div class='empty'>No events yet.</div>")
    else:
        parts.append(
            "<table><thead><tr><th>id</th><th>created_at</th>"
            "<th>event_type</th><th>source</th><th>model_used</th>"
            "<th>rating</th><th>summary</th></tr></thead><tbody>"
        )
        for e in events:
            summary = ""
            if e.get("advisor_output"):
                try:
                    parsed = json.loads(e["advisor_output"])
                    summary = (parsed.get("summary") or "")[:80]
                except json.JSONDecodeError:
                    summary = "(unparsed advisor_output)"
            parts.append(
                f"<tr><td>{_e(e['id'])}</td>"
                f"<td>{_e(e['created_at'])}</td>"
                f"<td>{_e(e['event_type'])}</td>"
                f"<td>{_e(e['source'])}</td>"
                f"<td>{_e(e.get('model_used'))}</td>"
                f"<td>{_e(e.get('user_rating') or '-')}</td>"
                f"<td>{_e(summary)}</td></tr>"
            )
        parts.append("</tbody></table>")

    # Recent verdicts
    parts.append("<h2>Recent verdicts (.loop/watcher.log)</h2>")
    if not verdicts:
        parts.append("<div class='empty'>No watcher.log entries.</div>")
    else:
        parts.append(
            "<table><thead><tr><th>timestamp</th><th>commit_sha</th>"
            "<th>verdict</th><th>rule</th><th>reason</th></tr></thead><tbody>"
        )
        for v in reversed(verdicts):
            verdict = v.get("verdict", "")
            parts.append(
                f"<tr><td>{_e(v.get('timestamp'))}</td>"
                f"<td><code>{_e(v.get('commit_sha'))}</code></td>"
                f"<td class='verdict-{_e(verdict)}'>{_e(verdict)}</td>"
                f"<td>{_e(v.get('rule_fired'))}</td>"
                f"<td>{_e(v.get('reason'))}</td></tr>"
            )
        parts.append("</tbody></table>")

    # Recent council runs
    parts.append("<h2>Recent council runs (.loop/council_runs.log)</h2>")
    if not council_logs:
        parts.append("<div class='empty'>No council_runs.log entries.</div>")
    else:
        parts.append(
            "<table><thead><tr><th>timestamp</th><th>fired</th>"
            "<th>filtered</th><th>risk</th><th>files</th>"
            "<th>reason</th></tr></thead><tbody>"
        )
        for c in reversed(council_logs):
            risk = c.get("risk_level", "")
            files = c.get("files") or []
            files_summary = ", ".join(files[:3])
            if len(files) > 3:
                files_summary += f" (+{len(files) - 3} more)"
            parts.append(
                f"<tr><td>{_e(c.get('timestamp'))}</td>"
                f"<td>{_e(c.get('fired'))}</td>"
                f"<td>{_e(c.get('filtered'))}</td>"
                f"<td class='risk-{_e(risk)}'>{_e(risk or '-')}</td>"
                f"<td>{_e(files_summary)}</td>"
                f"<td>{_e(c.get('reason'))}</td></tr>"
            )
        parts.append("</tbody></table>")

    # Memory patterns
    parts.append("<h2>Memory patterns (top by use_count)</h2>")
    if not patterns:
        parts.append("<div class='empty'>No distilled patterns yet.</div>")
    else:
        parts.append(
            "<table><thead><tr><th>kind</th><th>text</th>"
            "<th>confidence</th><th>use_count</th>"
            "<th>last_used_at</th></tr></thead><tbody>"
        )
        for p in patterns:
            parts.append(
                f"<tr><td>{_e(p['pattern_kind'])}</td>"
                f"<td>{_e(p['pattern_text'])}</td>"
                f"<td>{_e(p['confidence'])}</td>"
                f"<td>{_e(p['use_count'])}</td>"
                f"<td>{_e(p.get('last_used_at') or '-')}</td></tr>"
            )
        parts.append("</tbody></table>")

    parts.append("</body></html>")
    return "\n".join(parts)


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--watcher-log", default=str(DEFAULT_WATCHER_LOG))
    parser.add_argument("--council-log", default=str(DEFAULT_COUNCIL_LOG))
    args = parser.parse_args()
    print(render_html(
        db_path=Path(args.db),
        watcher_log_path=Path(args.watcher_log),
        council_log_path=Path(args.council_log),
    ))
    return 0


if __name__ == "__main__":
    sys.exit(cli())
