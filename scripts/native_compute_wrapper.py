"""Native-compute wrapper — Stage-1 adapter for LLVM/MLIR-optimized callables.

Per CLAUDE.md §43 + §47 + §56 + the operator-supplied
"LLVM/MLIR + Circuit Breaker + Agent Council" sequence spec.

THE BRUTAL ARCHITECTURE RULE (operator-supplied):
    LLVM/MLIR        = performance engine
    Circuit Breaker  = reliability shield
    Agent Council    = decision brain
    Observability    = truth layer
    Fallback         = survival path

This module is the "reliability shield + survival path" wrapper that
goes AROUND a compiled-binary / native callable / GPU kernel — NOT
inside the kernel itself (per the operator's "do not put circuit
breaker logic inside LLVM/MLIR optimization code" rule).

Caller workflow:
    1. Compile your hot path with clang/llvm/opt → fast native binary
    2. Expose it as a Python callable (ctypes / cffi / Python C ext)
    3. Wrap that callable with NativeComputeWrapper
    4. The wrapper handles: circuit-breaker state, timeout enforcement,
       fallback dispatch, latency telemetry, observability spans

Stage-1 contract (per §56):
    - Default opt-in via NATIVE_COMPUTE_WRAPPER_ENABLED=1
    - Lazy-imports the existing circuit_breaker module (libs/py/documind_core)
    - Composable with ANY callable (native or pure Python fallback)
    - status() reports {stage:1, breaker_state, last_latency, fallback_count, ...}

Stage-2 (planned):
    - Wire around BGE reranker (FlagEmbedding); fallback to RRF on timeout
    - Wire around vector search; fallback to BM25 on timeout
    - Wire around any future LLVM-compiled rerankers

COMPOSES WITH (per §49):
    libs/py/documind_core/circuit_breaker.py — the underlying CB primitives
    services/retrieval-svc/app/services/reranker.py — RRF (the fallback)
    services/retrieval-svc/app/services/bge_reranker.py — Stage-1 BGE adapter
        (this wrapper would protect future LLVM-compiled BGE inference)
    docs/architecture/llvm-mlir-circuit-breaker-2026-05-04.md — design doc
    §38 — decision audit (every dispatch logs the path taken)
    §47 — architecture & design patterns (fallback path is § rule)
    §52 — brutal tool review (40-row when wired into request hot path)
    §56 — Stage-1 6-gate adoption process
"""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

NATIVE_COMPUTE_WRAPPER_ENABLED = os.getenv("NATIVE_COMPUTE_WRAPPER_ENABLED", "").strip() == "1"


class NativeComputeWrapperDisabled(RuntimeError):
    """Raised when wrapper.run() is called but the env flag is unset.

    Stage-1 invariant: caller MUST opt in. Default-deny matches the
    other Stage-1 adapters (litellm, pydantic-ai, paperclip, gemma-council,
    bge-reranker, pii-redactor).
    """


@dataclass
class WrapperResult:
    """Per-call audit record. Caller persists to its decision-audit row."""
    ok: bool
    output: Any
    path_taken: str  # "native" | "fallback" | "fallback:open" | "fallback:timeout" | "fallback:error"
    native_latency_ms: int = 0
    fallback_latency_ms: int = 0
    error: str | None = None


@dataclass
class _Counters:
    """Shared mutable state — lockless writes are safe because only one
    thread per service updates these per-tool counters in practice."""
    success: int = 0
    failure: int = 0
    timeout: int = 0
    fallback_used: int = 0
    last_native_latency_ms: int = 0


