"""Langfuse tracer — Stage-1 adapter (per CLAUDE.md §56).

Closes the OBSERVABILITY-PLANE gap from
docs/architecture/six-plane-audit-2026-05-04.md: Langfuse was
pip-installed but rag_inference.py emits no LLM traces. Stage-1
ships the adapter; Stage-2 wires into rag_inference.py per /ask.

WHY LANGFUSE (vs OTel-only):
    OTel covers infrastructure traces (HTTP / DB / queue) but doesn't
    capture LLM-specific signals: prompt content, completion content,
    token counts, model name, temperature, retrieval-context-IDs,
    user feedback. Langfuse is purpose-built for LLM observability
    with a dashboard for ops + a structured schema for offline eval.

    Composes orthogonally with existing OTel + Prometheus + Grafana.
    Same correlation_id ties Langfuse traces to Jaeger spans.

ARCHITECTURE:
    rag_inference.ask(...)
       ↓
    open Langfuse trace (correlation_id, tenant_id, user_id)
       ↓
    span: retrieve  (input=query, output=chunk-ids, latency_ms)
       ↓
    span: rerank    (input=chunks, output=ranked_ids, model=bge)
       ↓
    span: generate  (input=prompt, output=answer, model, tokens, temp)
       ↓
    end trace + flush async (no-op when offline)

Stage-1 ships:
  - LangfuseTracer wrapper (no-op when disabled or unreachable)
  - Trace context manager + span helpers
  - Lazy langfuse import + offline-safe flush

Stage-2 (next iteration):
  - Wire @trace decorator into rag_inference.ask()
  - Per-step span (retrieve / rerank / pii / generate)
  - Persist generations with model + tokens + cost

OPERATOR OPT-IN:
    LANGFUSE_TRACER_ENABLED=1
    LANGFUSE_HOST=http://localhost:3000     # self-hosted (Stage-3)
    LANGFUSE_PUBLIC_KEY=pk-lf-...
    LANGFUSE_SECRET_KEY=sk-lf-...

OFFLINE-SAFE: when host unreachable / keys unset, tracer becomes
no-op. NEVER blocks the inference path.

COMPOSES WITH (per §49):
    services/inference-svc/app/services/rag_inference.py — Stage-2 wires
        @trace into ask()
    OTel collector — same correlation_id propagated
    Grafana — dashboard reads Langfuse + Prometheus side-by-side
    docs/architecture/six-plane-audit-2026-05-04.md — observability plane
    §38 — decision audit (Langfuse trace = explainability evidence)
    §43 — drill discipline
    §48 — explainability (trace shows prompt + retrieval + answer)
    §52 — brutal tool review (40-row when wired)
    §56 — Stage-1 6-gate
"""
from __future__ import annotations

import contextlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

LANGFUSE_TRACER_ENABLED = os.getenv("LANGFUSE_TRACER_ENABLED", "").strip() == "1"
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")


class LangfuseTracerDisabled(RuntimeError):
    """Raised when force-required tracer call is made but env unset.

    NOTE: Most tracer methods are NO-OP when disabled (offline-safe).
    This exception is reserved for explicit `require_active()` calls.
    """


@dataclass
class TraceSpan:
    """One span within a trace — retrieve / rerank / generate / etc."""
    name: str
    started_at: float
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0
    ended: bool = False


@dataclass
class TraceContext:
    """Top-level trace — wraps one /api/v1/ask request."""
    correlation_id: str
    tenant_id: str
    user_id: str | None = None
    started_at: float = 0.0
    spans: list[TraceSpan] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0
    flushed: bool = False


def is_available() -> bool:
    """Stage-1 §56 default-deny check + lazy install probe.

    Returns False when:
      - LANGFUSE_TRACER_ENABLED unset
      - langfuse module not installed
      - LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY missing

    Per offline-safe contract: bare keys-missing is NOT an error;
    we just become no-op. Caller's request path never breaks.
    """
    if not LANGFUSE_TRACER_ENABLED:
        return False
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return False
    try:
        import langfuse  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def status() -> dict[str, Any]:
    """Operator status surface — same shape as other Stage-1 adapters."""
    out: dict[str, Any] = {
        "stage": 1,
        "enabled_env": LANGFUSE_TRACER_ENABLED,
        "available": is_available(),
        "host": LANGFUSE_HOST,
        "has_public_key": bool(LANGFUSE_PUBLIC_KEY),
        "has_secret_key": bool(LANGFUSE_SECRET_KEY),
        "wiring_status": "stage-1 adapter; Stage-2 wires into rag_inference.ask per /api/v1/ask",
        "next_stage": (
            "Stage-2 — wire trace_context() into rag_inference.ask() with "
            "per-step spans (retrieve / pii / rerank / generate). Capture "
            "prompt + completion + tokens + correlation_id. Offline-safe: "
            "no-op when Langfuse host unreachable."
        ),
        "offline_safe": True,
    }
    if is_available():
        try:
            import langfuse
            out["langfuse_version"] = getattr(langfuse, "__version__", "unknown")
        except Exception as exc:
            out["langfuse_probe_error"] = str(exc)
    return out


