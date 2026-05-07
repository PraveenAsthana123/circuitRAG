"""GEPA-prompt promotion gate — Stage-4 adapter (per ADR-024-style chain).

Reads .loop/gepa_optimized_prompts.json (produced by run_gepa_empirical.py
--mode=compile) and ENFORCES safety gates before persisting the
optimized prompts to a prompt registry artifact that prompt_repo.py
can consume. Gates:

  Gate 1 — report status MUST be 'stage_3_compiled' (not 'stage_3_compile_suspect')
           A suspect compile has no real metric calls or unchanged prompts;
           promoting it would replace good prompts with empty/junk.
  Gate 2 — prompt_changed MUST be True
           If the GEPA compile didn't actually change prompts, there's
           nothing to promote.
  Gate 3 — every optimized prompt's instructions field MUST be non-empty
           Empty instructions in a registered prompt break the runtime.
  Gate 4 — append to .loop/gepa_promotion_history.jsonl
           Provenance audit trail per §38 — every promotion attempt
           logged (success OR rejection) with timestamp + reason.

DEFAULT-DENY via GEPA_PROMOTION_GATE_ENABLED=1. The persisted artifact is
written to .loop/gepa_active_prompts.json for prompt_repo to consume.

Stage-4 vs Stage-5:
  Stage-4 (this) — write the artifact + audit history.
  Stage-5 (deferred) — wire prompt_repo.py to READ from the artifact when
    governance.prompts DB row carries gepa_version metadata. That's the
    canary-release surface; this script just produces the input.

CONTRACT:
  - promote(report_path, ...) → PromotionDecision
  - PromotionDecision { promoted: bool, reason: str, ... }
  - status() / is_available()
  - CLI: python3 scripts/promote_gepa_prompts.py [--dry-run]

§47 fail-safe: missing/malformed report → 'skipped' decision, never raises.

COMPOSES WITH:
    scripts/run_gepa_empirical.py — produces gepa_optimized_prompts.json
    scripts/promote_best_config.py — sibling Stage-1 promotion gate
    scripts/best_config_history.py — sibling audit-trail reader
    .loop/gepa_promotion_history.jsonl — append-only audit trail
    services/inference-svc/.../prompt_repo.py — Stage-5 consumer
    §38 (governance), §47 (fail-safe), §51 (forensic substrate),
    §56.3 (Stage-4 in the GEPA chain)
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

GEPA_PROMOTION_GATE_ENABLED = os.getenv(
    "GEPA_PROMOTION_GATE_ENABLED", "",
).strip() == "1"

DEFAULT_REPORT_PATH = ".loop/gepa_optimized_prompts.json"
DEFAULT_ACTIVE_PATH = ".loop/gepa_active_prompts.json"
DEFAULT_HISTORY_PATH = ".loop/gepa_promotion_history.jsonl"


class GepaPromotionGateDisabled(RuntimeError):
    """Raised when force-required gate is invoked but env unset."""


@dataclass
class PromotionDecision:
    """Outcome of a single GEPA-prompt promotion-gate evaluation."""
    promoted: bool
    reason: str
    decided_at_ts: float
    report_status: str = ""
    prompt_changed: bool = False
    predictors_count: int = 0
    gates_failed: list[str] = field(default_factory=list)
    history_appended: bool = False
    active_artifact_written: bool = False
    source_report_path: str = ""
    active_artifact_path: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_available() -> bool:
    """Stage-4 default-deny check."""
    return GEPA_PROMOTION_GATE_ENABLED


def status() -> dict[str, Any]:
    """Operator status surface."""
    return {
        "stage": 4,
        "enabled_env": GEPA_PROMOTION_GATE_ENABLED,
        "available": is_available(),
        "report_path": DEFAULT_REPORT_PATH,
        "active_artifact_path": DEFAULT_ACTIVE_PATH,
        "history_path": DEFAULT_HISTORY_PATH,
        "next_stage": (
            "Stage-5 — prompt_repo.py reads .loop/gepa_active_prompts.json "
            "when governance.prompts row carries gepa_version metadata. "
            "Canary-release surface for traffic-split between baseline "
            "and GEPA-tuned prompts."
        ),
    }


def promote(
    *,
    report_path: str | None = None,
    active_path: str | None = None,
    history_path: str | None = None,
    dry_run: bool = False,
    target_prompt_name: str | None = None,
) -> PromotionDecision:
    """Apply gates; persist active prompts artifact if all pass.

    Per §47 fail-safe: missing/malformed report returns a 'skipped'
    decision, never raises.

    Stage-4 default-deny: when GEPA_PROMOTION_GATE_ENABLED is unset,
    returns 'skipped — gate disabled' without touching files.
    """
    decided_at = time.time()
    rp = report_path or DEFAULT_REPORT_PATH
    ap = active_path or DEFAULT_ACTIVE_PATH
    hp = history_path or DEFAULT_HISTORY_PATH

    decision = PromotionDecision(
        promoted=False,
        reason="",
        decided_at_ts=decided_at,
        source_report_path=rp,
        active_artifact_path=ap,
    )

    if not is_available():
        decision.reason = "skipped — GEPA_PROMOTION_GATE_ENABLED unset"
        return decision

    # Read GEPA report
    p = Path(rp)
    if not p.exists():
        decision.reason = f"skipped — report missing: {rp}"
        return decision
    try:
        report = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        decision.reason = f"skipped — malformed report: {exc}"
        return decision

    # Extract relevant fields for gates
    decision.report_status = str(report.get("status", "unknown"))
    decision.prompt_changed = bool(report.get("prompt_changed", False))
    optimized = report.get("optimized_prompts") or {}
    decision.predictors_count = len(optimized)

    # Apply gates
    failed: list[str] = []

    # Gate 1: status must be stage_3_compiled (not _suspect, not preflight)
    if decision.report_status != "stage_3_compiled":
        failed.append(
            f"report_status={decision.report_status!r} "
            "(must be stage_3_compiled)",
        )

    # Gate 2: prompt_changed must be True
    if not decision.prompt_changed:
        failed.append("prompt_changed=False (no optimization signal)")

    # Gate 3: every prompt has non-empty instructions
    empty_instructions = [
        name for name, p in optimized.items()
        if not (p.get("instructions") or "").strip()
    ]
    if empty_instructions:
        failed.append(
            f"empty instructions for {len(empty_instructions)} predictor(s): "
            f"{empty_instructions[:3]}",
        )

    # Gate 4: at least 1 predictor must be present
    if decision.predictors_count == 0:
        failed.append("optimized_prompts is empty (no predictors)")

    decision.gates_failed = failed

    if failed:
        decision.reason = f"rejected — gates failed: {', '.join(failed)}"
    else:
        decision.promoted = True
        decision.reason = "promoted — all gates passed"

    # Side effects: append history (always), write active artifact on success
    if not dry_run:
        try:
            history_p = Path(hp)
            history_p.parent.mkdir(parents=True, exist_ok=True)
            with history_p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(decision.as_dict()) + "\n")
            decision.history_appended = True
        except Exception as exc:
            log.warning("history append failed: %s", exc)

        if decision.promoted:
            try:
                active_p = Path(ap)
                active_p.parent.mkdir(parents=True, exist_ok=True)
                # Path-B alignment hint (per docs/architecture/
                # gepa-chain-status-and-stage6-blocker.md). When the
                # operator sets GEPA_TARGET_PROMPT_NAME (or passes
                # target_prompt_name=), the artifact carries that name
                # so prompt_repo Stage-5 overlay can ALSO register the
                # tuned prompt under <target>_gepa-<ts> — making the
                # gepa-tagged version reachable from the runtime
                # rag_inference lookup. Path A (refactor CouncilProgram
                # to wrap the runtime template directly) remains the
                # long-term right answer; this is the escape valve so
                # operators can test end-to-end NOW.
                resolved_target = (
                    target_prompt_name
                    or os.environ.get("GEPA_TARGET_PROMPT_NAME", "")
                ).strip() or None
                payload = {
                    "promoted_at_ts": decided_at,
                    "source_report": rp,
                    "report_status": decision.report_status,
                    "predictors_count": decision.predictors_count,
                    "gepa_target_prompt": resolved_target,
                    "optimized_prompts": optimized,
                    "lm_model": report.get("lm_model"),
                    "auto": report.get("auto"),
                    "gepa_elapsed_s": report.get("elapsed_s"),
                    "promotion_gate": {
                        "version": 1,
                        "gates_required": [
                            "report_status==stage_3_compiled",
                            "prompt_changed==True",
                            "non-empty instructions per predictor",
                            "predictors_count >= 1",
                        ],
                    },
                    "next_stage": (
                        "Stage-5 — prompt_repo.py loads this artifact "
                        "when governance.prompts row carries gepa_version "
                        "metadata. Canary traffic-split surface."
                    ),
                }
                active_p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                decision.active_artifact_written = True
            except Exception as exc:
                log.error("active artifact write failed: %s", exc)
                decision.promoted = False
                decision.reason = f"failed to write active artifact: {exc}"

    return decision


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description=(
            "GEPA-prompt promotion gate (Stage-4). Reads "
            ".loop/gepa_optimized_prompts.json, applies safety gates, "
            "and persists .loop/gepa_active_prompts.json for prompt_repo "
            "consumption (Stage-5)."
        ),
    )
    parser.add_argument("--report-path", default=None)
    parser.add_argument("--active-path", default=None)
    parser.add_argument("--history-path", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true",
                        help="Emit decision as JSON only")
    args = parser.parse_args()

    print("scripts/promote_gepa_prompts.py — Stage-4 GEPA-prompt promotion gate")
    print("Stage-4 opt-in via GEPA_PROMOTION_GATE_ENABLED=1")
    print()
    if not args.json:
        print(json.dumps(status(), indent=2))
        print()

    if not is_available():
        print("Gate disabled. Set GEPA_PROMOTION_GATE_ENABLED=1 to run.")
        sys.exit(0)

    decision = promote(
        report_path=args.report_path,
        active_path=args.active_path,
        history_path=args.history_path,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(decision.as_dict(), indent=2))
    else:
        print("=== GEPA-prompt promotion decision ===")
        print(f"  promoted:         {decision.promoted}")
        print(f"  reason:           {decision.reason}")
        print(f"  report_status:    {decision.report_status}")
        print(f"  prompt_changed:   {decision.prompt_changed}")
        print(f"  predictors:       {decision.predictors_count}")
        if decision.gates_failed:
            print("  gates_failed:")
            for g in decision.gates_failed:
                print(f"    - {g}")
        print(f"  history_appended: {decision.history_appended}")
        print(f"  artifact_written: {decision.active_artifact_written}")
        if decision.active_artifact_written:
            print(f"\nActive artifact: {decision.active_artifact_path}")

    sys.exit(0 if decision.promoted else 1)
