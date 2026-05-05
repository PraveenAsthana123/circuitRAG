#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Stage-3 default-flip earned-check (per §43 + §56.3).

Locks the meta-governance gate that decides "is Stage-3 default-flip
earned for this adapter?" Without this gate, any operator can flip a
default on speculation — violating §56.3.

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
CHECK = REPO / "scripts" / "stage3_earned_check.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def _make_history(tmp: Path, rows: list[dict]) -> Path:
    p = tmp / "history.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def main() -> int:
    print("-- 1. POSITIVE: stage3_earned_check.py exists + non-trivial --")
    if not CHECK.exists():
        print(f"x {CHECK} missing")
        return 1
    src = CHECK.read_text(encoding="utf-8")
    if len(src) < 4000:
        print(f"x check too short ({len(src)} chars)")
        return 1
    print(f"  ok: check present ({len(src)} chars)")

    print("-- 2. POSITIVE: 4 contract surfaces (check, status, is_available, EarnedReport) --")
    os.environ["STAGE3_EARNED_CHECK_ENABLED"] = "1"
    mod, spec = _load_module(CHECK)
    for name in ("check", "status", "is_available",
                 "EarnedReport", "Stage3EarnedCheckDisabled"):
        if not hasattr(mod, name):
            print(f"x stage3_earned_check.{name} missing")
            return 1
    print("  ok: 5 surfaces present")

    print("-- 3. NEGATIVE: default-deny — env unset → cold verdict --")
    os.environ.pop("STAGE3_EARNED_CHECK_ENABLED", None)
    spec.loader.exec_module(mod)
    if mod.is_available():
        print("x is_available must be False when env unset")
        return 1
    report = mod.check()
    if report.verdict != "cold":
        print(f"x env unset must yield cold verdict; got {report.verdict}")
        return 1
    if "STAGE3_EARNED_CHECK_ENABLED" not in report.rationale:
        print("x rationale must cite env flag")
        return 1
    print("  ok: default-deny → cold verdict")

    print("-- 4. NEGATIVE: missing history → cold (§47 fail-safe, no raise) --")
    os.environ["STAGE3_EARNED_CHECK_ENABLED"] = "1"
    spec.loader.exec_module(mod)
    report = mod.check(history_path="/nonexistent/path.jsonl")
    if report.verdict != "cold":
        print(f"x missing file must yield cold; got {report.verdict}")
        return 1
    print("  ok: missing history → cold; never raises")

    print("-- 5. NEGATIVE: <min_cycles promotions → not_earned (rejects speculation) --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        # 5 promotions, need 10
        now = time.time()
        rows = [
            {"promoted": True, "decided_at_ts": now - i,
             "config": {"chunking_strategy": "x", "min_score": 0.5,
                        "rerank_enabled": False, "retrieval_top_k": 10}}
            for i in range(5)
        ]
        hp = _make_history(tmp_p, rows)
        report = mod.check(history_path=str(hp), min_cycles=10)
        if report.verdict != "not_earned":
            print(f"x 5 cycles vs min=10 must yield not_earned; got {report.verdict}")
            return 1
        if "10" not in report.rationale or "5" not in str(report.promoted):
            print(f"x rationale must cite the gap; got {report.rationale!r}")
            return 1
    print("  ok: <min_cycles → not_earned (speculation rejected)")

    print("-- 6. NEGATIVE: high rejection rate → flapping (gate fighting writer) --")
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        # 10 promotions + 20 rejections = success_ratio 0.33
        now = time.time()
        rows = []
        for i in range(10):
            rows.append({
                "promoted": True, "decided_at_ts": now - i,
                "config": {"chunking_strategy": f"c{i}", "min_score": 0.5,
                           "rerank_enabled": False, "retrieval_top_k": 10},
            })
        for i in range(20):
            rows.append({
                "promoted": False, "reason": "rejected — gates failed",
                "decided_at_ts": now - 100 - i,
                "gates_failed": ["pass_rate=0.3 < min=0.5"],
            })
        hp = _make_history(tmp_p, rows)
        report = mod.check(history_path=str(hp), min_cycles=5,
                           min_success_ratio=0.8)
        if report.verdict != "flapping":
            print(f"x 10 promoted + 20 rejected must yield flapping; got {report.verdict}")
            return 1
        if "success_ratio" not in report.rationale:
            print("x rationale must cite the success_ratio gap")
            return 1
    print("  ok: high rejection → flapping (correctly identifies gate-vs-writer fight)")

    print("-- 7. POSITIVE+NEGATIVE: cycles+ratio+diversity → earned; single-winner → stable_single_winner --")
    # Two sub-cases drilled here:
    #   7a. Multi-distinct: 12 promotions × 4 distinct configs → earned
    #   7b. Single-winner: 12 promotions × 1 distinct config → stable_single_winner
    #   (overfitting evidence, not generalization — operator must
    #   diversify eval set before trusting Stage-3 default-flip).
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        now = time.time()

        # 7a. Multi-distinct → earned
        rows_multi = []
        for i in range(12):
            rows_multi.append({
                "promoted": True, "decided_at_ts": now - i,
                "config": {"chunking_strategy": "rps", "min_score": 0.5,
                           "rerank_enabled": (i % 4 == 0),
                           "retrieval_top_k": 5 + (i % 4) * 5},
            })
        rows_multi.append({
            "promoted": False, "reason": "rejected — gates failed",
            "decided_at_ts": now - 100,
            "gates_failed": ["margin=0.01 < min=0.05"],
        })
        hp = _make_history(tmp_p, rows_multi)
        report = mod.check(history_path=str(hp), min_cycles=10,
                           min_success_ratio=0.8)
        if report.verdict != "earned":
            print(f"x 7a: multi-distinct must be 'earned'; got {report.verdict} ({report.rationale})")
            return 1
        if report.distinct_winning_configs < 2:
            print(f"x 7a: must count ≥2 distinct configs; got {report.distinct_winning_configs}")
            return 1

        # 7b. Single-winner → stable_single_winner (overfitting flag)
        rows_single = []
        for i in range(12):
            rows_single.append({
                "promoted": True, "decided_at_ts": now - i,
                "config": {"chunking_strategy": "rps", "min_score": 0.5,
                           "rerank_enabled": False, "retrieval_top_k": 10},
            })
        hp2 = tmp_p / "single.jsonl"
        hp2.write_text("\n".join(json.dumps(r) for r in rows_single) + "\n", encoding="utf-8")
        report2 = mod.check(history_path=str(hp2), min_cycles=10,
                            min_success_ratio=0.8)
        if report2.verdict != "stable_single_winner":
            print(f"x 7b: single-winner must be 'stable_single_winner'; got {report2.verdict}")
            return 1
        if "overfitting" not in report2.rationale.lower():
            print(f"x 7b: rationale must cite 'overfitting'; got {report2.rationale!r}")
            return 1

        # 7c. Operator override — STAGE3_MIN_DISTINCT=1 accepts single-winner
        report3 = mod.check(history_path=str(hp2), min_cycles=10,
                            min_success_ratio=0.8, min_distinct=1)
        if report3.verdict != "earned":
            print(f"x 7c: min_distinct=1 must accept single-winner as earned; got {report3.verdict}")
            return 1
    print("  ok: multi-distinct → earned; single-winner → stable_single_winner; min_distinct=1 override works")

    print("-- 8. NEGATIVE: skipped rows are EXCLUDED from success_ratio --")
    # Rationale: skipped means the gate was disabled (env unset / no rows).
    # Counting them as 'failures' would punish operators who deliberately
    # ran the search without the gate (operator-choice, not work failure).
    with TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        now = time.time()
        # 10 promoted + 10 skipped = ratio 1.0 (skipped excluded)
        rows = []
        for i in range(10):
            rows.append({
                "promoted": True, "decided_at_ts": now - i,
                "config": {"chunking_strategy": f"c{i}", "min_score": 0.5,
                           "rerank_enabled": False, "retrieval_top_k": 10},
            })
        for i in range(10):
            rows.append({
                "promoted": False,
                "reason": "skipped — disabled",
                "decided_at_ts": now - 100 - i,
            })
        hp = _make_history(tmp_p, rows)
        report = mod.check(history_path=str(hp), min_cycles=10,
                           min_success_ratio=0.8)
        if report.verdict != "earned":
            print(f"x skipped rows must be EXCLUDED from ratio; expected earned, got {report.verdict}")
            return 1
        if abs(report.success_ratio - 1.0) > 0.01:
            print(f"x ratio should be 1.0 (skipped excluded); got {report.success_ratio}")
            return 1
        if report.skipped != 10:
            print(f"x skipped count should be 10; got {report.skipped}")
            return 1
    print("  ok: skipped rows excluded from ratio (counted but not penalized)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
