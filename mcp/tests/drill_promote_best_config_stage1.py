#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: promote_best_config Stage-1 (per §38 + §43 + §56).

Locks the safety gates that prevent blind "highest pass-rate wins"
promotion. Closes the §38 governance gap "what's promoted, by what
gate, when, and why?" with an append-only history.jsonl audit trail.

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "scripts" / "promote_best_config.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def _make_report(tmp: Path, *, top_pass: float, runner_pass: float, eval_size: int = 5) -> Path:
    """Synthesize a search report for gate testing."""
    report = {
        "ranked_configs": [
            {
                "config": {
                    "chunking_strategy": "recursive_paragraph_sentence",
                    "min_score": 0.5,
                    "rerank_enabled": False,
                    "rerank_top_k": 10,
                    "retrieval_top_k": 10,
                },
                "overall_pass_rate": top_pass,
                "eval_set_size": eval_size,
            },
            {
                "config": {
                    "chunking_strategy": "recursive_paragraph_sentence",
                    "min_score": 0.0,
                    "rerank_enabled": False,
                    "rerank_top_k": 10,
                    "retrieval_top_k": 5,
                },
                "overall_pass_rate": runner_pass,
                "eval_set_size": eval_size,
            },
        ],
        "summary": "test-fixture",
    }
    p = tmp / "report.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    return p


