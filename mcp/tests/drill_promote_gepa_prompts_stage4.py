#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: promote_gepa_prompts Stage-4 gate (per ADR-024-style chain + §43).

Locks the GEPA-prompt promotion gate that prevents suspect / unchanged /
empty optimization runs from being promoted to the active-prompts
artifact. Composes with promote_best_config (sibling gate) and the
empirical-loop chain.

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "scripts" / "promote_gepa_prompts.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def _make_report(tmp: Path, **overrides) -> Path:
    """Synthesize a GEPA report with sensible defaults that pass all gates,
    then apply per-test overrides."""
    base = {
        "ran_at_ts": time.time(),
        "status": "stage_3_compiled",
        "eval_set_size": 5,
        "trainset_size": 5,
        "auto": "light",
        "elapsed_s": 120.0,
        "lm_model": "ollama_chat/gemma2:9b",
        "metric_stats": {
            "calls": 50,
            "zero_scores": 10,
            "empty_answers": 0,
            "errors": 0,
            "samples": [],
        },
        "prompt_changed": True,
        "optimized_prompts": {
            "predict.predict": {
                "instructions": "Answer the user's question using council reasoning. Cite sources.",
                "fields": ["question", "answer"],
            },
        },
        "next_stage": "Stage-4 — promote",
        "summary": "test fixture",
    }
    base.update(overrides)
    p = tmp / "report.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    return p


