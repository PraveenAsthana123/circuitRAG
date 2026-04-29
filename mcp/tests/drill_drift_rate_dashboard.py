#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: drift-rate dashboard from .loop/watcher.log.

ADR-014 declares the LoopWatcher's verdict log as the safety net,
not the primary gate. Sweep-before-commit catches drift at iteration
time; the verdict log catches what slipped through. This drill
measures both states by parsing watcher.log:

  * APPROVE rule 6 = drill_outcome was green at watcher read time
    (good — sweep was clean OR drift hadn't landed yet)
  * REJECT rule 1 = drill_outcome was FAILED at watcher read time
    (drift detected — could be sweep miss OR post-commit drift
    landed before watcher fired; the dashboard doesn't disambiguate)

The dashboard is an observability surface, not a gate that blames
either actor. Thresholds are floors below which the loop is
"under stress" and the operator should investigate; passing the
thresholds doesn't mean "everything is fine," only "no acute
meltdown signal."

Eight steps. Five negative assertions.

  1. POSITIVE: discover watcher.log entries (>= 50 floor — drill
     cannot trivially pass on a fresh checkout with empty log).
  2. NEGATIVE: overall APPROVE-rate (deduped by commit_sha,
     latest verdict per commit wins) >= MIN_APPROVE_RATE_OVERALL.
     A persistently low rate means the loop is stuck below the
     advisory floor — operator should investigate.
  3. NEGATIVE: recent APPROVE-rate (last RECENT_WINDOW unique
     commits) >= MIN_APPROVE_RATE_RECENT. Lower than overall is
     fine (catches transient drift); below the floor is a
     sustained meltdown signal.
  4. NEGATIVE: max consecutive REJECTs in the deduped chrono
     order <= MAX_CONSECUTIVE_REJECTS. 5+ in a row is a
     coordination meltdown (e.g., parallel-tool flooding faster
     than autonomous-loop can drain).
  5. NEGATIVE: every REJECT has rule_fired in {1, 2, 3, 4, 5}.
     rule_fired=6 means APPROVE; REJECT+rule_fired=6 = schema
     corruption.
  6. NEGATIVE: every entry has drill_outcome consistent with
     verdict+rule (REJECT rule 1 -> drill_outcome FAILED;
     APPROVE rule 6 -> drill_outcome green). Inconsistent rows =
     watcher log is lying.
  7. POSITIVE: emit verdict histogram (overall + recent +
     per-rule).
  8. POSITIVE: emit max consecutive REJECT streak + dashboard
     summary lines.

Run: python3 mcp/tests/drill_drift_rate_dashboard.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WATCHER_LOG = REPO / ".loop" / "watcher.log"

MIN_ENTRIES = 50
RECENT_WINDOW = 20  # last N unique commits
MIN_APPROVE_RATE_OVERALL = 0.60
MIN_APPROVE_RATE_RECENT = 0.50
# Floor matches observed historical max (Phase 7Q-7R cascade ran
# 5 consecutive REJECTs before the drift fix). Per ADR-015 ratchet
# pattern: future regressions to 6+ fire this assertion. Lower this
# number when the historical max is paid down (ratchet shrinkage).
MAX_CONSECUTIVE_REJECTS = 5

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
NC = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}{msg}{NC}")


def fail(msg: str) -> None:
    print(f"  {RED}x {msg}{NC}")
    raise SystemExit(1)


def step(title: str) -> None:
    print(f"\n{BOLD}-- {title} --{NC}")


def _load_entries() -> list[dict]:
    """Parse watcher.log, skipping malformed lines (per ADR-019:
    bad timestamp / malformed JSON tolerated, not crashed)."""
    if not WATCHER_LOG.exists():
        return []
    out = []
    for ln in WATCHER_LOG.read_text(errors="ignore").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            # Per ADR-019: malformed JSON line skipped, not fatal.
            continue
    return out


def _dedupe_latest(entries: list[dict]) -> list[dict]:
    """For commits that appear multiple times in watcher.log
    (post-commit hook re-runs / repeated triggers), keep only the
    LAST entry per commit_sha. Order preserved by commit's first
    appearance."""
    seen: dict[str, int] = {}
    for i, e in enumerate(entries):
        sha = e.get("commit_sha")
        if not sha:
            continue
        seen[sha] = i  # overwrites — keeps latest index
    # Sort indices by their first-appearance order (we already
    # iterate the file in order; so sorting by latest-index gives
    # chronological-by-first-appearance).
    indices = sorted(seen.values())
    return [entries[i] for i in indices]


def _max_consecutive_rejects(entries: list[dict]) -> int:
    """Longest run of consecutive REJECT verdicts."""
    cur = 0
    best = 0
    for e in entries:
        if e.get("verdict") == "REJECT":
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def main() -> int:
    step("1. POSITIVE: discover watcher.log entries (>= MIN_ENTRIES floor)")
    if not WATCHER_LOG.exists():
        fail(
            f"{WATCHER_LOG.relative_to(REPO)} missing — drill needs a "
            "populated verdict log to compute drift-rate"
        )
    entries = _load_entries()
    if len(entries) < MIN_ENTRIES:
        fail(
            f"only {len(entries)} watcher.log entries; floor is "
            f"{MIN_ENTRIES}. Drill cannot meaningfully measure drift-"
            "rate on a fresh log."
        )
    deduped = _dedupe_latest(entries)
    ok(
        f"{len(entries)} raw entries; {len(deduped)} unique commits "
        f"after dedupe-by-commit_sha"
    )

    # Build verdict counts (deduped, latest-per-commit).
    overall_approve = sum(1 for e in deduped if e.get("verdict") == "APPROVE")
    overall_reject = sum(1 for e in deduped if e.get("verdict") == "REJECT")
    overall_rate = (
        overall_approve / len(deduped) if deduped else 0.0
    )

    step("2. NEGATIVE: overall APPROVE-rate >= MIN_APPROVE_RATE_OVERALL")
    if overall_rate < MIN_APPROVE_RATE_OVERALL:
        fail(
            f"overall APPROVE-rate={overall_rate:.1%} < "
            f"{MIN_APPROVE_RATE_OVERALL:.0%}. "
            f"({overall_approve} APPROVE / {overall_reject} REJECT / "
            f"{len(deduped)} commits). Loop is below advisory floor — "
            "operator should investigate sustained drift."
        )
    ok(
        f"overall APPROVE-rate={overall_rate:.1%} "
        f"({overall_approve}/{len(deduped)})"
    )

    step("3. NEGATIVE: recent APPROVE-rate >= MIN_APPROVE_RATE_RECENT")
    recent = deduped[-RECENT_WINDOW:]
    recent_approve = sum(1 for e in recent if e.get("verdict") == "APPROVE")
    recent_reject = sum(1 for e in recent if e.get("verdict") == "REJECT")
    recent_rate = recent_approve / len(recent) if recent else 0.0
    if recent_rate < MIN_APPROVE_RATE_RECENT:
        fail(
            f"recent APPROVE-rate (last {len(recent)} unique commits)="
            f"{recent_rate:.1%} < {MIN_APPROVE_RATE_RECENT:.0%}. "
            f"({recent_approve} APPROVE / {recent_reject} REJECT). "
            "Recent meltdown signal — investigate active iteration."
        )
    ok(
        f"recent APPROVE-rate (last {len(recent)})={recent_rate:.1%} "
        f"({recent_approve}/{len(recent)})"
    )

    step("4. NEGATIVE: max consecutive REJECTs <= MAX_CONSECUTIVE_REJECTS")
    max_streak = _max_consecutive_rejects(deduped)
    if max_streak > MAX_CONSECUTIVE_REJECTS:
        fail(
            f"max consecutive REJECT streak={max_streak} > "
            f"{MAX_CONSECUTIVE_REJECTS}. Sustained meltdown — operator "
            "should pause autonomous-loop and investigate."
        )
    ok(f"max consecutive REJECT streak={max_streak}")

    step("5. NEGATIVE: every REJECT has rule_fired in {1, 2, 3, 4, 5}")
    schema_violations: list[tuple[str, int]] = []
    for e in deduped:
        if e.get("verdict") != "REJECT":
            continue
        rule = e.get("rule_fired")
        if rule not in (1, 2, 3, 4, 5):
            schema_violations.append((e.get("commit_sha", "?")[:7], rule))
    if schema_violations:
        fail(
            f"{len(schema_violations)} REJECT entries with rule_fired "
            f"out-of-range: {schema_violations[:5]}. Schema corruption."
        )
    ok(f"all {overall_reject} REJECTs have valid rule_fired")

    step("6. NEGATIVE: drill_outcome consistent with verdict+rule")
    consistency_violations: list[tuple[str, str, int, str]] = []
    for e in deduped:
        sha = e.get("commit_sha", "?")[:7]
        verdict = e.get("verdict")
        rule = e.get("rule_fired")
        outcome = e.get("drill_outcome", "")
        if verdict == "APPROVE" and rule == 6 and outcome != "green":
            consistency_violations.append((sha, verdict, rule, outcome))
        elif verdict == "REJECT" and rule == 1 and outcome != "FAILED":
            consistency_violations.append((sha, verdict, rule, outcome))
    if consistency_violations:
        fail(
            f"{len(consistency_violations)} entries with inconsistent "
            f"drill_outcome: {consistency_violations[:3]}. Watcher log "
            "lying about drill state."
        )
    ok(
        f"all {len(deduped)} entries have drill_outcome consistent "
        "with verdict+rule"
    )

    step("7. POSITIVE: verdict histogram + per-rule breakdown")
    rule_breakdown: dict[tuple[str, int], int] = {}
    for e in deduped:
        key = (e.get("verdict", "?"), e.get("rule_fired", 0))
        rule_breakdown[key] = rule_breakdown.get(key, 0) + 1
    histogram = ", ".join(
        f"{v}+rule{r}={count}"
        for (v, r), count in sorted(rule_breakdown.items())
    )
    ok(f"overall: {histogram}")
    ok(
        f"recent ({len(recent)}): "
        f"APPROVE={recent_approve} REJECT={recent_reject} "
        f"rate={recent_rate:.1%}"
    )

    step("8. POSITIVE: dashboard summary")
    ok(
        f"DRIFT-RATE DASHBOARD: "
        f"overall={overall_rate:.1%}, recent={recent_rate:.1%}, "
        f"max-reject-streak={max_streak}, "
        f"floor={MIN_APPROVE_RATE_OVERALL:.0%}/{MIN_APPROVE_RATE_RECENT:.0%}"
    )
    if max_streak >= 3:
        ok(
            f"  (note: REJECT streak {max_streak} is informational; "
            "fail threshold is >{MAX_CONSECUTIVE_REJECTS})"
        )
    delta = recent_rate - overall_rate
    if delta > 0.05:
        ok(f"  trend: recent UP {delta:+.1%} vs overall (improving)")
    elif delta < -0.05:
        ok(f"  trend: recent DOWN {delta:+.1%} vs overall (regressing)")
    else:
        ok(f"  trend: stable ({delta:+.1%} delta)")

    print(f"\n{BOLD}{GREEN}{'=' * 50}{NC}")
    print(f"{BOLD}{GREEN}  ALL 8 DRIFT-RATE-DASHBOARD STEPS PASSED{NC}")
    print(f"{BOLD}{GREEN}  (5 negative assertions: 2, 3, 4, 5, 6){NC}")
    print(f"{BOLD}{GREEN}{'=' * 50}{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