def main() -> int:
    print("-- 1. POSITIVE: promote_best_config.py exists + non-trivial --")
    if not GATE.exists():
        print(f"x {GATE} missing")
        return 1
    src = GATE.read_text(encoding="utf-8")
    if len(src) < 4000:
        print(f"x gate module too short ({len(src)} chars)")
        return 1
    print(f"  ok: gate present ({len(src)} chars)")

    print("-- 2. POSITIVE: 4 contract surfaces (promote, status, is_available, PromotionDecision) --")
    os.environ["PROMOTION_GATE_ENABLED"] = "1"
    mod, spec = _load_module(GATE)
    for name in ("promote", "status", "is_available",
                 "PromotionDecision", "PromotionGateDisabled"):
        if not hasattr(mod, name):
            print(f"x promote_best_config.{name} missing")
            return 1
    print("  ok: 5 contract surfaces present")

    print("-- 3. NEGATIVE: default-deny — promote() returns 'skipped' when env unset --")
    os.environ.pop("PROMOTION_GATE_ENABLED", None)
    spec.loader.exec_module(mod)
    if mod.is_available():
        print("x is_available() must be False when env unset")
        return 1
    decision = mod.promote()
    if decision.promoted:
        print("x promote() must NOT promote when disabled")
        return 1
    if "skipped" not in decision.reason.lower() or "PROMOTION_GATE_ENABLED" not in decision.reason:
        print(f"x reason must cite env flag; got {decision.reason!r}")
        return 1
    print("  ok: default-deny preserved")

    print("-- 4. NEGATIVE: missing report file → skipped, not raised (§47 fail-safe) --")
    os.environ["PROMOTION_GATE_ENABLED"] = "1"
    spec.loader.exec_module(mod)
    decision = mod.promote(report_path="/nonexistent/path/report.json")
    if decision.promoted:
        print("x missing report must NOT promote")
        return 1
    if "skipped" not in decision.reason.lower():
        print(f"x missing report must yield 'skipped'; got {decision.reason!r}")
        return 1
    print("  ok: §47 fail-safe — missing file never raises")

    print("-- 5. NEGATIVE: low-pass-rate REJECTED by gate (not just warned) --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report = _make_report(tmp_p, top_pass=0.3, runner_pass=0.2, eval_size=5)
        # Force min_pass_rate=0.5 via env override
        os.environ["PROMOTION_MIN_PASS_RATE"] = "0.5"
        spec.loader.exec_module(mod)
        decision = mod.promote(
            report_path=str(report),
            best_path=str(tmp_p / "best.json"),
            history_path=str(tmp_p / "history.jsonl"),
        )
        if decision.promoted:
            print("x pass_rate=0.3 must NOT be promoted under min=0.5")
            return 1
        if not any("pass_rate" in g for g in decision.gates_failed):
            print(f"x gates_failed must cite pass_rate; got {decision.gates_failed}")
            return 1
        # best_config.json MUST NOT have been written
        if (tmp_p / "best.json").exists():
            print("x best_config.json must NOT be written when gate fails")
            return 1
        # history.jsonl MUST have the rejection row
        if not (tmp_p / "history.jsonl").exists():
            print("x history.jsonl must be appended even on rejection (audit)")
            return 1
        os.environ.pop("PROMOTION_MIN_PASS_RATE", None)
    print("  ok: low pass_rate rejected; best_config NOT written; history WAS appended")

    print("-- 6. NEGATIVE: tied pass_rate → Occam tie-break (simpler config wins) --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        # Both configs at 1.0 — but one has rerank=True, one has False.
        # The simpler one (rerank=False) MUST win.
        tied_report = {
            "ranked_configs": [
                {
                    "config": {
                        "chunking_strategy": "recursive_paragraph_sentence",
                        "min_score": 0.5,
                        "rerank_enabled": True,
                        "rerank_top_k": 10,
                        "retrieval_top_k": 10,
                    },
                    "overall_pass_rate": 1.0,
                    "eval_set_size": 5,
                },
                {
                    "config": {
                        "chunking_strategy": "recursive_paragraph_sentence",
                        "min_score": 0.5,
                        "rerank_enabled": False,
                        "rerank_top_k": 10,
                        "retrieval_top_k": 10,
                    },
                    "overall_pass_rate": 1.0,
                    "eval_set_size": 5,
                },
            ],
            "summary": "tied-test",
        }
        rp = tmp_p / "tied.json"
        rp.write_text(json.dumps(tied_report), encoding="utf-8")
        spec.loader.exec_module(mod)
        decision = mod.promote(
            report_path=str(rp),
            best_path=str(tmp_p / "best.json"),
            history_path=str(tmp_p / "history.jsonl"),
        )
        if not decision.promoted:
            print(f"x tied 1.0/1.0 should still promote (margin doesn't apply when both pass min); got {decision.reason}")
            return 1
        if decision.config.get("rerank_enabled") is not False:
            print(f"x Occam tie-break must pick rerank=False (simpler); got {decision.config}")
            return 1
    print("  ok: Occam tie-break picks the simpler config")

    print("-- 7. NEGATIVE: history.jsonl is APPEND-ONLY (audit invariant) --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report = _make_report(tmp_p, top_pass=1.0, runner_pass=0.0, eval_size=5)
        hp = tmp_p / "history.jsonl"
        # Pre-populate with a fake row
        hp.write_text('{"prior":"row"}\n', encoding="utf-8")
        spec.loader.exec_module(mod)
        mod.promote(
            report_path=str(report),
            best_path=str(tmp_p / "best.json"),
            history_path=str(hp),
        )
        lines = hp.read_text(encoding="utf-8").splitlines()
        if len(lines) != 2:
            print(f"x history must be append-only; expected 2 lines, got {len(lines)}")
            return 1
        if json.loads(lines[0]).get("prior") != "row":
            print("x prior history row was overwritten — append-only violated")
            return 1
    print("  ok: history.jsonl is append-only; prior rows preserved")

    print("-- 8. NEGATIVE: dry_run=True → no side effects --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        report = _make_report(tmp_p, top_pass=1.0, runner_pass=0.0, eval_size=5)
        bp = tmp_p / "best.json"
        hp = tmp_p / "history.jsonl"
        spec.loader.exec_module(mod)
        decision = mod.promote(
            report_path=str(report),
            best_path=str(bp),
            history_path=str(hp),
            dry_run=True,
        )
        if not decision.promoted:
            print("x dry_run should still report promoted=True for valid winner")
            return 1
        if bp.exists():
            print("x dry_run must NOT write best_config.json")
            return 1
        if hp.exists():
            print("x dry_run must NOT append to history.jsonl")
            return 1
    print("  ok: dry_run is side-effect-free")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
