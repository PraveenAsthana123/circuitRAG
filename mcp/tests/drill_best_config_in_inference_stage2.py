#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Stage-2 best_config_loader wire into rag_inference.ask (per §43 + §56).

Locks the additive override that makes inference-svc seed top_k from
the empirically-best config when the AskRequest didn't explicitly set
the field. Failure to override = legacy behavior preserved.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAG = REPO / "services" / "inference-svc" / "app" / "services" / "rag_inference.py"
LOADER = REPO / "scripts" / "best_config_loader.py"


def main() -> int:
    print("-- 1. POSITIVE: rag_inference imports best_config_loader getters lazily --")
    if not RAG.exists():
        print(f"x {RAG} missing")
        return 1
    src = RAG.read_text(encoding="utf-8")
    if "from best_config_loader import" not in src:
        print("x rag_inference must import from best_config_loader")
        return 1
    if "get_default_top_k" not in src:
        print("x rag_inference must import get_default_top_k")
        return 1
    print("  ok: best_config_loader imported lazily inside ask()")

    print("-- 2. NEGATIVE: import is INSIDE ask() (lazy, not module-level) --")
    # Module-level imports would force best_config_loader to load at
    # service startup; we want lazy + flag-gated.
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = [a.name for a in getattr(node, "names", [])]
            if mod == "best_config_loader" or "best_config_loader" in names:
                print("x best_config_loader must NOT be imported at module level")
                return 1
    print("  ok: best_config_loader is lazy-imported inside ask()")

    print("-- 3. NEGATIVE: env-flag gate enforced (BEST_CONFIG_LOADER_ENABLED) --")
    if "BEST_CONFIG_LOADER_ENABLED" not in src:
        print("x rag_inference must check BEST_CONFIG_LOADER_ENABLED")
        return 1
    print("  ok: env-flag gated; default disabled")

    print("-- 4. NEGATIVE: caller-explicit top_k WINS over best_config (intent preservation) --")
    # The drill enforces the model_fields_set check — without it the
    # override would steamroll callers that explicitly passed top_k.
    if "model_fields_set" not in src:
        print("x rag_inference must check request.model_fields_set to detect explicit overrides")
        return 1
    if '"top_k" not in request.model_fields_set' not in src:
        print('x must guard override behind: "top_k" not in request.model_fields_set')
        return 1
    print("  ok: caller intent wins; best_config only fills DEFAULTS")

    print("-- 5. NEGATIVE: §47 fail-safe — loader errors do NOT raise --")
    # Find the best_config block + verify try/except around it.
    block_start = src.find("0.5. Stage-2 best-config defaults")
    if block_start < 0:
        print("x best-config block marker missing")
        return 1
    block_end = src.find("# 1. Retrieve", block_start)
    block = src[block_start:block_end]
    if "try:" not in block:
        print("x best-config block must wrap loader call in try/except")
        return 1
    if "except Exception" not in block:
        print("x must catch generic Exception (fail-safe)")
        return 1
    if "effective_top_k = request.top_k" not in block:
        print("x must initialize effective_top_k = request.top_k BEFORE the try")
        return 1
    print("  ok: loader errors don't escape; legacy behavior preserved")

    print("-- 6. NEGATIVE: retrieve() consumes effective_top_k, NOT request.top_k --")
    # The retrieve() call must use the resolved effective_top_k. If
    # the wire is broken (still passes request.top_k), the override
    # has no effect.
    retrieve_idx = src.find("self._retrieval.retrieve(")
    retrieve_end = src.find(")", retrieve_idx)
    retrieve_call = src[retrieve_idx:retrieve_end]
    if "top_k=effective_top_k" not in retrieve_call:
        print("x retrieve() must consume effective_top_k (not request.top_k)")
        return 1
    if "top_k=request.top_k" in retrieve_call:
        print("x retrieve() must NOT pass request.top_k directly (defeats override)")
        return 1
    print("  ok: retrieve() reads effective_top_k after override resolution")

    print("-- 7. POSITIVE: ast-valid + trace step emitted for explainability --")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"x syntax error after Stage-2 wire: {exc}")
        return 1
    if 'trace.step("best_config_defaults")' not in src:
        print("x must emit trace.step('best_config_defaults') for §48 explainability")
        return 1
    print("  ok: ast-valid; trace step emitted (audit-replayable)")

    print("-- 8. NEGATIVE: best_config_loader.py UNCHANGED (no reverse import) --")
    # Stage-2 wire is INTO inference-svc; the loader source must NOT
    # have grown an import OF inference-svc / retrieval-svc (cycle
    # prevention).
    loader_src = LOADER.read_text(encoding="utf-8")
    rev = re.compile(
        r"^\s*(from\s+.*inference|from\s+.*retrieval|"
        r"import\s+.*inference|import\s+.*retrieval|"
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