def main() -> int:
    print("-- 1. POSITIVE: promote_gepa_prompts.py exists + non-trivial --")
    if not GATE.exists():
        print(f"x {GATE} missing")
        return 1
    src = GATE.read_text(encoding="utf-8")
    if len(src) < 4000:
        print(f"x gate too short ({len(src)} chars)")
        return 1
    print(f"  ok: gate present ({len(src)} chars)")

    print("-- 2. POSITIVE: 5 contract surfaces present --")
    os.environ["GEPA_PROMOTION_GATE_ENABLED"] = "1"
    mod, spec = _load_module(GATE)
    for name in ("promote", "status", "is_available",
                 "PromotionDecision", "GepaPromotionGateDisabled"):
        if not hasattr(mod, name):
            print(f"x promote_gepa_prompts.{name} missing")
            return 1
    print("  ok: 5 contract surfaces present")

    print("-- 3. NEGATIVE: default-deny — env unset → 'skipped' --")
    os.environ.pop("GEPA_PROMOTION_GATE_ENABLED", None)
    spec.loader.exec_module(mod)
    if mod.is_available():
        print("x is_available() must be False when env unset")
        return 1
    decision = mod.promote()
    if decision.promoted:
        print("x must NOT promote when disabled")
        return 1
    if "skipped" not in decision.reason.lower() or "GEPA_PROMOTION_GATE_ENABLED" not in decision.reason:
        print(f"x reason must cite env flag; got {decision.reason!r}")
        return 1
    print("  ok: default-deny preserved")

    print("-- 4. NEGATIVE: missing report → skipped, never raises (§47 fail-safe) --")
    os.environ["GEPA_PROMOTION_GATE_ENABLED"] = "1"
    spec.loader.exec_module(mod)
    decision = mod.promote(report_path="/nonexistent/path/report.json")
    if decision.promoted:
        print("x missing report must NOT promote")
        return 1
    if "skipped" not in decision.reason.lower():
        print(f"x missing report must yield 'skipped'; got {decision.reason!r}")
        return 1
    print("  ok: §47 fail-safe — missing file never raises")

    print("-- 5. NEGATIVE: status='stage_3_compile_suspect' REJECTED --")
    # Critical: the suspect-detection in run_gepa_empirical (commit 6cc6ddd
    # + user/linter additions) flags fast/empty runs as suspect. The
    # promotion gate MUST refuse to promote those. If it didn't, we'd
    # replace good prompts with the unchanged-but-marked-suspect output.
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report = _make_report(tmp_p, status="stage_3_compile_suspect")
        decision = mod.promote(
            report_path=str(report),
            active_path=str(tmp_p / "active.json"),
            history_path=str(tmp_p / "history.jsonl"),
        )
        if decision.promoted:
            print("x suspect status must be REJECTED")
            return 1
        if not any("stage_3_compiled" in g for g in decision.gates_failed):
            print(f"x rationale must cite required status; got {decision.gates_failed}")
            return 1
        # Active artifact MUST NOT be written
        if (tmp_p / "active.json").exists():
            print("x active artifact must NOT be written on rejection")
            return 1
        # History MUST be appended (audit invariant)
        if not (tmp_p / "history.jsonl").exists():
            print("x history.jsonl must be appended even on rejection")
            return 1
    print("  ok: suspect status rejected; no artifact; history audited")

    print("-- 6. NEGATIVE: prompt_changed=False REJECTED --")
    # If GEPA didn't actually change prompts, there's nothing to promote.
    # Promoting unchanged-prompts would still bump version + perturb the
    # cache layer for no actual improvement.
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report = _make_report(tmp_p, prompt_changed=False)
        decision = mod.promote(
            report_path=str(report),
            active_path=str(tmp_p / "active.json"),
            history_path=str(tmp_p / "history.jsonl"),
        )
        if decision.promoted:
            print("x prompt_changed=False must be REJECTED")
            return 1
        if not any("prompt_changed" in g for g in decision.gates_failed):
            print(f"x rationale must cite prompt_changed; got {decision.gates_failed}")
            return 1
    print("  ok: prompt_changed=False rejected (no optimization signal)")

    print("-- 7. NEGATIVE: empty instructions REJECTED (defends runtime) --")
    # An empty-instructions prompt registered into prompt_repo would
    # break the runtime. Drill enforces the gate catches this.
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report = _make_report(
            tmp_p,
            optimized_prompts={
                "predict.predict": {"instructions": "", "fields": []},
            },
        )
        decision = mod.promote(
            report_path=str(report),
            active_path=str(tmp_p / "active.json"),
            history_path=str(tmp_p / "history.jsonl"),
        )
        if decision.promoted:
            print("x empty instructions must be REJECTED")
            return 1
        if not any("empty instructions" in g for g in decision.gates_failed):
            print(f"x rationale must cite empty instructions; got {decision.gates_failed}")
            return 1
    print("  ok: empty instructions rejected")

    print("-- 8. POSITIVE: valid report PROMOTED + artifact written + history appended --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report = _make_report(tmp_p)
        active_path = tmp_p / "active.json"
        history_path = tmp_p / "history.jsonl"
        decision = mod.promote(
            report_path=str(report),
            active_path=str(active_path),
            history_path=str(history_path),
        )
        if not decision.promoted:
            print(f"x valid report should promote; got {decision.reason}")
            return 1
        if not active_path.exists():
            print("x active artifact must be written on promotion")
            return 1
        if not history_path.exists():
            print("x history must be appended on promotion")
            return 1
        # Active artifact must contain optimized_prompts + provenance
        active = json.loads(active_path.read_text())
        if "optimized_prompts" not in active:
            print("x active artifact missing optimized_prompts")
            return 1
        if "promotion_gate" not in active:
            print("x active artifact missing promotion_gate metadata")
            return 1
        if active.get("predictors_count") != 1:
            print(f"x predictors_count expected 1; got {active.get('predictors_count')}")
            return 1
        # Dry-run check: same valid input + dry_run=True → no side effects
        active_dry = tmp_p / "active_dry.json"
        history_dry = tmp_p / "history_dry.jsonl"
        decision_dry = mod.promote(
            report_path=str(report),
            active_path=str(active_dry),
            history_path=str(history_dry),
            dry_run=True,
        )
        if not decision_dry.promoted:
            print("x dry_run with valid report should still report promoted=True")
            return 1
        if active_dry.exists():
            print("x dry_run must NOT write active artifact")
            return 1
        if history_dry.exists():
            print("x dry_run must NOT append history")
            return 1
    print("  ok: valid report promoted; artifact + history written; dry_run side-effect-free")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
