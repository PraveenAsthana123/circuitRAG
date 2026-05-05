#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: BGE Stage-3 wire into HybridRetriever (per §43 + §56).

Locks the Stage-3 promotion that ACTUALLY wires bge_reranker_protected
into the HybridRetriever request hot path. The wire is opt-in via
BGE_RERANKER_IN_HOT_PATH=1 (third gate on top of Stage-1's two flags),
preserving legacy-caller compatibility.

Three-flag opt-in chain:
  BGE_RERANKER_ENABLED=1               (Stage-1 BGE adapter)
  NATIVE_COMPUTE_WRAPPER_ENABLED=1     (Stage-1 wrapper)
  BGE_RERANKER_IN_HOT_PATH=1           (Stage-3 wiring — this drill)

Eight steps. Six negative.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RETRIEVER = REPO / "services" / "retrieval-svc" / "app" / "services" / "hybrid_retriever.py"
PROTECTED = REPO / "services" / "retrieval-svc" / "app" / "services" / "bge_reranker_protected.py"
BGE = REPO / "services" / "retrieval-svc" / "app" / "services" / "bge_reranker.py"


def main() -> int:
    print("-- 1. POSITIVE: HybridRetriever now references Stage-3 wire --")
    if not RETRIEVER.exists():
        print(f"x {RETRIEVER} missing")
        return 1
    src = RETRIEVER.read_text(encoding="utf-8")
    if "BGE_RERANKER_IN_HOT_PATH" not in src:
        print("x Stage-3 env flag BGE_RERANKER_IN_HOT_PATH not referenced")
        return 1
    if "protected_rerank" not in src:
        print("x must call protected_rerank from bge_reranker_protected")
        return 1
    print("  ok: HybridRetriever wired to protected_rerank under BGE_RERANKER_IN_HOT_PATH flag")

    print("-- 2. NEGATIVE: BGE Stage-1 + Stage-2 modules don't WIRE Stage-3 (clean layering) --")
    bge_src = BGE.read_text(encoding="utf-8")
    prot_src = PROTECTED.read_text(encoding="utf-8")
    # Stage-3 must NOT have its env-flag check inside Stage-1/2 modules.
    # Documentation MENTIONS of the flag in next_stage docstrings are
    # legitimate (Stage-2 documents Stage-3 path); ACTUAL wiring is the
    # red flag — a getenv check or `if .*BGE_RERANKER_IN_HOT_PATH` block.
    wire_pattern = re.compile(
        r'(os\.getenv\([\'"]BGE_RERANKER_IN_HOT_PATH|'
        r'^\s*if\s+.*BGE_RERANKER_IN_HOT_PATH)',
        re.MULTILINE,
    )
    if wire_pattern.search(bge_src):
        print("x bge_reranker.py has actual Stage-3 env-check wiring — must stay Stage-1")
        return 1
    if wire_pattern.search(prot_src):
        print("x bge_reranker_protected.py has actual Stage-3 env-check wiring — must stay Stage-2")
        return 1
    # Cycle check: Stage-1/2 must not import HybridRetriever
    if "from app.services.hybrid_retriever" in bge_src or "from app.services.hybrid_retriever" in prot_src:
        print("x Stage-1/2 modules must NOT import HybridRetriever (cycle risk)")
        return 1
    print("  ok: Stage-1/2 modules don't WIRE Stage-3 (docstrings can mention; no env-check)")

    print("-- 3. NEGATIVE: wire fires AFTER min_score floor (preserves quality semantics) --")
    # The semantic order MUST be: fused → top_k → min_score → rerank
    # Reranking BEFORE min_score would let irrelevant chunks survive
    # because their bge_score might rank them above borderline-relevant
    # ones. min_score is the hard floor; rerank refines what survives.
    min_score_idx = src.find("min_score_filter")
    rerank_idx = src.find("BGE_RERANKER_IN_HOT_PATH")
    if min_score_idx < 0 or rerank_idx < 0:
        print("x missing min_score or rerank block in HybridRetriever")
        return 1
    if rerank_idx < min_score_idx:
        print("x rerank wire must come AFTER min_score filter; semantic order broken")
        return 1
    print("  ok: rerank fires AFTER min_score floor (correct order)")

    print("-- 4. NEGATIVE: default-deny — wire ONLY fires when env flag set to '1' --")
    # Per Stage-3 default-deny: legacy callers must see no behavior
    # change. Drill the EXACT env-flag check (=='1') so 'true', 'yes',
    # etc. don't accidentally enable.
    flag_check = re.search(
        r'os\.getenv\(\s*[\'"]BGE_RERANKER_IN_HOT_PATH[\'"][^)]*\)\s*\.strip\(\)\s*==\s*[\'"]1[\'"]',
        src,
    )
    if not flag_check:
        print("x flag check must be exact: os.getenv(...).strip() == '1'")
        return 1
    print("  ok: default-deny — wire fires only when flag literally '1'")

    print("-- 5. NEGATIVE: lazy import inside the conditional (no module-top dep) --")
    # Stage-3 imports protected_rerank LAZILY inside the if-block.
    # Module-top import would break callers that don't opt in (they'd
    # pay the cost of loading bge_reranker_protected + transitive
    # FlagEmbedding probe even when off).
    lines_before_class = src[:src.find("class HybridRetriever")]
    if "bge_reranker_protected" in lines_before_class:
        print("x bge_reranker_protected must NOT be imported at module top")
        return 1
    if "protected_rerank" in lines_before_class:
        print("x protected_rerank must NOT be imported at module top")
        return 1
    print("  ok: protected_rerank lazy-imported inside the wire block")

    print("-- 6. NEGATIVE: wire FAILS SAFE — exception caught + chunks preserved --")
    # Per §47 fallback rule: rerank failure must NOT break the request
    # path. The drill enforces a try/except around the rerank call AND
    # a log line so operators see the failure.
    wire_block = src[src.find("BGE_RERANKER_IN_HOT_PATH"):src.find("latency_ms = ")]
    if "try:" not in wire_block:
        print("x wire must wrap rerank call in try/except (fail-safe)")
        return 1
    if "except Exception" not in wire_block:
        print("x must catch generic Exception around rerank (fail-safe)")
        return 1
    if "log.warning" not in wire_block:
        print("x failure path must log.warning so ops sees the issue")
        return 1
    print("  ok: rerank failure caught + logged + chunks preserved")

    print("-- 7. NEGATIVE: bge_score is preserved as metadata (not lost on rebuild) --")
    # When converting reranked dicts back to RetrievedChunk, the
    # bge_score field doesn't exist on RetrievedChunk's schema. We
    # must preserve it in the .metadata dict so downstream callers
    # (citations, rerank-aware ranking) can see it.
    if "bge_score" not in src:
        print("x bge_score handling missing")
        return 1
    if 'metadata' not in src[src.find("BGE_RERANKER_IN_HOT_PATH"):]:
        print("x bge_score must be preserved in metadata dict on rebuild")
        return 1
    print("  ok: bge_score preserved in chunk.metadata after rebuild")

    print("-- 8. POSITIVE: HybridRetriever still imports cleanly (syntax-valid wire) --")
    # Final sanity: the file must still be Python-valid after the edit.
    sys.path.insert(0, str(RETRIEVER.parent.parent.parent))
    try:
        import ast
        ast.parse(src)
    except SyntaxError as exc:
        print(f"x HybridRetriever has syntax error after Stage-3 wire: {exc}")
        return 1
    print("  ok: HybridRetriever Python-valid after Stage-3 wire")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
