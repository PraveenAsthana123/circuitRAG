#!/usr/bin/env python3
"""Reflection engine — periodic self-critique of recent council decisions.

Per CLAUDE.md §44 (autonomous loop with reflection signals), §45.4 (no
checkbox flips without code), §47 (architecture: reflection as a separate
runtime concern from execution), §48 (AI explainability), §53 row 45
(continuous improvement: outcomes → drift signals → next iteration).

User's Environment State doc listed Reflection Engine as ❌ Missing
(P1). Iter-58 ships the scaffold:

    Read .loop/issue_audit.jsonl + .loop/issue_decisions.jsonl
    → compute drift signals (apply rate, hallucination rate,
      retry storm, latency p95, cost per fix)
    → emit a structured ReflectionReport that downstream consumers
      (council scheduler, dashboard) read to decide:
        - which lane is degrading?
        - which rule code keeps failing council?
        - is the outcome metric trending up or down?

CONTRACT
  reflect(audit_path, window_days, min_attempts) -> ReflectionReport

  ReflectionReport contains:
    - generated_at: UTC timestamp
    - window_days: lookback
    - total_attempts: int
    - apply_rate: float ∈ [0, 1]   (applied / attempted)
    - by_lane: {lane → {attempted, applied, apply_rate, p95_latency_s,
                        avg_tokens, regression_signal}}
    - by_rule_code: {rule → {attempted, applied, apply_rate}}
    - drift_signals: list[str] — human-readable findings (empty when
                                  the system is healthy)
    - recommended_actions: list[str] — what the next iteration should do
    - honesty_signal: one-line summary of overall state

Read-only. NEVER mutates. Never publishes. The output is the artifact;
the council scheduler / dashboard / next-iter planner is the consumer.

Run from CLI:
    python3 scripts/reflection_engine.py --window 7
    python3 scripts/reflection_engine.py --window 7 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOOP_DIR = REPO / ".loop"
DEFAULT_AUDIT = LOOP_DIR / "issue_audit.jsonl"
DEFAULT_DECISIONS = LOOP_DIR / "issue_decisions.jsonl"

# Drift thresholds — tuned conservatively. A signal fires only when the
# evidence is robust (min_attempts ≥ 5) so single-flake events don't
# trigger spurious recommendations.
APPLY_RATE_FLOOR = 0.30  # below this → quality concern
RETRY_STORM_THRESHOLD = 5  # repeats per id within window
LATENCY_P95_CONCERN_S = 60.0
APPLY_RATE_DEGRADATION = 0.20  # 20-pct drop vs prior window


@dataclass(frozen=True)
class LaneStats:
    lane: str
    attempted: int
    applied: int
    apply_rate: float
    p95_latency_s: float
    avg_tokens: float
    regression_signal: str  # "" when stable; non-empty describes drift


@dataclass(frozen=True)
class RuleStats:
    rule_code: str
    attempted: int
    applied: int
    apply_rate: float


@dataclass(frozen=True)
class ReflectionReport:
    generated_at: str  # ISO UTC
    window_days: int
    total_attempts: int
    applied: int
    apply_rate: float
    by_lane: dict[str, LaneStats] = field(default_factory=dict)
    by_rule_code: dict[str, RuleStats] = field(default_factory=dict)
    drift_signals: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    honesty_signal: str = ""


def _read_jsonl(path: Path, limit: int = 50000) -> list[dict]:
    """Read JSONL, tolerating malformed lines."""
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _within_window(row: dict, cutoff: datetime) -> bool:
    """Return True iff row.ts is within the window."""
    ts_str = row.get("ts") or ""
    if not ts_str:
        return False
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts >= cutoff


def _percentile(values: list[float], p: float) -> float:
    """p ∈ [0, 100]. Returns 0.0 for empty input."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_v) - 1)
    if f == c:
        return sorted_v[f]
    return sorted_v[f] + (sorted_v[c] - sorted_v[f]) * (k - f)


def _rule_code_from_id(issue_id: str) -> str:
    """Extract rule code from id like `ruff-E402-__init__.py-L579`."""
    if not issue_id:
        return "?"
    parts = issue_id.split("-")
    if len(parts) >= 2:
        # ruff-E402-... → 'E402'; bandit-B110-... → 'B110'
        return parts[1] if parts[1] else "?"
    return "?"


