"""Stage-3 default-flip earned-check (per CLAUDE.md §56.3).

Per §56.3: "Stage-3 (default-flip) requires empirical eval (10+ real
cycles) showing parity with the original path. No flipping defaults
on speculation."

This script reads .loop/best_config_history.jsonl and decides whether
the best_config registry adapter has accumulated enough successful
empirical cycles to earn a Stage-3 default flip (BEST_CONFIG_LOADER_ENABLED=1
becomes the default for new operators).

The check is INFORMATIONAL — it never flips the default. It just gives
operators a deterministic answer to "is Stage-3 earned for this adapter?"

CONTRACT:
  - check(history_path, min_cycles=10, min_success_ratio=0.8) → EarnedReport
  - status() / is_available()
  - CLI: python3 scripts/stage3_earned_check.py [--min-cycles N]
  - Default-deny via STAGE3_EARNED_CHECK_ENABLED=1

ALGORITHM:
  1. Load all history rows
  2. Count promoted vs total (excluding skipped — they're env-state, not work)
  3. Verdict:
     - earned                — promoted >= min_cycles AND ratio >= ratio
                               AND distinct_winning_configs >= min_distinct
     - stable_single_winner  — meets cycles + ratio but only 1 distinct
                               config; eval set never varied → likely
                               overfitting, not generalization. Operator
                               must vary eval set or extend cycles before
                               trusting Stage-3 default-flip.
     - not_earned            — too few cycles
     - flapping              — promoted occurred but rejection rate too high
     - cold                  — no rows at all (loader never ran)

OPERATOR FLOW:
  Run quarterly:
    BEST_CONFIG_HISTORY_ENABLED=1 STAGE3_EARNED_CHECK_ENABLED=1 \\
      python3 scripts/stage3_earned_check.py
  → if earned, operator manually flips the default in code

§47 fail-safe: missing/malformed history → cold verdict, never raises.

COMPOSES WITH:
    scripts/best_config_history.py — provides load_history()
    scripts/promote_best_config.py — writes the rows we count
    docs/architecture/empirical-rag-config-loop.md — operator runbook
    §38 (governance), §47 (fail-safe), §56.3 (Stage-3 contract)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

STAGE3_EARNED_CHECK_ENABLED = os.getenv("STAGE3_EARNED_CHECK_ENABLED", "").strip() == "1"

DEFAULT_MIN_CYCLES = int(os.getenv("STAGE3_MIN_CYCLES", "10"))
DEFAULT_MIN_SUCCESS_RATIO = float(os.getenv("STAGE3_MIN_SUCCESS_RATIO", "0.8"))
# Diversity threshold — Stage-3 needs evidence that the empirical
# winner generalizes across DIFFERENT evals, not that it overfits to
# one fixed eval set. Default 2: at least 2 distinct configs must
# have won across the cycles. Operator can lower to 1 with
# STAGE3_MIN_DISTINCT=1 if they explicitly accept "stable single
# winner against fixed eval set" as sufficient.
DEFAULT_MIN_DISTINCT = int(os.getenv("STAGE3_MIN_DISTINCT", "2"))
DEFAULT_HISTORY_PATH = os.getenv(
    "BEST_CONFIG_HISTORY_PATH",
    ".loop/best_config_history.jsonl",
)


class Stage3EarnedCheckDisabled(RuntimeError):
    """Raised when force-required check is invoked but env unset."""


@dataclass
class EarnedReport:
    """Verdict on whether Stage-3 default-flip is earned."""
    verdict: str = "cold"  # earned | not_earned | flapping | cold
    rationale: str = ""
    decided_at_ts: float = 0.0
    total_attempts: int = 0
    promoted: int = 0
    rejected: int = 0
    skipped: int = 0
    success_ratio: float = 0.0
    min_cycles_required: int = 0
    min_success_ratio_required: float = 0.0
    min_distinct_required: int = 0
    distinct_winning_configs: int = 0
    earliest_ts: float = 0.0
    latest_ts: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_available() -> bool:
    """Stage-1 default-deny check."""
    return STAGE3_EARNED_CHECK_ENABLED


def status() -> dict[str, Any]:
    """Operator status surface."""
    return {
        "stage": "meta",
        "enabled_env": STAGE3_EARNED_CHECK_ENABLED,
        "available": is_available(),
        "thresholds": {
            "min_cycles": DEFAULT_MIN_CYCLES,
            "min_success_ratio": DEFAULT_MIN_SUCCESS_RATIO,
            "min_distinct": DEFAULT_MIN_DISTINCT,
        },
        "history_path": DEFAULT_HISTORY_PATH,
        "next_stage": (
            "Operator manually flips BEST_CONFIG_LOADER_ENABLED default "
            "to '1' in best_config_loader.py once verdict='earned'. "
            "Drill should be added to lock the post-flip contract."
        ),
    }


def _config_signature(config: dict[str, Any]) -> str:
    """Stable string key for a config — same convention as promote_best_config."""
    return (
        f"chunk={config.get('chunking_strategy', '?')}|"
        f"min_score={config.get('min_score', '?')}|"
        f"rerank={config.get('rerank_enabled', '?')}|"
        f"top_k={config.get('retrieval_top_k', config.get('top_k', '?'))}"
    )


def check(
    *,
    history_path: str | None = None,
    min_cycles: int | None = None,
    min_success_ratio: float | None = None,
    min_distinct: int | None = None,
) -> EarnedReport:
    """Apply the Stage-3-earned heuristic.

    Per §47 fail-safe: missing/malformed history → cold verdict, never raises.

    Default-deny: when STAGE3_EARNED_CHECK_ENABLED is unset, returns
    a cold report with rationale='disabled'.
    """
    decided_at = time.time()
    cycles = min_cycles if min_cycles is not None else DEFAULT_MIN_CYCLES
    ratio_threshold = (
        min_success_ratio
        if min_success_ratio is not None
        else DEFAULT_MIN_SUCCESS_RATIO
    )
    distinct_threshold = (
        min_distinct
        if min_distinct is not None
        else DEFAULT_MIN_DISTINCT
    )
    report = EarnedReport(
        decided_at_ts=decided_at,
        min_cycles_required=cycles,
        min_success_ratio_required=ratio_threshold,
        min_distinct_required=distinct_threshold,
    )

    if not is_available():
        report.verdict = "cold"
        report.rationale = "STAGE3_EARNED_CHECK_ENABLED unset"
        return report

    use_path = history_path or DEFAULT_HISTORY_PATH
    p = Path(use_path)
    if not p.exists():
        report.verdict = "cold"
        report.rationale = f"history file missing: {use_path}"
        return report

    rows: list[dict[str, Any]] = []
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as exc:
        report.verdict = "cold"
        report.rationale = f"history read failed: {exc}"
        return report

    if not rows:
        report.verdict = "cold"
        report.rationale = "history file empty"
        return report

    # Count by classification — same logic as best_config_history.summarize
    for r in rows:
        promoted_flag = bool(r.get("promoted", False))
        reason = str(r.get("reason", ""))
        if promoted_flag:
            report.promoted += 1
        elif "skipped" in reason.lower():
            report.skipped += 1
        else:
            report.rejected += 1

    report.total_attempts = len(rows)
    timestamps = [float(r.get("decided_at_ts", 0.0)) for r in rows]
    report.earliest_ts = min(timestamps) if timestamps else 0.0
    report.latest_ts = max(timestamps) if timestamps else 0.0

    # Real attempts = promoted + rejected (skipped is env-state, not work)
    real_attempts = report.promoted + report.rejected
    if real_attempts > 0:
        report.success_ratio = report.promoted / real_attempts

    # Distinct winning configs — diversity check. Stage-3 should be
    # earned by repeated promotion of MULTIPLE distinct winners
    # (proves the system isn't just stuck on one config).
    promoted_rows = [r for r in rows if bool(r.get("promoted", False))]
    distinct_sigs: set[str] = set()
    for r in promoted_rows:
        cfg = r.get("config") or {}
        if cfg:
            distinct_sigs.add(_config_signature(cfg))
        else:
            sig = r.get("raw_winner_signature", "")
            if sig:
                distinct_sigs.add(sig)
    report.distinct_winning_configs = len(distinct_sigs)

    # Verdict
    if report.promoted < cycles:
        report.verdict = "not_earned"
        report.rationale = (
            f"only {report.promoted} successful promotion(s); "
            f"need {cycles} per §56.3"
        )
    elif report.success_ratio < ratio_threshold:
        report.verdict = "flapping"
        report.rationale = (
            f"success_ratio={report.success_ratio:.2f} < "
            f"required={ratio_threshold:.2f}; gate is fighting the writer"
        )
    elif report.distinct_winning_configs < distinct_threshold:
        # Cycles + ratio met, but only ONE distinct config has won.
        # That's not generalization — that's overfitting to a fixed
        # eval set. Operator must vary the eval set OR explicitly
        # accept the single-winner case via STAGE3_MIN_DISTINCT=1
        # before trusting the Stage-3 default-flip.
        report.verdict = "stable_single_winner"
        report.rationale = (
            f"{report.promoted} promotions but only "
            f"{report.distinct_winning_configs} distinct config(s); "
            f"need ≥{distinct_threshold} winners across diverse eval "
            f"sets to prove generalization. Likely overfitting — "
            f"vary the eval set or set STAGE3_MIN_DISTINCT=1 to accept."
        )
    else:
        report.verdict = "earned"
        report.rationale = (
            f"{report.promoted} promotions over "
            f"{report.distinct_winning_configs} distinct configs at "
            f"success_ratio={report.success_ratio:.2f} ≥ {ratio_threshold:.2f}"
        )
    return report


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-path", default=None)
    parser.add_argument("--min-cycles", type=int, default=None)
    parser.add_argument("--min-success-ratio", type=float, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    print("scripts/stage3_earned_check.py — Stage-3 default-flip earned-check")
    print(f"Stage-meta opt-in via STAGE3_EARNED_CHECK_ENABLED=1")
    print()
    print(json.dumps(status(), indent=2))
    print()

    if not is_available():
        print("Check disabled. Set STAGE3_EARNED_CHECK_ENABLED=1 to evaluate.")
        sys.exit(0)

    report = check(
        history_path=args.history_path,
        min_cycles=args.min_cycles,
        min_success_ratio=args.min_success_ratio,
    )
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(f"=== Stage-3 default-flip earned-check ===")
        print(f"  verdict:        {report.verdict}")
        print(f"  rationale:      {report.rationale}")
        print(f"  total attempts: {report.total_attempts}")
        print(f"  promoted:       {report.promoted}")
        print(f"  rejected:       {report.rejected}")
        print(f"  skipped:        {report.skipped}")
        print(f"  success ratio:  {report.success_ratio:.2f} "
              f"(required ≥ {report.min_success_ratio_required:.2f})")
        print(f"  distinct configs promoted: {report.distinct_winning_configs}")
        print(f"  cycles required: {report.min_cycles_required}")

    # Exit 0 on earned verdict, 1 otherwise — operators can use in CI
    sys.exit(0 if report.verdict == "earned" else 1)
