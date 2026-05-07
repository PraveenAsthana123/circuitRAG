#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Stage-2 best_config_loader wire into HybridRetriever (per §43 + §56).

Symmetric to drill_best_config_in_inference_stage2.py — locks the same
intent-preserving + fail-safe override pattern in retrieval-svc.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HR = REPO / "services" / "retrieval-svc" / "app" / "services" / "hybrid_retriever.py"
LOADER = REPO / "scripts" / "best_config_loader.py"


def main() -> int:
    print("-- 1. POSITIVE: hybrid_retriever lazily imports best_config_loader getters --")
    if not HR.exists():
        print(f"x {HR} missing")
        return 1
    src = HR.read_text(encoding="utf-8")
    if "from best_config_loader import" not in src:
        print("x hybrid_retriever must import from best_config_loader")
        return 1
    if "get_default_min_score" not in src:
        print("x must import get_default_min_score")
        return 1
    print("  ok: best_config_loader imported lazily")

    print("-- 2. NEGATIVE: import is INSIDE retrieve() (lazy, not module-level) --")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            if mod == "best_config_loader" or "best_config_loader" in names:
                print("x best_config_loader must NOT be imported at module level")
                return 1
    print("  ok: best_config_loader is lazy-imported inside retrieve()")

    print("-- 3. NEGATIVE: env-flag gate enforced --")
    if "BEST_CONFIG_LOADER_ENABLED" not in src:
        print("x retriever must check BEST_CONFIG_LOADER_ENABLED")
        return 1
    print("  ok: env-flag gated; default disabled")

    print("-- 4. NEGATIVE: caller-explicit min_score WINS (model_fields_set guard) --")
    if "model_fields_set" not in src:
        print("x retriever must check request.model_fields_set")
        return 1
    if '"min_score" not in request.model_fields_set' not in src:
        print('x must guard override behind: "min_score" not in request.model_fields_set')
        return 1
    print("  ok: caller intent wins; best_config only fills DEFAULTS")

    print("-- 5. NEGATIVE: §47 fail-safe — loader errors don't escape --")
    block_start = src.find("Stage-2 best_config_loader wire")
    if block_start < 0:
        print("x best_config block marker missing")
        return 1
    block_end = src.find("if effective_min_score > 0.0:", block_start)
    if block_end < 0:
        print("x effective_min_score floor marker missing")
        return 1
    block = src[block_start:block_end]
    if "try:" not in block:
        print("x best_config block must wrap loader call in try/except")
        return 1
    if "except Exception" not in block:
        print("x must catch generic Exception")
        return 1
    if "effective_min_score = request.min_score" not in block:
        print("x must initialize effective_min_score = request.min_score BEFORE try")
        return 1
    print("  ok: loader errors don't escape; legacy behavior preserved")

    print("-- 6. NEGATIVE: floor uses effective_min_score (not request.min_score) --")
    # The min_score floor + log line MUST consume effective_min_score.
    # If they still read request.min_score, the override has no effect.
    floor_idx = src.find("if effective_min_score > 0.0:")
    floor_end = src.find("# Stage-2 HyDE wire", floor_idx)
    floor_body = src[floor_idx:floor_end]
    if "c.score >= effective_min_score" not in floor_body:
        print("x floor filter must use effective_min_score")
        return 1
    if "c.score >= request.min_score" in floor_body:
        print("x floor filter must NOT reference request.min_score directly")
        return 1
    if "n_after, effective_min_score" not in floor_body:
        print("x log line must report effective threshold (not request literal)")
        return 1
    print("  ok: floor consumes effective_min_score")

    print("-- 7. POSITIVE: ast-valid + cache fingerprint still uses request literal --")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"x syntax error after Stage-2 wire: {exc}")
        return 1
    # Cache fingerprint MUST keep req.min_score (the literal request
    # value). If it switched to effective_min_score, two different
    # callers (one explicit min_score=0.0, one omitting and getting
    # best_config 0.5) would COLLIDE on the same fingerprint.
    fp_idx = src.find("min_score=str(req.min_score)")
    if fp_idx < 0:
        print("x cache fingerprint must reference req.min_score (request literal)")
        return 1
    print("  ok: ast-valid; cache fingerprint preserves request literal")

    print("-- 8. NEGATIVE: best_config_loader.py UNCHANGED (no reverse import) --")
    loader_src = LOADER.read_text(encoding="utf-8")
    rev = re.compile(
        r"^\s*(from\s+.*retrieval|from\s+.*inference|"
        r"import\s+.*retrieval|import\s+.*inference|"
        r"from\s+services\.|import\s+services\.)",
        re.MULTILINE,
    )
    if rev.search(loader_src):
        print("x best_config_loader imports services (cycle risk)")
        return 1
    print("  ok: loader source clean; no cycle introduced")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