def _get_client():
    """Lazy-load Langfuse client; cached on function attribute.

    Returns None when not available — caller checks `client is None`
    and treats it as no-op. Per offline-safe contract.
    """
    if not is_available():
        return None
    if not hasattr(_get_client, "_cached"):
        try:
            from langfuse import Langfuse  # noqa: PLC0415
            _get_client._cached = Langfuse(  # type: ignore[attr-defined]
                public_key=LANGFUSE_PUBLIC_KEY,
                secret_key=LANGFUSE_SECRET_KEY,
                host=LANGFUSE_HOST,
            )
        except Exception as exc:
            log.warning("langfuse_client_init failed: %s", exc)
            _get_client._cached = None  # type: ignore[attr-defined]
    return _get_client._cached  # type: ignore[attr-defined]


@contextlib.contextmanager
def trace_context(
    *,
    correlation_id: str,
    tenant_id: str,
    user_id: str | None = None,
    name: str = "rag.ask",
):
    """Context manager wrapping one /api/v1/ask request.

    Usage:
        with trace_context(correlation_id=cid, tenant_id=t) as ctx:
            with span(ctx, "retrieve", inputs={"query": q}) as sp:
                chunks = retrieve(q)
                sp.outputs["chunk_count"] = len(chunks)
            ...

    Offline-safe: if Langfuse client unavailable, the context still
    creates a TraceContext for in-memory tracking but never sends
    over the wire. Caller's rag_inference.ask() path never breaks.
    """
    ctx = TraceContext(
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        user_id=user_id,
        started_at=time.monotonic(),
    )
    try:
        yield ctx
    finally:
        ctx.elapsed_ms = int((time.monotonic() - ctx.started_at) * 1000)
        # Async flush — never blocks the request path
        client = _get_client()
        if client is not None:
            try:
                client.trace(
                    id=ctx.correlation_id,
                    name=name,
                    user_id=ctx.user_id,
                    metadata={
                        "tenant_id": ctx.tenant_id,
                        "elapsed_ms": ctx.elapsed_ms,
                        "span_count": len(ctx.spans),
                        **ctx.metadata,
                    },
                )
                # Per-span emission. Langfuse SDK auto-batches; we just
                # call .span() per recorded span.
                for sp in ctx.spans:
                    client.span(
                        trace_id=ctx.correlation_id,
                        name=sp.name,
                        input=sp.inputs,
                        output=sp.outputs,
                        metadata={
                            "elapsed_ms": sp.elapsed_ms,
                            **sp.metadata,
                        },
                    )
                ctx.flushed = True
            except Exception as exc:
                # Offline-safe: never break the request path on
                # observability flush.
                log.warning("langfuse_flush_failed cid=%s: %s",
                            ctx.correlation_id, exc)


@contextlib.contextmanager
def span(ctx: TraceContext, name: str, *, inputs: dict[str, Any] | None = None):
    """Span context manager — wraps a sub-step within a trace.

    Usage:
        with span(ctx, "retrieve", inputs={"query": q}) as sp:
            chunks = retrieve(q)
            sp.outputs["chunk_count"] = len(chunks)
            sp.metadata["latency_ms"] = elapsed
    """
    sp = TraceSpan(
        name=name,
        started_at=time.monotonic(),
        inputs=dict(inputs or {}),
    )
    try:
        yield sp
    finally:
        sp.elapsed_ms = int((time.monotonic() - sp.started_at) * 1000)
        sp.ended = True
        ctx.spans.append(sp)


def require_active() -> None:
    """Strict check — raises if tracer not available.

    For callers who NEED tracing (audit-required code paths). Most
    inference-side callers should use is_available() + offline-safe
    no-op pattern instead.
    """
    if not is_available():
        raise LangfuseTracerDisabled(
            "Langfuse tracer not available. Set LANGFUSE_TRACER_ENABLED=1 + "
            "LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY + ensure langfuse "
            "is installed."
        )


if __name__ == "__main__":
    import json
    import sys
    print("scripts/langfuse_tracer.py — Stage-1 Langfuse LLM observability")
    print(f"Stage-1 opt-in via LANGFUSE_TRACER_ENABLED=1 (+ keys)")
    print("Offline-safe: no-op when host/keys unavailable.")
    print()
    print(json.dumps(status(), indent=2))
    sys.exit(0)
