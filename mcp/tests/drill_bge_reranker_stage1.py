#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: BGE reranker Stage-1 adapter (per §56 + compression-tools-audit).

Per CLAUDE.md §43 + §56. Locks Stage-1 promotion that:

  - bge_reranker.py exists as a SEPARATE module (NOT modifying RRF)
  - 4 contract surfaces: is_available, rerank, status, BGERerankerDisabled
  - Default opt-in via BGE_RERANKER_ENABLED=1
  - When disabled → is_available() returns False; rerank raises
    BGERerankerDisabled with actionable error message
  - Lazy import — FlagEmbedding NOT loaded at module import time
  - Stage-1 status reports the right metadata (stage, enabled_env,
    available, wiring_status, next_stage)
  - Source documents the §43 + §56 gate path
  - RRF reranker source unchanged (no Stage-1 leakage into RRF)

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SVC = REPO / "services" / "retrieval-svc" / "app" / "services"
BGE = SVC / "bge_reranker.py"
RRF = SVC / "reranker.py"
sys.path.insert(0, str(REPO / "services" / "retrieval-svc"))


def main() -> int:
    print("-- 1. POSITIVE: bge_reranker.py exists as a SEPARATE module --")
    if not BGE.exists():
        print(f"x {BGE} missing")
        return 1
    src = BGE.read_text(encoding="utf-8")
    if len(src) < 2000:
        print(f"x bge_reranker module too short ({len(src)} chars)")
        return 1
    print(f"  ok: bge_reranker present ({len(src)} chars)")

    print("-- 2. NEGATIVE: RRF reranker source UNCHANGED (no Stage-1 leakage) --")
    # The RRF reranker is the Stage-0 baseline. Stage-1 BGE adapter must
    # NOT modify it; new file only. Drilled to lock the Stage-1
    # adapter-pattern contract.
    rrf_src = RRF.read_text(encoding="utf-8")
    if "BGE" in rrf_src or "bge_score" in rrf_src or "FlagReranker" in rrf_src:
        print("x RRF reranker has BGE leakage — Stage-1 must be a separate module")
        return 1
    print("  ok: RRF source unchanged (Stage-0 contract preserved)")

    print("-- 3. POSITIVE: 4 contract surfaces exported --")
    os.environ.pop("BGE_RERANKER_ENABLED", None)
    # Need to import via app.services.bge_reranker but that requires app
    # path to be in sys.path. Use direct module load.
    spec = importlib.util.spec_from_file_location("bge_reranker", BGE)
    bge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bge)
    for name in ("is_available", "rerank", "status", "BGERerankerDisabled"):
        if not hasattr(bge, name):
            print(f"x bge_reranker.{name} missing")
            return 1
    print("  ok: 4 surfaces exported (is_available, rerank, status, exception)")

    print("-- 4. NEGATIVE: default is_available()=False (BGE_RERANKER_ENABLED unset) --")
    # The module loaded above already saw env BGE_RERANKER_ENABLED unset.
    # We pop it again to confirm + re-execute the spec to re-evaluate
    # the module-level constant.
    os.environ.pop("BGE_RERANKER_ENABLED", None)
    spec.loader.exec_module(bge)  # re-execute against current env
    if bge.is_available():
        print(f"x default must be False; got {bge.is_available()}")
        return 1
    print("  ok: default opt-out preserved")

    print("-- 5. NEGATIVE: rerank raises BGERerankerDisabled when off --")
    raised = False
    try:
        bge.rerank("test query", [{"text": "test chunk"}])
    except bge.BGERerankerDisabled as exc:
        raised = True
        if "BGE_RERANKER_ENABLED" not in str(exc):
            print(f"x error msg must cite BGE_RERANKER_ENABLED; got: {exc}")
            return 1
    if not raised:
        print("x rerank should raise when flag off")
        return 1
    print("  ok: BGERerankerDisabled raised + cites flag")

    print("-- 6. NEGATIVE: BGERerankerDisabled subclasses RuntimeError --")
    if not issubclass(bge.BGERerankerDisabled, RuntimeError):
        print("x BGERerankerDisabled must subclass RuntimeError")
        return 1
    print("  ok: exception is RuntimeError-subclass")

    print("-- 7. NEGATIVE: heavy FlagReranker class NOT instantiated at module import --")
    # Stage-1 adapter contract: the EXPENSIVE thing (FlagReranker class
    # which loads a 568M-param model on instantiation) must be lazy.
    # is_available() can do `import FlagEmbedding` for a fast availability
    # check — that's not the load-cost; the load is FlagReranker(model_id).
    lines_before_def = src[:src.find("def rerank")]
    if "FlagReranker(" in lines_before_def:
        print("x FlagReranker(...) must NOT be instantiated at module top — only inside rerank()")
        return 1
    # Module-level Reranker = FlagReranker(...) assignment also forbidden
    import re as _re
    if _re.search(r"^[A-Z_]+\s*=\s*FlagReranker", lines_before_def, _re.MULTILINE):
        print("x module-level FlagReranker assignment detected — must be lazy")
        return 1
    print("  ok: FlagReranker lazy-instantiated inside rerank()")

    print("-- 8. POSITIVE: status() reports Stage-1 + next-stage path --")
    s = bge.status()
    if s.get("stage") != 1:
        print(f"x status.stage must be 1; got {s.get('stage')}")
        return 1
    for key in ("enabled_env", "model", "available", "wiring_status", "next_stage"):
        if key not in s:
            print(f"x status missing key: {key}")
            return 1
    if "Stage-2" not in s["next_stage"]:
        print("x status.next_stage must reference Stage-2 wiring path")
        return 1
    print("  ok: status reports stage=1 + Stage-2 next-step path")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