def reflect(
    *,
    audit_path: Path = DEFAULT_AUDIT,
    decisions_path: Path = DEFAULT_DECISIONS,
    window_days: int = 7,
    min_attempts: int = 5,
) -> ReflectionReport:
    """Build a ReflectionReport from the local audit + decisions JSONL.

    min_attempts: drift signals require this many attempts in a lane/rule
    before firing — prevents single-flake events from triggering spurious
    recommendations.
    """
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    audit = _read_jsonl(audit_path)
    decisions = _read_jsonl(decisions_path)

    # Filter to window
    audit = [r for r in audit if _within_window(r, cutoff)]
    decisions = [r for r in decisions if _within_window(r, cutoff)]

    # Build per-id outcome map: id → "applied" | "rejected" | other
    id_outcome: dict[str, str] = {}
    for d in decisions:
        rid = d.get("id") or d.get("issue_id") or ""
        outcome = d.get("outcome") or d.get("decision") or ""
        if rid:
            id_outcome[rid] = outcome

    # Aggregate by lane
    by_lane_raw: dict[str, dict] = defaultdict(
        lambda: {"attempted": 0, "applied": 0, "latencies": [], "tokens": []},
    )
    by_rule_raw: dict[str, dict] = defaultdict(
        lambda: {"attempted": 0, "applied": 0},
    )
    id_attempt_count: dict[str, int] = defaultdict(int)

    for row in audit:
        rid = row.get("id") or row.get("issue_id") or ""
        lane = row.get("lane") or "?"
        outcome = row.get("outcome") or ""
        latency = float(row.get("latency_s") or 0.0)
        tokens = int(row.get("tokens") or 0)

        # Lane-level rollup
        by_lane_raw[lane]["attempted"] += 1
        if outcome in ("applied", "fix_applied", "council_applied"):
            by_lane_raw[lane]["applied"] += 1
        # Cross-ref decision file for terminal outcome
        if rid in id_outcome and id_outcome[rid] in ("applied", "fix_applied"):
            by_lane_raw[lane]["applied"] += 1
        if latency > 0:
            by_lane_raw[lane]["latencies"].append(latency)
        if tokens > 0:
            by_lane_raw[lane]["tokens"].append(tokens)

        # Rule-level rollup
        rule = _rule_code_from_id(rid)
        if rule != "?":
            by_rule_raw[rule]["attempted"] += 1
            if outcome in ("applied", "fix_applied", "council_applied") or (
                rid in id_outcome
                and id_outcome[rid] in ("applied", "fix_applied")
            ):
                by_rule_raw[rule]["applied"] += 1

        if rid:
            id_attempt_count[rid] += 1

    # Materialize lane + rule stats with drift signals
    drift_signals: list[str] = []
    by_lane: dict[str, LaneStats] = {}
    for lane, stats in by_lane_raw.items():
        attempted = stats["attempted"]
        applied = min(stats["applied"], attempted)  # cap at attempted
        apply_rate = applied / attempted if attempted else 0.0
        p95 = _percentile(stats["latencies"], 95.0)
        avg_tokens = (
            sum(stats["tokens"]) / len(stats["tokens"]) if stats["tokens"] else 0.0
        )
        regression = ""
        if attempted >= min_attempts and apply_rate < APPLY_RATE_FLOOR:
            regression = (
                f"apply_rate {apply_rate:.1%} < floor {APPLY_RATE_FLOOR:.0%}"
            )
            drift_signals.append(f"lane '{lane}': {regression}")
        if attempted >= min_attempts and p95 > LATENCY_P95_CONCERN_S:
            latency_signal = f"p95 latency {p95:.1f}s > {LATENCY_P95_CONCERN_S:.0f}s"
            regression = (
                f"{regression}; {latency_signal}" if regression else latency_signal
            )
            drift_signals.append(f"lane '{lane}': {latency_signal}")
        by_lane[lane] = LaneStats(
            lane=lane,
            attempted=attempted,
            applied=applied,
            apply_rate=round(apply_rate, 4),
            p95_latency_s=round(p95, 2),
            avg_tokens=round(avg_tokens, 1),
            regression_signal=regression,
        )

    by_rule_code: dict[str, RuleStats] = {}
    for rule, stats in by_rule_raw.items():
        attempted = stats["attempted"]
        applied = min(stats["applied"], attempted)
        apply_rate = applied / attempted if attempted else 0.0
        if attempted >= min_attempts and apply_rate < APPLY_RATE_FLOOR:
            drift_signals.append(
                f"rule '{rule}': apply_rate {apply_rate:.1%} over "
                f"{attempted} attempts — council struggles with this code"
            )
        by_rule_code[rule] = RuleStats(
            rule_code=rule,
            attempted=attempted,
            applied=applied,
            apply_rate=round(apply_rate, 4),
        )

    # Retry-storm detection (any id attempted ≥ RETRY_STORM_THRESHOLD)
    storm_ids = [
        rid for rid, n in id_attempt_count.items() if n >= RETRY_STORM_THRESHOLD
    ]
    if storm_ids:
        drift_signals.append(
            f"retry storm: {len(storm_ids)} id(s) attempted "
            f"≥{RETRY_STORM_THRESHOLD} times — {storm_ids[:3]}"
        )

    # Total
    total_attempts = sum(s.attempted for s in by_lane.values())
    total_applied = sum(s.applied for s in by_lane.values())
    overall_rate = total_applied / total_attempts if total_attempts else 0.0

    # Recommended actions — derived from drift_signals
    recommended_actions: list[str] = []
    if drift_signals:
        recommended_actions.append(
            "Review the drift_signals; lanes / rules with apply_rate below "
            "the floor are next-iteration targets per §55.3 outcome contract."
        )
        if storm_ids:
            recommended_actions.append(
                f"Retry storm: route {storm_ids[:3]} to human-review queue "
                f"per §50.5.3 (don't keep retrying the same id without escalation)."
            )
    else:
        recommended_actions.append(
            "No drift detected this window — continue current cadence."
        )

    honesty = (
        f"{total_applied}/{total_attempts} applied "
        f"(apply_rate {overall_rate:.1%}); "
        f"{len(drift_signals)} drift signal(s) over {window_days}d window"
    )

    return ReflectionReport(
        generated_at=datetime.now(UTC).isoformat(),
        window_days=window_days,
        total_attempts=total_attempts,
        applied=total_applied,
        apply_rate=round(overall_rate, 4),
        by_lane=by_lane,
        by_rule_code=by_rule_code,
        drift_signals=drift_signals,
        recommended_actions=recommended_actions,
        honesty_signal=honesty,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--window", type=int, default=7,
        help="Lookback window in days (default: 7)",
    )
    parser.add_argument(
        "--min-attempts", type=int, default=5,
        help="Minimum attempts before drift signals fire (default: 5)",
    )
    parser.add_argument(
        "--audit", type=Path, default=DEFAULT_AUDIT,
        help=f"Path to audit JSONL (default: {DEFAULT_AUDIT.relative_to(REPO)})",
    )
    parser.add_argument(
        "--decisions", type=Path, default=DEFAULT_DECISIONS,
        help=f"Path to decisions JSONL (default: {DEFAULT_DECISIONS.relative_to(REPO)})",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit JSON report instead of human-readable summary",
    )
    args = parser.parse_args()

    report = reflect(
        audit_path=args.audit,
        decisions_path=args.decisions,
        window_days=args.window,
        min_attempts=args.min_attempts,
    )

    if args.json:
        # Convert dataclasses to dicts; nested LaneStats / RuleStats too
        out = asdict(report)
        # Normalize: by_lane / by_rule_code are dict[str, dataclass] →
        # asdict() already handles top-level; ensure inner shape is plain.
        print(json.dumps(out, indent=2, default=str))
        return 0

    # Human-readable
    print(f"Reflection Report — {report.generated_at}")
    print(f"  window: {report.window_days}d")
    print(f"  total attempts: {report.total_attempts}")
    print(f"  applied: {report.applied}")
    print(f"  apply_rate: {report.apply_rate:.1%}")
    print(f"  honesty: {report.honesty_signal}")
    print()
    if report.by_lane:
        print("by lane:")
        for lane, s in sorted(
            report.by_lane.items(), key=lambda kv: -kv[1].attempted,
        )[:10]:
            print(
                f"  {lane:35s}  attempts={s.attempted:3d}  "
                f"applied={s.applied:3d}  rate={s.apply_rate:.1%}  "
                f"p95_s={s.p95_latency_s:.1f}"
                f"{'  ⚠ ' + s.regression_signal if s.regression_signal else ''}"
            )
    print()
    if report.drift_signals:
        print("drift signals:")
        for signal in report.drift_signals[:10]:
            print(f"  - {signal}")
        print()
    if report.recommended_actions:
        print("recommended actions:")
        for action in report.recommended_actions:
            print(f"  - {action}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
