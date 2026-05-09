#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: advanced offline-safe RAGAS/Giskard/DeepEval status.

NEGATIVE: missing optional engines must be surfaced instead of silently hidden.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATUS = REPO / "scripts" / "eval_quality_status.py"
HARNESS = REPO / "services" / "evaluation-svc" / "app" / "eval_harness.py"


def require(src: str, needle: str, label: str) -> None:
    if needle not in src:
        raise AssertionError(f"missing {label}: {needle!r}")


def _load_status_module():
    spec = importlib.util.spec_from_file_location("eval_quality_status", STATUS)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load eval_quality_status")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    print("-- 1. POSITIVE: status script exists + parses --")
    src = STATUS.read_text(encoding="utf-8")
    ast.parse(src)
    print("  ok: eval quality status script is Python-valid")

    print("-- 2. POSITIVE: all three eval engines are surfaced --")
    for needle in ("ragas", "giskard", "deepeval", "RAGAS_EVAL_ENABLED", "GISKARD_SCAN_ENABLED", "DEEPEVAL_ENABLED"):
        require(src, needle, needle)
    print("  ok: RAGAS/Giskard/DeepEval status + env gates are present")

    print("-- 3. POSITIVE: deterministic offline gate is available --")
    for needle in ("deterministic_rag_gate", "answer_groundedness", "context_relevance", "answer_correctness"):
        require(src, needle, needle)
    mod = _load_status_module()
    gate = mod.deterministic_rag_gate(
        question="Which store handles graph relationships?",
        answer="Neo4j handles graph relationships.",
        contexts=["Neo4j handles graph relationships with Cypher."],
        ground_truth="Neo4j handles graph relationships.",
    )
    if not gate["overall_pass"]:
        raise AssertionError(f"expected deterministic gate to pass; got {gate}")
    print("  ok: deterministic offline gate scores a known-good RAG sample")

    print("-- 4. NEGATIVE: eval harness catches non-ImportError import failures --")
    harness = HARNESS.read_text(encoding="utf-8")
    for cls_name in ("RagasEngine", "DeepEvalEngine", "GiskardEngine"):
        require(harness, "except Exception as exc", f"{cls_name} broad import safety")
    require(harness, "import_error", "operator import error visibility")
    print("  ok: harness reports import errors instead of crashing eval-svc")

    print("\nALL 4 EVAL QUALITY STATUS STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
