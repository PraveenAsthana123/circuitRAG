"""Best-config promotion gate — Stage-1 adapter (per CLAUDE.md §38 + §56).

Reads .loop/autorag_search_report.json (produced by run_autorag_empirical.py)
and ENFORCES safety gates before writing .loop/best_config.json. Gates:

  Gate 1 — minimum absolute pass_rate (default 0.5)
           A 30% pass_rate isn't a "winner"; it's a degraded eval set.
  Gate 2 — minimum margin over runner-up (default 0.0 — "any margin")
           When margin = 0 (tie at 1.0), prefer the config with FEWER
           features enabled (Occam): no rerank > rerank, lower top_k > higher.
  Gate 3 — minimum eval_set_size (default 5)
           Fewer than N pairs makes the result non-statistical.
  Gate 4 — mandatory append to .loop/best_config_history.jsonl
           Provenance audit trail per §38 — every promotion attempt logged
           (success OR rejection) with timestamp + reason.

CONTRACT:
  - promote(report_path, dry_run=...) → PromotionDecision
  - PromotionDecision { promoted: bool, reason: str, ... }
  - status() / is_available()
  - Default-deny via PROMOTION_GATE_ENABLED=1; otherwise the existing
    auto-write in run_autorag_empirical.py keeps working unchanged.

OPERATOR FLOW:
    1. operator runs scripts/run_autorag_empirical.py
       → writes .loop/autorag_search_report.json
       → writes .loop/best_config.json (auto-promote, current behavior)
    2. operator runs scripts/promote_best_config.py
       → re-reads search_report
       → applies gates
       → REWRITES best_config.json ONLY if gates pass
       → appends to best_config_history.jsonl

SAFETY:
  - Refuses to write if any gate fails
  - Returns structured PromotionDecision; CLI prints + exits 0/1
  - Never raises on missing/malformed file — returns "skipped"

COMPOSES WITH:
    scripts/run_autorag_empirical.py — produces the search report
    scripts/best_config_loader.py — reads the promoted config
    .loop/best_config_history.jsonl — append-only audit trail
    §38 (governance), §51 (forensic substrate), §56 Stage-1
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PROMOTION_GATE_ENABLED = os.getenv("PROMOTION_GATE_ENABLED", "").strip() == "1"

# Gate thresholds — operator can tune via env
MIN_PASS_RATE = float(os.getenv("PROMOTION_MIN_PASS_RATE", "0.5"))
MIN_MARGIN = float(os.getenv("PROMOTION_MIN_MARGIN", "0.0"))
MIN_EVAL_SET = int(os.getenv("PROMOTION_MIN_EVAL_SET", "5"))


class PromotionGateDisabled(RuntimeError):
    """Raised when force-required gate is invoked but env unset."""


@dataclass
class PromotionDecision:
    """Outcome of a single promotion-gate evaluation."""
    promoted: bool
    reason: str
    decided_at_ts: float
    pass_rate: float = 0.0
    runner_up_pass_rate: float = 0.0
    margin: float = 0.0
    eval_set_size: int = 0
    config: dict[str, Any] = field(default_factory=dict)
    gates_failed: list[str] = field(default_factory=list)
    history_appended: bool = False
    best_config_written: bool = False
    raw_winner_signature: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_available() -> bool:
    """Stage-1 default-deny check."""
    return PROMOTION_GATE_ENABLED


def status() -> dict[str, Any]:
    """Operator status surface."""
    return {
        "stage": 1,
        "enabled_env": PROMOTION_GATE_ENABLED,
        "available": is_available(),
        "gates": {
            "min_pass_rate": MIN_PASS_RATE,
            "min_margin": MIN_MARGIN,
            "min_eval_set": MIN_EVAL_SET,
        },
        "next_stage": (
            "Stage-2 — wire into scripts/run_autorag_empirical.py so the "
            "auto-write of best_config.json is gated by promote_best_config "
            "rather than blind 'highest pass-rate wins'"
        ),
    }


def _occam_score(config: dict[str, Any]) -> int:
    """Lower = simpler. Used to break pass-rate ties."""
    score = 0
    if config.get("rerank_enabled"):
        score += 100
    score += int(config.get("retrieval_top_k", 10))
    return score


def _config_signature(config: dict[str, Any]) -> str:
    """Stable string for audit trail comparisons."""
    return (
        f"chunk={config.get('chunking_strategy', '?')} "
        f"min_score={config.get('min_score', '?')} "
        f"rerank={config.get('rerank_enabled', '?')} "
        f"top_k={config.get('retrieval_top_k', '?')}"
    )


def promote(
    *,
    report_path: str = ".loop/autorag_search_report.json",
    best_path: str = ".loop/best_config.json",
    history_path: str = ".loop/best_config_history.jsonl",
    dry_run: bool = False,
) -> PromotionDecision:
    """Apply gates; promote winner if all pass.

    Per §47 fail-safe: missing/malformed report returns a "skipped"
    decision, never raises.

    Stage-1 contract: when env not set, returns "skipped — gate
    disabled" without touching files. The existing auto-write path
    (in run_autorag_empirical.py) continues unchanged.
    """
    decided_at = time.time()

    if not is_available():
        return PromotionDecision(
            promoted=False,
            reason="skipped — PROMOTION_GATE_ENABLED unset",
            decided_at_ts=decided_at,
        )

    # Read search report
    rp = Path(report_path)
    if not rp.exists():
        return PromotionDecision(
            promoted=False,
            reason=f"skipped — report missing: {report_path}",
            decided_at_ts=decided_at,
        )
    try:
        report = json.loads(rp.read_text(encoding="utf-8"))
    except Exception as exc:
        return PromotionDecision(
            promoted=False,
            reason=f"skipped — malformed report: {exc}",
            decided_at_ts=decided_at,
        )

    ranked = report.get("ranked_configs") or []
    if not ranked:
        return PromotionDecision(
            promoted=False,
            reason="skipped — no ranked_configs in report",
            decided_at_ts=decided_at,
        )

    # Resolve top-1; break ties via Occam (simpler config wins)
    top_pass = max(r.get("overall_pass_rate", 0.0) for r in ranked)
    top_tier = [r for r in ranked if r.get("overall_pass_rate", 0.0) == top_pass]
    top_tier.sort(key=lambda r: _occam_score(r.get("config") or {}))
    winner = top_tier[0]
    runner_up = next(
        (r for r in ranked if r.get("overall_pass_rate", 0.0) < top_pass),
        None,
    )
    runner_pass = runner_up.get("overall_pass_rate", 0.0) if runner_up else 0.0
    margin = top_pass - runner_pass
    eval_size = winner.get("eval_set_size", 0)

    # Apply gates
    failed: list[str] = []
    if top_pass < MIN_PASS_RATE:
        failed.append(f"pass_rate={top_pass:.2f} < min={MIN_PASS_RATE}")
    if margin < MIN_MARGIN:
        failed.append(f"margin={margin:.2f} < min={MIN_MARGIN}")
    if eval_size < MIN_EVAL_SET:
        failed.append(f"eval_set_size={eval_size} < min={MIN_EVAL_SET}")

    decision = PromotionDecision(
        promoted=False,
        reason="",
        decided_at_ts=decided_at,
        pass_rate=top_pass,
        runner_up_pass_rate=runner_pass,
        margin=margin,
        eval_set_size=eval_size,
        config=dict(winner.get("config") or {}),
        gates_failed=failed,
        raw_winner_signature=_config_signature(winner.get("config") or {}),
    )

    if failed:
        decision.reason = f"rejected — gates failed: {', '.join(failed)}"
    else:
        decision.promoted = True
        decision.reason = "promoted — all gates passed"

    # Side effects: append history (always, success or fail), and
    # write best_config.json on success.
    if not dry_run:
        try:
            hp = Path(history_path)
            hp.parent.mkdir(parents=True, exist_ok=True)
            with hp.open("a", encoding="utf-8") as f:
                f.write(json.dumps(decision.as_dict()) + "\n")
            decision.history_appended = True
        except Exception as exc:
            log.warning("history append failed: %s", exc)

        if decision.promoted:
            try:
                bp = Path(best_path)
                bp.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "promoted_at_ts": decided_at,
                    "config": decision.config,
                    "pass_rate": top_pass,
                    "runner_up_pass_rate": runner_pass,
                    "margin": margin,
                    "eval_set_size": eval_size,
                    "search_method": report.get("summary", "unknown"),
                    "promotion_gate": {
                        "min_pass_rate": MIN_PASS_RATE,
                        "min_margin": MIN_MARGIN,
                        "min_eval_set": MIN_EVAL_SET,
                    },
                }
                bp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                decision.best_config_written = True
            except Exception as exc:
                log.error("best_config write failed: %s", exc)
                decision.promoted = False
                decision.reason = f"failed to write best_config: {exc}"

    return decision


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print("scripts/promote_best_config.py — Stage-1 promotion gate")
    print("Stage-1 opt-in via PROMOTION_GATE_ENABLED=1")
    print()
    print(json.dumps(status(), indent=2))
    print()
    if not is_available():
        print("Gate disabled. Set PROMOTION_GATE_ENABLED=1 to run.")
        sys.exit(0)
    decision = promote()
    print(json.dumps(decision.as_dict(), indent=2))
    sys.exit(0 if decision.promoted else 1)
