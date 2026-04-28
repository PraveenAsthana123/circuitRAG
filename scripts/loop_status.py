#!/usr/bin/env python3
"""Loop status — one-shot "is everything fine?" report.

Reads:
  * advisor.db    (events + council_runs + memory patterns)
  * .loop/watcher.log
  * .loop/council_runs.log
  * .loop/last_drill_outcome.json
  * .loop/replay_council.log (if present)

Prints structured key:value lines so operators can grep / awk
without parsing JSON. Use --json for machine-readable output.

Designed for operator's "morning check" workflow:

  $ python3 scripts/loop_status.py
  loop_state: HEALTHY
  last_commit_verdict: APPROVE  (rule_fired=6)
  drill_status_age_s: 240  (FRESH)
  drill_outcome: green  (38/38)
  events_total: 6
  events_pr_review: 6
  council_runs_total: 5
  council_runs_pending: 1   # events without a council_run row
  last_council_outcome: ok
  last_council_duration_s: 94.7
  watcher_recent_rejects: 0
  ollama: active
  ollama_models: 15

Exit codes:
  0  HEALTHY (everything green)
  1  WARNING (recent REJECTs, stale drill status, etc.)
  2  ERROR (advisor.db missing, daemon down)

Per Phase 5I + ADR-014.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ADVISOR_DB = REPO / "advisor.db"
LOOP_DIR = REPO / ".loop"
WATCHER_LOG = LOOP_DIR / "watcher.log"
COUNCIL_LOG = LOOP_DIR / "council_runs.log"
DRILL_STATUS = LOOP_DIR / "last_drill_outcome.json"
REPLAY_LOG = LOOP_DIR / "replay_council.log"

STALE_AFTER_SECS = 600  # match pre-commit hook default


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _read_log_tail(path: Path, limit: int = 50) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text().splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _query_db(sql: str, params: tuple = ()) -> list[tuple]:
    if not ADVISOR_DB.exists():
        return []
    try:
        with sqlite3.connect(str(ADVISOR_DB)) as conn:
            return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []


def _ollama_active() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "ollama"],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip() == "active"
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


def _ollama_model_count() -> int:
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5,
        )
        # First line is header; count remaining
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        return max(0, len(lines) - 1)
    except (FileNotFoundError, subprocess.SubprocessError):
        return -1


def collect_status() -> dict:
    """Gather all status into a single dict."""
    status: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    warnings: list[str] = []
    errors: list[str] = []

    # advisor.db state
    if not ADVISOR_DB.exists():
        errors.append("advisor.db missing — bootstrap not run?")
        status["events_total"] = 0
        status["council_runs_total"] = 0
        status["events_pr_review"] = 0
        status["council_runs_pending"] = 0
    else:
        events_rows = _query_db(
            "SELECT COUNT(*), event_type FROM advisor_events GROUP BY event_type"
        )
        status["events_total"] = sum(c for c, _ in events_rows)
        status["events_pr_review"] = next(
            (c for c, t in events_rows if t == "pr_review"), 0,
        )
        status["council_runs_total"] = (
            _query_db("SELECT COUNT(*) FROM advisor_council_runs")[0][0]
            if _query_db("SELECT COUNT(*) FROM advisor_council_runs") else 0
        )
        # Pending = events WITHOUT a council_run row (LEFT JOIN trick)
        pending = _query_db(
            "SELECT COUNT(*) FROM advisor_events e "
            "LEFT JOIN advisor_council_runs c ON c.event_id = e.id "
            "WHERE e.event_type = 'pr_review' AND c.id IS NULL"
        )
        status["council_runs_pending"] = pending[0][0] if pending else 0

    # Drill status
    drill = _read_json(DRILL_STATUS)
    if drill is None:
        warnings.append("drill status missing — pre-commit hook not active?")
        status["drill_status_age_s"] = -1
        status["drill_outcome"] = "unknown"
    else:
        try:
            ts = datetime.fromisoformat(drill["timestamp"])
            now = datetime.now(timezone.utc)
            age = int((now - ts).total_seconds())
        except (KeyError, ValueError):
            age = -1
        status["drill_status_age_s"] = age
        if age > STALE_AFTER_SECS:
            warnings.append(f"drill status stale ({age}s)")
        failed = drill.get("failed_drills") or []
        total = drill.get("total_drills", 0)
        status["drill_outcome"] = "green" if not failed else "FAILED"
        status["drill_passed"] = total - len(failed)
        status["drill_total"] = total
        if failed:
            status["drill_failed_names"] = failed
            warnings.append(f"{len(failed)} drill(s) failing: {failed[:3]}")

    # Watcher log
    verdicts = _read_log_tail(WATCHER_LOG)
    if verdicts:
        latest = verdicts[-1]
        status["last_commit_verdict"] = latest.get("verdict", "?")
        status["last_commit_rule_fired"] = latest.get("rule_fired", 0)
        # Recent REJECTs (last 10 verdicts)
        recent = verdicts[-10:]
        status["watcher_recent_rejects"] = sum(
            1 for v in recent if v.get("verdict") == "REJECT"
        )
        if status["watcher_recent_rejects"] > 0:
            warnings.append(
                f"{status['watcher_recent_rejects']} REJECTs in last 10 commits"
            )
        status["watcher_log_entries"] = len(verdicts)
    else:
        status["last_commit_verdict"] = "none"
        status["watcher_recent_rejects"] = 0
        status["watcher_log_entries"] = 0

    # Council log
    councils = _read_log_tail(COUNCIL_LOG)
    if councils:
        latest = councils[-1]
        status["last_council_fired"] = latest.get("fired", False)
        status["last_council_filtered"] = latest.get("filtered", False)
        status["last_council_risk"] = latest.get("risk_level") or "-"
        status["last_council_duration_s"] = latest.get("duration_s", 0)
        status["council_log_entries"] = len(councils)
    else:
        status["council_log_entries"] = 0

    # Ollama
    status["ollama"] = "active" if _ollama_active() else "inactive"
    if status["ollama"] != "active":
        warnings.append("Ollama daemon not active — council won't fire")
    model_count = _ollama_model_count()
    if model_count >= 0:
        status["ollama_models"] = model_count

    # Roll up
    if errors:
        status["loop_state"] = "ERROR"
        status["errors"] = errors
    elif warnings:
        status["loop_state"] = "WARNING"
        status["warnings"] = warnings
    else:
        status["loop_state"] = "HEALTHY"

    return status


def render_text(status: dict) -> str:
    """Operator-friendly key:value output."""
    state = status["loop_state"]
    color = {"HEALTHY": "\033[32m", "WARNING": "\033[33m",
             "ERROR": "\033[31m"}.get(state, "")
    reset = "\033[0m" if color else ""
    lines = [f"{color}loop_state: {state}{reset}"]
    skip_keys = {"loop_state", "warnings", "errors", "drill_failed_names"}
    for k in [
        "last_commit_verdict", "last_commit_rule_fired",
        "drill_status_age_s", "drill_outcome",
        "drill_passed", "drill_total",
        "events_total", "events_pr_review",
        "council_runs_total", "council_runs_pending",
        "last_council_fired", "last_council_filtered",
        "last_council_risk", "last_council_duration_s",
        "watcher_recent_rejects", "watcher_log_entries",
        "council_log_entries",
        "ollama", "ollama_models",
    ]:
        if k in status:
            lines.append(f"  {k}: {status[k]}")
    if "warnings" in status:
        lines.append("")
        lines.append("Warnings:")
        for w in status["warnings"]:
            lines.append(f"  - {w}")
    if "errors" in status:
        lines.append("")
        lines.append("Errors:")
        for e in status["errors"]:
            lines.append(f"  - {e}")
    if "drill_failed_names" in status:
        lines.append("")
        lines.append("Failing drills:")
        for d in status["drill_failed_names"]:
            lines.append(f"  - {d}")
    return "\n".join(lines)


def cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="machine-readable JSON output")
    args = parser.parse_args()
    status = collect_status()
    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(render_text(status))
    return {"HEALTHY": 0, "WARNING": 1, "ERROR": 2}.get(
        status["loop_state"], 2,
    )


if __name__ == "__main__":
    sys.exit(cli())
