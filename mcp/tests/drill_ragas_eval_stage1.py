#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: RAGAS eval adapter Stage-1 (per §43 + §56).

Locks the Evaluation-Plane Stage-1 adapter that:
  - exists at scripts/ragas_eval_adapter.py
  - composes with eval-svc (which still has stub imports — Stage-2)
  - 7 contract surfaces: is_available, status, score, aggregate,
    AssessmentMatrix, BenchmarkMatrix, RAGASEvalDisabled
  - 5 RAGAS metrics: faithfulness, answer_relevancy, context_precision,
    context_recall, answer_correctness
  - Default-deny: RAGAS_EVAL_ENABLED=1 required
  - Lazy ragas import (cold-start fast)
  - Auto-skips ground-truth-required metrics when none provided
  - eval_harness.py source UNCHANGED (Stage-2 lands the wiring)

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTER = REPO / "scripts" / "ragas_eval_adapter.py"
EVAL_HARNESS = REPO / "services" / "evaluation-svc" / "app" / "eval_harness.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: ragas_eval_adapter.py exists + non-trivial size --")
    if not ADAPTER.exists():
        print(f"x {ADAPTER} missing")
        return 1
    src = ADAPTER.read_text(encoding="utf-8")
    if len(src) < 6000:
        print(f"x adapter too short ({len(src)} chars)")
        return 1
    print(f"  ok: ragas_eval_adapter present ({len(src)} chars)")

    print("-- 2. NEGATIVE: eval_harness.py source UNCHANGED (Stage-2 wires) --")
    if EVAL_HARNESS.exists():
        eh = EVAL_HARNESS.read_text(encoding="utf-8")
        if "ragas_eval_adapter" in eh or "AssessmentMatrix" in eh:
            print("x eval_harness has Stage-1 reference — Stage-2 hasn't landed")
            return 1
    print("  ok: eval_harness source unchanged (Stage-1 purely additive)")

    print("-- 3. POSITIVE: 7 contract surfaces exported --")
    os.environ.pop("RAGAS_EVAL_ENABLED", None)
    mod, spec = _load_module(ADAPTER)
    expected = (
        "is_available", "status", "score", "aggregate",
        "AssessmentMatrix", "BenchmarkMatrix", "RAGASEvalDisabled",
    )
    for name in expected:
        if not hasattr(mod, name):
            print(f"x ragas_eval_adapter.{name} missing")
            return 1
    print("  ok: 7 surfaces exported")

    print("-- 4. NEGATIVE: default-deny — score() raises when env unset --")
    os.environ.pop("RAGAS_EVAL_ENABLED", None)
    spec.loader.exec_module(mod)
    raised = False
    try:
        mod.score(question="q", answer="a", contexts=["c"])
    except mod.RAGASEvalDisabled as exc:
        raised = True
        if "RAGAS_EVAL_ENABLED" not in str(exc):
            print(f"x error msg must cite env flag; got: {exc}")
            return 1
    if not raised:
        print("x score() should raise when flag off")
        return 1
    print("  ok: default-deny preserved (cites env flag)")

    print("-- 5. NEGATIVE: 5 RAGAS metrics declared (operator-spec coverage) --")
    expected_metrics = {
        "faithfulness", "answer_relevancy", "context_precision",
        "context_recall", "answer_correctness",
    }
    declared = set(mod.ALL_METRICS)
    missing = expected_metrics - declared
    if missing:
        print(f"x missing metrics: {sorted(missing)}")
        return 1
    if len(declared) != 5:
        print(f"x expected 5 metrics; got {len(declared)}")
        return 1
    # Per-metric thresholds must exist for all 5
    for m in expected_metrics:
        if m not in mod.THRESHOLDS:
            print(f"x THRESHOLDS missing entry for {m}")
            return 1
    print("  ok: 5 RAGAS metrics + per-metric thresholds")

    print("-- 6. NEGATIVE: lazy ragas import (NOT at module top) --")
    # ragas pulls in datasets, langchain, transformers — heavy. Module
    # top stays light; ragas loaded inside score()/_configure_judge().
    lines_before_def = src[:src.find("def is_available")]
    if re.search(r"^import ragas\b", lines_before_def, re.MULTILINE):
        print("x ragas must NOT be imported at module top")
        return 1
    if re.search(r"^from ragas\b", lines_before_def, re.MULTILINE):
        print("x ragas must NOT be 'from'-imported at module top")
        return 1
    if "from datasets" in lines_before_def or "import datasets" in lines_before_def:
        print("x datasets must NOT be imported at module top (heavy)")
        return 1
    print("  ok: ragas + datasets lazy-loaded inside score()")

    print("-- 7. NEGATIVE: AssessmentMatrix + BenchmarkMatrix expose required fields --")
    a = mod.AssessmentMatrix()
    for field_name in ("scores", "thresholds", "passes", "failures",
                       "overall_pass", "summary", "metric_count", "judge_model"):
        if not hasattr(a, field_name):
            print(f"x AssessmentMatrix missing field: {field_name}")
            return 1
    d = a.as_dict()
    if "overall_pass" not in d:
        print("x as_dict must include overall_pass")
        return 1
    b = mod.BenchmarkMatrix()
    for field_name in ("window_size", "per_metric_mean", "per_metric_p50",
                       "per_metric_p95", "per_metric_pass_rate", "overall_pass_rate"):
        if not hasattr(b, field_name):
            print(f"x BenchmarkMatrix missing field: {field_name}")
            return 1
    # Also test aggregate() with synthetic rows
    rows = [
        mod.AssessmentMatrix(
            scores={"faithfulness": 0.9, "answer_relevancy": 0.8},
            passes={"faithfulness": True, "answer_relevancy": True},
            overall_pass=True,
        ),
        mod.AssessmentMatrix(
            scores={"faithfulness": 0.5, "answer_relevancy": 0.6},
            passes={"faithfulness": False, "answer_relevancy": False},
            overall_pass=False,
        ),
    ]
    bench = mod.aggregate(rows)
    if bench.window_size != 2:
        print(f"x aggregate() window_size must be 2; got {bench.window_size}")
        return 1
    if abs(bench.overall_pass_rate - 0.5) > 0.001:
        print(f"x aggregate() overall_pass_rate must be 0.5; got {bench.overall_pass_rate}")
        return 1
    if "faithfulness" not in bench.per_metric_mean:
        print("x aggregate() must compute per_metric_mean")
        return 1
    print("  ok: AssessmentMatrix + BenchmarkMatrix + aggregate() shape")

    print("-- 8. POSITIVE: status() reports stage=1 + Stage-2 wiring path --")
    s = mod.status()
    if s.get("stage") != 1:
        print(f"x stage must be 1; got {s.get('stage')}")
        return 1
    for key in ("enabled_env", "available", "lm_model", "ollama_host",
                "metrics", "thresholds", "wiring_status", "next_stage"):
        if key not in s:
            print(f"x status missing key: {key}")
            return 1
    if "Stage-2" not in s["next_stage"]:
        print("x next_stage must reference Stage-2")
        return 1
    if "eval_harness" not in s["next_stage"]:
        print("x next_stage must mention eval_harness (Stage-2 wiring site)")
        return 1
    if "rag_inference" not in s["next_stage"]:
        print("x next_stage must mention rag_inference (per-/ask wiring site)")
        return 1
    if len(s["metrics"]) != 5:
        print(f"x status.metrics must list 5 metrics; got {len(s['metrics'])}")
        return 1
    print("  ok: status reports stage=1 + Stage-2 wiring path covers eval_harness + rag_inference")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