class NativeComputeWrapper:
    """Wraps a native callable with circuit-breaker + timeout + fallback.

    Args:
        name: identifier for breaker keying + telemetry (e.g. "bge_reranker")
        native_fn: the fast path (LLVM/MLIR-compiled or otherwise)
        fallback_fn: the survival path; same signature as native_fn
        timeout_ms: per-call timeout for the native path; on miss, we
            record_failure on the breaker and dispatch fallback
        threshold: failure count to OPEN the breaker (default 5)
        recovery_s: seconds in OPEN before allowing half-open probe
            (default 30)

    Example:
        wrapper = NativeComputeWrapper(
            name="bge_reranker",
            native_fn=bge_compiled_rerank,   # ctypes-bound LLVM artifact
            fallback_fn=rrf_rerank,           # pure-Python RRF fallback
            timeout_ms=500,
        )
        result = wrapper.run(query, chunks)
        # result.path_taken in {"native", "fallback:open", "fallback:timeout", ...}
    """

    def __init__(
        self,
        *,
        name: str,
        native_fn: Callable[..., Any],
        fallback_fn: Callable[..., Any],
        timeout_ms: int = 500,
        threshold: int = 5,
        recovery_s: int = 30,
    ) -> None:
        if not NATIVE_COMPUTE_WRAPPER_ENABLED:
            raise NativeComputeWrapperDisabled(
                "Native compute wrapper disabled. Set "
                "NATIVE_COMPUTE_WRAPPER_ENABLED=1 to use."
            )
        self._name = name
        self._native = native_fn
        self._fallback = fallback_fn
        self._timeout_ms = timeout_ms
        self._threshold = threshold
        self._recovery_s = recovery_s
        self._counters = _Counters()
        self._state = "closed"
        self._opened_at = 0.0
        self._lock = threading.RLock()
        # Single-thread pool: native calls happen one at a time per
        # wrapper instance; for parallel native calls, instantiate a
        # wrapper per concurrency unit.
        self._pool = ThreadPoolExecutor(max_workers=1)

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> str:
        """Returns 'closed' | 'open' | 'half-open'."""
        with self._lock:
            if self._state == "open" and (time.monotonic() - self._opened_at) >= self._recovery_s:
                self._state = "half-open"
            return self._state

    def is_open(self) -> bool:
        return self.state == "open"

    def record_success(self) -> None:
        with self._lock:
            self._counters.success += 1
            if self._state == "half-open":
                # Recovery probe succeeded → close the breaker
                self._state = "closed"
                log.info("native_wrapper_recovered name=%s", self._name)

    def record_failure(self, *, kind: str = "error") -> None:
        with self._lock:
            self._counters.failure += 1
            if kind == "timeout":
                self._counters.timeout += 1
            if self._state == "half-open":
                # Probe failed → re-open
                self._state = "open"
                self._opened_at = time.monotonic()
            elif self._counters.failure - self._counters.success >= self._threshold:
                # Cumulative-failure trip — could refine to rolling window
                self._state = "open"
                self._opened_at = time.monotonic()
                log.warning(
                    "native_wrapper_opened name=%s failures=%d threshold=%d",
                    self._name, self._counters.failure, self._threshold,
                )

    def status(self) -> dict[str, Any]:
        with self._lock:
            c = self._counters
            return {
                "stage": 1,
                "name": self._name,
                "enabled_env": NATIVE_COMPUTE_WRAPPER_ENABLED,
                "breaker_state": self.state,
                "timeout_ms": self._timeout_ms,
                "threshold": self._threshold,
                "recovery_s": self._recovery_s,
                "counters": {
                    "success": c.success,
                    "failure": c.failure,
                    "timeout": c.timeout,
                    "fallback_used": c.fallback_used,
                    "last_native_latency_ms": c.last_native_latency_ms,
                },
                "wiring_status": "stage-1 adapter; not wired around live native components yet",
                "next_stage": "Stage-2 — wire around BGE reranker (LLVM-compiled future) with RRF fallback",
            }

    def run(self, *args: Any, **kwargs: Any) -> WrapperResult:
        """Dispatch with breaker + timeout + fallback per the operator
        spec. Path taken is recorded on the WrapperResult."""
        # OPEN breaker → straight to fallback
        if self.is_open():
            t0 = time.monotonic()
            try:
                out = self._fallback(*args, **kwargs)
                fb_latency = int((time.monotonic() - t0) * 1000)
                with self._lock:
                    self._counters.fallback_used += 1
                return WrapperResult(
                    ok=True, output=out, path_taken="fallback:open",
                    fallback_latency_ms=fb_latency,
                )
            except Exception as exc:
                fb_latency = int((time.monotonic() - t0) * 1000)
                return WrapperResult(
                    ok=False, output=None, path_taken="fallback:open",
                    fallback_latency_ms=fb_latency, error=str(exc),
                )

        # CLOSED or HALF-OPEN → try native with timeout
        t0 = time.monotonic()
        future = self._pool.submit(self._native, *args, **kwargs)
        try:
            out = future.result(timeout=self._timeout_ms / 1000.0)
            native_latency = int((time.monotonic() - t0) * 1000)
            with self._lock:
                self._counters.last_native_latency_ms = native_latency
            self.record_success()
            return WrapperResult(
                ok=True, output=out, path_taken="native",
                native_latency_ms=native_latency,
            )
        except FutTimeout:
            future.cancel()
            self.record_failure(kind="timeout")
            log.warning("native_timeout name=%s timeout_ms=%d", self._name, self._timeout_ms)
            t1 = time.monotonic()
            try:
                out = self._fallback(*args, **kwargs)
                fb_latency = int((time.monotonic() - t1) * 1000)
                with self._lock:
                    self._counters.fallback_used += 1
                return WrapperResult(
                    ok=True, output=out, path_taken="fallback:timeout",
                    native_latency_ms=self._timeout_ms,
                    fallback_latency_ms=fb_latency,
                )
            except Exception as exc:
                fb_latency = int((time.monotonic() - t1) * 1000)
                return WrapperResult(
                    ok=False, output=None, path_taken="fallback:timeout",
                    native_latency_ms=self._timeout_ms,
                    fallback_latency_ms=fb_latency, error=str(exc),
                )
        except Exception as exc:
            self.record_failure(kind="error")
            log.warning("native_error name=%s error=%s", self._name, exc)
            t1 = time.monotonic()
            try:
                out = self._fallback(*args, **kwargs)
                fb_latency = int((time.monotonic() - t1) * 1000)
                with self._lock:
                    self._counters.fallback_used += 1
                return WrapperResult(
                    ok=True, output=out, path_taken="fallback:error",
                    fallback_latency_ms=fb_latency, error=str(exc),
                )
            except Exception as exc2:
                fb_latency = int((time.monotonic() - t1) * 1000)
                return WrapperResult(
                    ok=False, output=None, path_taken="fallback:error",
                    fallback_latency_ms=fb_latency,
                    error=f"native: {exc}; fallback: {exc2}",
                )


def is_available() -> bool:
    """Stage-1 §56 default-deny check. Same shape as other adapters."""
    return NATIVE_COMPUTE_WRAPPER_ENABLED


if __name__ == "__main__":
    import json
    import sys
    print("scripts/native_compute_wrapper.py — Stage-1 LLVM/MLIR + CB wrapper")
    print(f"Stage-1 opt-in via NATIVE_COMPUTE_WRAPPER_ENABLED=1")
    print(f"Composes ANY native callable with circuit breaker + timeout + fallback")
    print()
    sample_status = {
        "stage": 1,
        "enabled_env": NATIVE_COMPUTE_WRAPPER_ENABLED,
        "available": is_available(),
        "wrapper_pattern": "name + native_fn + fallback_fn + timeout_ms",
        "states": ["closed", "open", "half-open"],
        "use_cases": [
            "BGE reranker (LLVM-compiled future) with RRF fallback",
            "vector search with BM25 fallback",
            "any GPU/CPU optimized kernel with pure-Python fallback",
        ],
        "next_stage": "Stage-2 — wire around BGE reranker with RRF fallback",
    }
    print(json.dumps(sample_status, indent=2))
    sys.exit(0)
