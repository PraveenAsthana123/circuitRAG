#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: AutoRAG optimizer Stage-1 (per §43 + §56).

Locks the OPTIMIZATION-PLANE Stage-1 adapter that:
  - exists at scripts/autorag_optimizer.py
  - composes with chunking_strategy_selector + bge_reranker_protected
    + ragas_eval_adapter (all shipped earlier this session)
  - 7 contract surfaces: is_available, status, search_config_space,
    ConfigPoint, SearchAxes, ConfigResult, SearchReport, AutoRAGOptimizerDisabled
  - Default-deny: AUTORAG_OPTIMIZER_ENABLED=1 required
  - Lazy autorag import (heavy)
  - SearchAxes default grid is non-trivial (≥24 configs)
  - Empirical run with synthetic eval_set + run_rag mock returns
    a ranked SearchReport with best_config

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTER = REPO / "scripts" / "autorag_optimizer.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: autorag_optimizer.py exists + non-trivial size --")
    if not ADAPTER.exists():
        print(f"x {ADAPTER} missing")
        return 1
    src = ADAPTER.read_text(encoding="utf-8")
    if len(src) < 6000:
        print(f"x autorag_optimizer too short ({len(src)} chars)")
        return 1
    print(f"  ok: autorag_optimizer present ({len(src)} chars)")

    print("-- 2. POSITIVE: composes with 3 prior Stage-1 adapters --")
    # Search axes pull from existing adapters (chunking + BGE + RAGAS).
    # The module's docstring + composition layer must reference them.
    for ref in ("chunking_strategy_selector", "bge_reranker_protected",
                "ragas_eval_adapter"):
        if ref not in src:
            print(f"x must reference {ref} in composition")
            return 1
    print("  ok: composes with chunking_strategy_selector + bge_reranker_protected + ragas_eval_adapter")

    print("-- 3. POSITIVE: 8 contract surfaces exported --")
    os.environ["AUTORAG_OPTIMIZER_ENABLED"] = "1"
    mod, spec = _load_module(ADAPTER)
    expected = (
        "is_available", "status", "search_config_space",
        "ConfigPoint", "SearchAxes", "ConfigResult", "SearchReport",
        "AutoRAGOptimizerDisabled",
    )
    for name in expected:
        if not hasattr(mod, name):
            print(f"x autorag_optimizer.{name} missing")
            return 1
    print(f"  ok: all {len(expected)} surfaces exported")

    print("-- 4. NEGATIVE: default-deny — search_config_space raises when env unset --")
    os.environ.pop("AUTORAG_OPTIMIZER_ENABLED", None)
    spec.loader.exec_module(mod)
    raised = False
    try:
        mod.search_config_space(eval_set=[], run_rag=lambda q, c: {})
    except mod.AutoRAGOptimizerDisabled as exc:
        raised = True
        if "AUTORAG_OPTIMIZER_ENABLED" not in str(exc):
            print(f"x error msg must cite env flag; got: {exc}")
            return 1
    if not raised:
        print("x search_config_space should raise when flag off")
        return 1
    print("  ok: default-deny preserved (cites env flag)")

    # Re-enable
    os.environ["AUTORAG_OPTIMIZER_ENABLED"] = "1"
    spec.loader.exec_module(mod)

    print("-- 5. NEGATIVE: SearchAxes default grid is non-trivial (≥24 configs) --")
    axes = mod.SearchAxes()
    grid_size = axes.grid_size()
    if grid_size < 24:
        print(f"x default grid too small for empirical search; got {grid_size}")
        return 1
    points = list(axes.points())
    if len(points) != grid_size:
        print(f"x points() must yield exactly grid_size; got {len(points)} vs {grid_size}")
        return 1
    print(f"  ok: default grid has {grid_size} configs (search-worthy)")

    print("-- 6. NEGATIVE: ConfigPoint.signature is stable + dedup-friendly --")
    cp1 = mod.ConfigPoint(chunking_strategy="x", min_score=0.5, rerank_enabled=True)
    cp2 = mod.ConfigPoint(chunking_strategy="x", min_score=0.5, rerank_enabled=True)
    cp3 = mod.ConfigPoint(chunking_strategy="y", min_score=0.5, rerank_enabled=True)
    if cp1.signature() != cp2.signature():
        print("x signature must be stable across equivalent configs")
        return 1
    if cp1.signature() == cp3.signature():
        print("x signature must distinguish different configs")
        return 1
    print("  ok: signature is stable + distinguishing")

    print("-- 7. NEGATIVE: lazy autorag + ragas imports (NOT at module top) --")
    # autorag pulls in lots of deps; module top stays light. ragas
    # adapter imported lazily only when score_fn is None.
    lines_before_def = src[:src.find("def is_available")]
    if re.search(r"^import autorag\b", lines_before_def, re.MULTILINE):
        print("x autorag must NOT be imported at module top")
        return 1
    if re.search(r"^from autorag\b", lines_before_def, re.MULTILINE):
        print("x autorag must NOT be 'from'-imported at module top")
        return 1
    if re.search(r"^from ragas_eval_adapter", lines_before_def, re.MULTILINE):
        print("x ragas_eval_adapter must NOT be imported at module top (lazy default)")
        return 1
    print("  ok: autorag + ragas lazy-loaded")

    print("-- 8. POSITIVE: empirical search returns SearchReport with best_config --")
    # Synthetic eval set + a run_rag/score_fn that's deterministic so
    # the drill stays purely-Python (no Ollama call).
    eval_set = [
        {"question": "Q1", "ground_truth": "A1"},
        {"question": "Q2", "ground_truth": "A2"},
    ]

    def fake_run_rag(q, cp):
        # Better config (higher min_score) → "better answer"
        better = cp.min_score >= 0.5 and cp.rerank_enabled
        return {
            "answer": "good" if better else "bad",
            "contexts": [f"ctx for {q} via {cp.signature()}"],
        }

    def fake_score(q, a, ctx, gt):
        # Better answers = pass; worse = fail
        passing = a == "good"
        scores = {"faithfulness": 0.9 if passing else 0.4,
                  "answer_relevancy": 0.9 if passing else 0.4}
        return {
            "scores": scores,
            "thresholds": {"faithfulness": 0.7, "answer_relevancy": 0.7},
            "passes": {k: v >= 0.7 for k, v in scores.items()},
            "overall_pass": passing,
            "summary": "ok" if passing else "fail",
        }

    # Tiny grid for fast drill
    tiny_axes = mod.SearchAxes(
        chunking_strategies=["a"],
        min_scores=[0.0, 0.5],
        rerank_options=[False, True],
        retrieval_top_ks=[10],
    )
    report = mod.search_config_space(
        eval_set=eval_set,
        run_rag=fake_run_rag,
        score_fn=fake_score,
        axes=tiny_axes,
    )
    if not isinstance(report, mod.SearchReport):
        print("x must return SearchReport")
        return 1
    if report.best_config is None:
        print("x best_config must not be None for non-empty grid")
        return 1
    # The fake_run_rag rule: better when min_score>=0.5 AND rerank.
    # So the winner should be (min_score=0.5, rerank=True).
    if not (report.best_config.min_score == 0.5 and report.best_config.rerank_enabled):
        print(f"x search did not find expected winner; got {report.best_config.signature()}")
        return 1
    if report.best_pass_rate < 1.0:
        print(f"x best should achieve 100% pass; got {report.best_pass_rate}")
        return 1
    if "best=" not in report.summary:
        print(f"x summary must include 'best='; got: {report.summary!r}")
        return 1
    print(f"  ok: search empirically picks correct winner; pass_rate={report.best_pass_rate:.2%}")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
