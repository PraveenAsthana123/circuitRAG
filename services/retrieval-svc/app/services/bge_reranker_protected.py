"""BGE reranker WITH circuit breaker — Stage-2 wiring.

Per CLAUDE.md §43 + §47 + §52 + §56 + the operator-supplied
"LLVM/MLIR + Circuit Breaker + Agent Council" sequence spec.

Stage-1 shipped: bge_reranker (the BGE adapter, opt-in) and
native_compute_wrapper (the breaker+timeout+fallback shield).
Stage-2 wires the shield AROUND the blade, with RRF as the survival
path on timeout / breaker-open / native exception.

Usage:
    from bge_reranker_protected import protected_rerank

    chunks = protected_rerank(query, raw_chunks, top_k=10)
    # On native success: BGE re-ordered chunks
    # On breaker open / timeout / error: original chunks unchanged
    #   (caller's existing RRF+min_score is the natural fallback shape;
    #    we don't re-fuse here because the chunks already came through
    #    HybridRetriever's RRF stage — passing them through unchanged
    #    preserves the RRF ranking.)

Stage-2 invariants (drilled):
  - protected_rerank() composes bge_reranker.rerank with NativeComputeWrapper
  - Both must be opted in (BGE_RERANKER_ENABLED=1 + NATIVE_COMPUTE_WRAPPER_ENABLED=1)
  - When EITHER is off → caller gets original chunks back (no error)
  - When BGE times out (default 1500ms) → fallback to original chunks
    (RRF order is preserved; caller's pipeline stays sane)
  - Wrapper instance cached at module level (per-process breaker state)
  - status() reports both adapters' state + composed wiring snapshot

COMPOSES WITH (per §49):
    services/retrieval-svc/app/services/bge_reranker.py — Stage-1 BGE
    scripts/native_compute_wrapper.py — Stage-1 wrapper
    services/retrieval-svc/app/services/reranker.py — RRF (RRF order
        preserved on fallback path)
    services/retrieval-svc/app/services/hybrid_retriever.py — caller
        site (optional hot-path wiring via BGE_RERANKER_IN_HOT_PATH)
    docs/architecture/llvm-mlir-circuit-breaker-2026-05-04.md — design
    §43 — drill discipline
    §47 — fallback path is § rule
    §52 — brutal tool review (40-row when wired into HybridRetriever)
    §56 — Stage-2 6-gate adoption process
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Wrapper timeout — BGE on a 568M-param model is ~50-200ms per query
# on a GTX 1080 Ti for 10-50 chunks. 1500ms is generous; tune down
# if production latency budget tightens.
BGE_WRAPPER_TIMEOUT_MS = int(os.getenv("BGE_WRAPPER_TIMEOUT_MS", "1500"))
BGE_WRAPPER_THRESHOLD = int(os.getenv("BGE_WRAPPER_THRESHOLD", "5"))
BGE_WRAPPER_RECOVERY_S = int(os.getenv("BGE_WRAPPER_RECOVERY_S", "60"))

# Add scripts/ to path so we can import native_compute_wrapper.
# In production this would be a proper installed package; for Stage-2
# we keep the lightweight import-by-path until the wrapper graduates.
_REPO = Path(__file__).resolve().parents[4]
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _both_opted_in() -> bool:
    """Both Stage-1 adapters must be opted-in for Stage-2 to fire."""
    return (
        os.getenv("BGE_RERANKER_ENABLED", "").strip() == "1"
        and os.getenv("NATIVE_COMPUTE_WRAPPER_ENABLED", "").strip() == "1"
    )


def _get_wrapper():
    """Lazy-load the cached wrapper instance.

    Caching is essential: a fresh wrapper per call resets the breaker
    state every request, defeating the purpose. The module-level cache
    means breaker state is per-process-lifetime, which is the correct
    granularity for a service.
    """
    if not _both_opted_in():
        return None
    if not hasattr(_get_wrapper, "_instance"):
        # Lazy imports — keep cold-start fast for callers who don't use this
        from native_compute_wrapper import NativeComputeWrapper  # noqa: PLC0415

        from app.services import bge_reranker  # noqa: PLC0415

        if not bge_reranker.is_available():
            log.info("bge_reranker_protected: BGE not available; wrapper not instantiated")
            return None

        def _native(query: str, chunks: list[dict]) -> list[dict]:
            """Native fast path — calls the BGE cross-encoder."""
            return bge_reranker.rerank(query, chunks)

        def _fallback(_query: str, chunks: list[dict]) -> list[dict]:
            """Survival path — preserve RRF order (chunks come from
            HybridRetriever which already applied RRF + min_score)."""
            log.info("bge_reranker_protected: fallback to RRF order (n=%d)", len(chunks))
            return list(chunks)

        _get_wrapper._instance = NativeComputeWrapper(  # type: ignore[attr-defined]
            name="bge_reranker",
            native_fn=_native,
            fallback_fn=_fallback,
            timeout_ms=BGE_WRAPPER_TIMEOUT_MS,
            threshold=BGE_WRAPPER_THRESHOLD,
            recovery_s=BGE_WRAPPER_RECOVERY_S,
        )
    return _get_wrapper._instance  # type: ignore[attr-defined]


def is_available() -> bool:
    """True iff BOTH BGE and wrapper are opted in AND BGE is loadable."""
    if not _both_opted_in():
        return False
    return _get_wrapper() is not None


def protected_rerank(query: str, chunks: list[dict[str, Any]], *, top_k: int | None = None) -> list[dict[str, Any]]:
    """Re-rank with BGE behind a circuit breaker; fallback to RRF order.

    Returns the original chunks list (RRF order preserved) when:
      - either Stage-1 adapter is disabled (silent pass-through; this
        is intentional Stage-2 contract — wrapper is OPT-IN)
      - BGE call exceeds BGE_WRAPPER_TIMEOUT_MS (default 1500ms)
      - BGE raises an exception (model not loaded, OOM, etc)
      - breaker is OPEN (after 5 failures, 60s recovery)

    Returns BGE-reordered chunks otherwise.

    Args:
        query: user query string
        chunks: list of dict-shaped chunks from HybridRetriever
        top_k: optional truncation after rerank (default None = all)
    """
    wrapper = _get_wrapper()
    if wrapper is None:
        # Stage-1 adapter(s) disabled — silent pass-through with RRF order
        if top_k is not None:
            return list(chunks[:top_k])
        return list(chunks)

    result = wrapper.run(query, chunks)
    log.info(
        "bge_protected path=%s native_ms=%d fallback_ms=%d ok=%s",
        result.path_taken,
        result.native_latency_ms,
        result.fallback_latency_ms,
        result.ok,
    )
    output = result.output if result.ok else list(chunks)
    if top_k is not None:
        return list(output[:top_k])
    return list(output)


def status() -> dict[str, Any]:
    """Operator status surface — composes Stage-1 BGE + Stage-1 wrapper."""
    out: dict[str, Any] = {
        "stage": 2,
        "both_opted_in": _both_opted_in(),
        "available": is_available(),
        "timeout_ms": BGE_WRAPPER_TIMEOUT_MS,
        "threshold": BGE_WRAPPER_THRESHOLD,
        "recovery_s": BGE_WRAPPER_RECOVERY_S,
        "wiring_status": (
            "stage-2 protected wrapper; HybridRetriever can invoke it "
            "as an opt-in post-RRF stage via BGE_RERANKER_IN_HOT_PATH"
        ),
        "next_stage": (
            "Stage-4 — empirical promotion: run protected hot path against "
            "RAG-test queries, compare precision/latency, then decide "
            "whether to default-enable per environment"
        ),
    }
    wrapper = _get_wrapper()
    if wrapper is not None:
        out["wrapper_status"] = wrapper.status()
    return out
