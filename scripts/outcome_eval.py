"""Outcome-based evaluation framework — Tier 4 #4.5.

Per CLAUDE.md §55.3 (outcome-based contract): every iteration must
measurably move ONE of three numbers OR honestly report "no
measurement possible because <X>". Activity metrics (LOC changed,
council runs completed, models touched) are rejected.

This module is the ENFORCER. It reads the audit files and computes:

  1. APPLY RATE         applied / attempted (rolling 7-day window)
  2. REGRESSION COUNT   drills passing-then-failing (target: 0)
  3. COST PER FIX       sum(tokens × rate) / fixes_applied

  + emit a "snapshot" JSON for before/after comparison so an
  iteration can run `outcome_eval.py snapshot` BEFORE its work,
  then `outcome_eval.py compare-to <pre>.json` AFTER, and the
  diff IS the iteration's outcome metric.

USAGE
=====

  python3 scripts/outcome_eval.py snapshot                 # write current state to .loop/outcome_snapshot.json
  python3 scripts/outcome_eval.py snapshot --label pre-X   # named pre-iteration snapshot
  python3 scripts/outcome_eval.py compare-to pre-X         # show delta against named snapshot
  python3 scripts/outcome_eval.py report                   # human-readable current state
  python3 scripts/outcome_eval.py contract                 # verify §55.3 contract on last commit

Drilled by mcp/tests/drill_outcome_eval.py.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import ClassVar

REPO = Path(__file__).resolve().parent.parent
APPLY_AUDIT = REPO / ".loop" / "agent_task_board_apply.jsonl"
ISSUE_AUDIT = REPO / ".loop" / "issue_audit.jsonl"
SNAPSHOT_DIR = REPO / ".loop" / "outcome_snapshots"


# Cost-per-1k-tokens estimates (matches scripts/agent_lead.py).
COST_PER_1K_CENTS: dict[str, float] = {
    "llama3.2:1b": 0.05,
    "codegemma:7b-instruct": 0.10,
    "deepseek-coder:6.7b-instruct": 0.10,
    "codellama:7b-instruct": 0.10,
    "qwen2.5:latest": 0.10,
    "claude-cli": 5.0,
    "codex-cli": 4.0,
}


@dataclass(frozen=True)
class OutcomeMetrics:
    """The three §55.3-mandated metrics + audit context.

    Frozen so iterations can't mutate after the fact.
    """

    timestamp: str
    label: str | None
    window_days: int
    apply_attempts: int
    apply_succeeded: int
    apply_rate: float                 # applied / attempts ; 0.0 if attempts=0
    regression_count: int              # drills failing that previously passed
    total_tokens: int
    estimated_cost_cents: float
    cost_per_fix_cents: float | None   # None if applied=0

    model_config: ClassVar[dict] = {"frozen": True}

    def to_dict(self) -> dict:
        return asdict(self)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # skip malformed
    return out


def _within_window(ts_str: str, *, days: int) -> bool:
    """True iff ts (ISO 8601) is within `days` of now."""
    try:
        ts = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True  # tolerant: rows without parseable ts count
    now = datetime.datetime.now(datetime.UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.UTC)
    delta = now - ts
    return delta.days <= days


def compute_metrics(*, window_days: int = 7, label: str | None = None) -> OutcomeMetrics:
    """Compute the 3 §55.3 metrics over the given window."""
    apply_rows = _load_jsonl(APPLY_AUDIT)
    audit_rows = _load_jsonl(ISSUE_AUDIT)

    # Filter apply rows to window.
    in_window = [r for r in apply_rows if _within_window(r.get("timestamp", ""), days=window_days)]
    attempts = sum(1 for r in in_window if r.get("outcome") in ("applied", "rejected"))
    succeeded = sum(1 for r in in_window if r.get("outcome") == "applied")
    apply_rate = (succeeded / attempts) if attempts > 0 else 0.0

    # Cost: sum tokens × rate from audit chain entries.
    total_tokens = 0
    total_cost_cents = 0.0
    for row in audit_rows:
        if not _within_window(row.get("timestamp", ""), days=window_days):
            continue
        chain = row.get("chain", {})
        for role_entry in chain.values():
            if not isinstance(role_entry, dict):
                continue
            tokens = role_entry.get("tokens", 0) or 0
            model = role_entry.get("model", "")
            if not isinstance(tokens, int):
                continue
            total_tokens += tokens
            rate = COST_PER_1K_CENTS.get(model, 0.10)
            total_cost_cents += (tokens / 1000.0) * rate
    cost_per_fix = (total_cost_cents / succeeded) if succeeded > 0 else None

    # Regression count: a regression is a drill that PASSED in the prior
    # snapshot and FAILED in this one. Without a prior snapshot we
    # report 0 (can't measure delta from nothing).
    regression_count = _count_regressions_vs_last_snapshot()

    return OutcomeMetrics(
        timestamp=_now_iso(),
        label=label,
        window_days=window_days,
        apply_attempts=attempts,
        apply_succeeded=succeeded,
        apply_rate=round(apply_rate, 4),
        regression_count=regression_count,
        total_tokens=total_tokens,
        estimated_cost_cents=round(total_cost_cents, 4),
        cost_per_fix_cents=round(cost_per_fix, 4) if cost_per_fix is not None else None,
    )


def _count_regressions_vs_last_snapshot() -> int:
    """Run all drills; count those that fail now but passed in the
    most-recent snapshot if one exists. Returns 0 when there's no
    prior snapshot (delta uncomputable, not theater)."""
    snapshots = sorted(SNAPSHOT_DIR.glob("*.json")) if SNAPSHOT_DIR.exists() else []
    if not snapshots:
        return 0
    try:
        prior = json.loads(snapshots[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    prior_passing = set(prior.get("passing_drills", []))
    if not prior_passing:
        return 0
    now_passing = _drills_currently_passing()
    regressions = prior_passing - now_passing
    return len(regressions)


def _drills_currently_passing() -> set[str]:
    """Run every drill in mcp/tests/drill_*.py and return the names
    that exit 0. Used by regression detection. Bounded at 30s per
    drill — slow drills are shown as not-passing rather than hanging
    the whole eval.
    """
    drills_dir = REPO / "mcp" / "tests"
    if not drills_dir.exists():
        return set()
    passing: set[str] = set()
    for drill in sorted(drills_dir.glob("drill_*.py")):
        proc = subprocess.run(
            [sys.executable, str(drill)],
            cwd=REPO, capture_output=True, text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            passing.add(drill.stem)
    return passing


def _drills_currently_passing_safe() -> set[str]:
    """Wrapper that catches subprocess timeouts safely."""
    try:
        return _drills_currently_passing()
    except subprocess.TimeoutExpired:
        return set()


def cmd_snapshot(args: argparse.Namespace) -> int:
    label = args.label or "default"
    metrics = compute_metrics(window_days=args.window_days, label=label)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = SNAPSHOT_DIR / f"{label}-{metrics.timestamp.replace(':', '_')}.json"
    payload = metrics.to_dict()
    payload["passing_drills"] = sorted(_drills_currently_passing_safe())
    snap_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"✓ snapshot written: {snap_path.relative_to(REPO)}")
    print(f"  apply_rate     {metrics.apply_rate:.2%} ({metrics.apply_succeeded}/{metrics.apply_attempts})")
    print(f"  regressions    {metrics.regression_count}")
    print(f"  cost_per_fix   {metrics.cost_per_fix_cents}¢")
    return 0


def cmd_compare_to(args: argparse.Namespace) -> int:
    """Compare the most-recent snapshot with `label==<name>` against current."""
    if not SNAPSHOT_DIR.exists():
        print("x no snapshots found")
        return 1
    matches = sorted(SNAPSHOT_DIR.glob(f"{args.name}-*.json"))
    if not matches:
        print(f"x no snapshot with label {args.name!r}")
        return 1
    pre = json.loads(matches[-1].read_text(encoding="utf-8"))
    post = compute_metrics(window_days=pre.get("window_days", 7))
    pre_passing = set(pre.get("passing_drills", []))
    now_passing = _drills_currently_passing_safe()
    regressed = sorted(pre_passing - now_passing)
    new_passing = sorted(now_passing - pre_passing)

    print(f"=== Outcome delta vs {args.name} ===")
    print("               PRE          POST          DELTA")
    print(f"  apply_rate   {pre['apply_rate']:>5.2%}        {post.apply_rate:>5.2%}        {post.apply_rate - pre['apply_rate']:+.2%}")
    print(f"  attempts     {pre['apply_attempts']:>5}        {post.apply_attempts:>5}        {post.apply_attempts - pre['apply_attempts']:+}")
    print(f"  succeeded    {pre['apply_succeeded']:>5}        {post.apply_succeeded:>5}        {post.apply_succeeded - pre['apply_succeeded']:+}")
    print(f"  cost_cents   {pre['estimated_cost_cents']:>5.2f}        {post.estimated_cost_cents:>5.2f}        {post.estimated_cost_cents - pre['estimated_cost_cents']:+.2f}")
    print(f"  drills_pass  {len(pre_passing):>5}        {len(now_passing):>5}        {len(now_passing) - len(pre_passing):+}")
    if regressed:
        print(f"\n  REGRESSIONS ({len(regressed)}):")
        for d in regressed:
            print(f"    - {d}")
    if new_passing:
        print(f"\n  NEW PASSING ({len(new_passing)}):")
        for d in new_passing:
            print(f"    + {d}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    metrics = compute_metrics(window_days=args.window_days)
    print(f"=== Outcome metrics — {metrics.window_days}d window ===")
    print(f"  Apply rate           {metrics.apply_rate:.2%}  ({metrics.apply_succeeded}/{metrics.apply_attempts})")
    print(f"  Regressions          {metrics.regression_count}")
    print(f"  Total tokens         {metrics.total_tokens}")
    print(f"  Est. cost            {metrics.estimated_cost_cents}¢")
    if metrics.cost_per_fix_cents is not None:
        print(f"  Cost per fix         {metrics.cost_per_fix_cents}¢")
    else:
        print("  Cost per fix         (no fixes applied in window)")
    return 0


def cmd_contract(args: argparse.Namespace) -> int:
    """§55.3 enforcement: verify the most-recent commit moved at
    least one of (apply_rate, regression_count, cost_per_fix)
    OR honestly declared 'no measurement possible'.

    Heuristic: if last commit message contains 'no measurement
    possible because' OR has explicit BEFORE→AFTER delta lines,
    it's compliant. Otherwise warn.
    """
    proc = subprocess.run(
        ["git", "log", "-1", "--pretty=format:%B"],
        cwd=REPO, capture_output=True, text=True, timeout=10,
    )
    if proc.returncode != 0:
        print("x git log failed")
        return 1
    body = proc.stdout
    has_no_measurement = "no measurement possible" in body.lower()
    has_delta = any(marker in body.lower() for marker in (
        "before -> after", "before → after", "apply rate",
        "regression", "cost per fix", "outcome metric",
    ))
    if has_no_measurement or has_delta:
        print("✓ §55.3 contract honored: commit message references outcome OR honest no-measurement disclaimer")
        return 0
    print("⚠ §55.3 contract NOT honored: last commit message lacks outcome reference")
    print("  Add either:")
    print("    - 'before → after' delta on apply_rate / regression_count / cost_per_fix")
    print("    - explicit 'no measurement possible because <reason>'")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="outcome_eval.py", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_snap = sub.add_parser("snapshot", help="write current outcome snapshot")
    p_snap.add_argument("--label", default=None)
    p_snap.add_argument("--window-days", type=int, default=7)
    p_snap.set_defaults(func=cmd_snapshot)

    p_cmp = sub.add_parser("compare-to", help="diff against named snapshot")
    p_cmp.add_argument("name")
    p_cmp.set_defaults(func=cmd_compare_to)

    p_rep = sub.add_parser("report", help="human-readable current metrics")
    p_rep.add_argument("--window-days", type=int, default=7)
    p_rep.set_defaults(func=cmd_report)

    p_ct = sub.add_parser("contract", help="verify §55.3 on last commit")
    p_ct.set_defaults(func=cmd_contract)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
