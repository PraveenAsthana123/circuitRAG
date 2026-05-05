#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: RAGAS Stage-2 wire into eval_harness.py (per §43 + §56).

Locks the Stage-2 wiring of ragas_eval_adapter.score() into the
eval-svc RagasEngine.evaluate() method. This closes the eval-svc
stub gap surfaced in docs/architecture/six-plane-audit-2026-05-04.md.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HARNESS = REPO / "services" / "evaluation-svc" / "app" / "eval_harness.py"
ADAPTER = REPO / "scripts" / "ragas_eval_adapter.py"


def main() -> int:
    print("-- 1. POSITIVE: eval_harness now imports ragas_eval_adapter --")
    if not HARNESS.exists():
        print(f"x {HARNESS} missing")
        return 1
    src = HARNESS.read_text(encoding="utf-8")
    if "ragas_eval_adapter" not in src:
        print("x eval_harness must reference ragas_eval_adapter")
        return 1
    if "from ragas_eval_adapter" not in src:
        print("x must import score from ragas_eval_adapter")
        return 1
    print("  ok: eval_harness wired to ragas_eval_adapter")

    print("-- 2. NEGATIVE: ragas_eval_adapter doesn't IMPORT eval_harness (no cycle) --")
    adapter_src = ADAPTER.read_text(encoding="utf-8")
    rev_import = re.compile(
        r"^\s*(from\s+.*eval_harness|import\s+.*eval_harness|from\s+app\.|import\s+app\.)",
        re.MULTILINE,
    )
    if rev_import.search(adapter_src):
        print("x ragas_eval_adapter imports eval_harness / app modules (cycle)")
        return 1
    print("  ok: ragas_eval_adapter doesn't import eval-svc (clean layering)")

    print("-- 3. NEGATIVE: stub shape preserved when RAGAS_EVAL_ENABLED unset --")
    # Per the operator's brutal rule: don't break callers when adapter
    # is disabled. The harness must return the SAME shape (with metrics
    # dict) whether the adapter fired or not. configured=False signals
    # "operator hasn't opted in", not "broken".
    if 'RAGAS_EVAL_ENABLED' not in src:
        print("x harness must check RAGAS_EVAL_ENABLED env flag")
        return 1
    if 'configured' not in src:
        print("x harness must include 'configured' flag in response")
        return 1
    if "RAGAS_EVAL_ENABLED unset" not in src:
        print("x reason field must cite RAGAS_EVAL_ENABLED when not opted in")
        return 1
    print("  ok: stub shape preserved with configured=False when adapter disabled")

    print("-- 4. NEGATIVE: lazy ragas_eval_adapter import (NOT at module top) --")
    # eval-svc cold-start invariant. ragas pulls in datasets + langchain
    # + transformers. Lazy import inside evaluate() keeps cold-start fast.
    class_idx = src.find("class RagasEngine")
    lines_before_class = src[:class_idx]
    if "from ragas_eval_adapter" in lines_before_class:
        print("x ragas_eval_adapter must NOT be imported at module top")
        return 1
    if "import ragas_eval_adapter" in lines_before_class:
        print("x ragas_eval_adapter must NOT be imported at module top")
        return 1
    print("  ok: ragas_eval_adapter lazy-imported inside evaluate()")

    print("-- 5. NEGATIVE: wire FAILS SAFE — adapter errors fall back to stub shape --")
    # Per §47 fail-safe: never break eval-svc on adapter error. The
    # try/except must catch generic Exception and return a stub-shape
    # response with the error attached.
    eval_idx = src.find("def evaluate(")
    eval_end = src.find("class GuardrailsEngine", eval_idx)
    if eval_end < 0:
        eval_end = eval_idx + 5000
    eval_body = src[eval_idx:eval_end]
    if "try:" not in eval_body:
        print("x evaluate() must wrap adapter call in try/except")
        return 1
    if "except Exception" not in eval_body:
        print("x must catch generic Exception (fail-safe)")
        return 1
    if "logger.warning" not in eval_body:
        print("x failure path must log.warning so ops sees the issue")
        return 1
    if '"error"' not in eval_body and "'error'" not in eval_body:
        print("x error response shape must include 'error' field")
        return 1
    print("  ok: adapter errors caught + logged + stub-shape preserved")

    print("-- 6. NEGATIVE: enabled-path returns AssessmentMatrix-derived fields --")
    # When adapter fires successfully, the response must surface the
    # full AssessmentMatrix shape: scores + thresholds + passes +
    # failures + overall_pass + summary. Drill enforces these are
    # in the response when configured.
    for required in ("scores", "thresholds", "passes", "failures",
                     "overall_pass", "summary", "judge_model"):
        if f'"{required}"' not in src and f"'{required}'" not in src:
            print(f"x enabled-path response missing field: {required}")
            return 1
    print("  ok: enabled response carries full AssessmentMatrix shape")

    print("-- 7. NEGATIVE: ragas backwards-compat 'metrics' dict still present --")
    # Existing dashboard / API consumers expect a 'metrics' dict with
    # faithfulness / answer_relevance / context_precision /
    # context_recall keys. Stage-2 wire must NOT remove this — it
    # populates from AssessmentMatrix.scores when configured + falls
    # back to None when not. Drill enforces backward compat.
    if '"metrics"' not in src and "'metrics'" not in src:
        print("x harness must keep 'metrics' dict for backward compat")
        return 1
    if '"faithfulness"' not in src:
        print("x metrics dict must keep 'faithfulness' key (legacy contract)")
        return 1
    print("  ok: 'metrics' dict preserved (backward-compat with dashboard)")

    print("-- 8. POSITIVE: Python-valid + smoke (disabled path returns dict) --")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"x eval_harness has syntax error after wire: {exc}")
        return 1
    # Smoke: import + invoke with adapter disabled
    os.environ.pop("RAGAS_EVAL_ENABLED", None)
    sys.path.insert(0, str(REPO / "services" / "evaluation-svc"))
    try:
        # Loaded via importlib because the file isn't on sys.path
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_eval_harness_smoke", HARNESS,
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_eval_harness_smoke"] = mod
        spec.loader.exec_module(mod)
        engine = mod.RagasEngine()
        result = engine.evaluate(
            question="test", answer="answer", contexts=["context"],
        )
        if not isinstance(result, dict):
            print(f"x evaluate() must return dict; got {type(result)}")
            return 1
        if result.get("available") is None:
            print("x result must have 'available' key")
            return 1
    except Exception as exc:
        print(f"x evaluate() smoke failed: {exc}")
        return 1
    print(f"  ok: Python-valid + smoke returns dict shape (configured={result.get('configured', '?')})")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
