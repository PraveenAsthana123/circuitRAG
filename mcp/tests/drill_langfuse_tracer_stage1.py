#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Langfuse tracer Stage-1 (per §43 + §56).

Locks the Stage-1 LLM observability adapter that:
  - exists at scripts/langfuse_tracer.py
  - 7 contract surfaces: is_available, status, trace_context, span,
    require_active, TraceContext, TraceSpan, LangfuseTracerDisabled
  - Offline-safe: NO-OP when host unreachable / keys missing
  - Default-deny: LANGFUSE_TRACER_ENABLED + keys required
  - Lazy langfuse import (heavy)
  - rag_inference.py UNCHANGED (Stage-2 wires)

Eight steps. Six negative.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADAPTER = REPO / "scripts" / "langfuse_tracer.py"
RAG_INFER = REPO / "services" / "inference-svc" / "app" / "services" / "rag_inference.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod, spec


def main() -> int:
    print("-- 1. POSITIVE: langfuse_tracer.py exists + non-trivial size --")
    if not ADAPTER.exists():
        print(f"x {ADAPTER} missing")
        return 1
    src = ADAPTER.read_text(encoding="utf-8")
    if len(src) < 5000:
        print(f"x langfuse_tracer too short ({len(src)} chars)")
        return 1
    print(f"  ok: langfuse_tracer present ({len(src)} chars)")

    print("-- 2. NEGATIVE: rag_inference.py UNCHANGED (Stage-2 wires) --")
    if RAG_INFER.exists():
        ri_src = RAG_INFER.read_text(encoding="utf-8")
        if "langfuse_tracer" in ri_src or "trace_context" in ri_src:
            print("x rag_inference has Langfuse wire — Stage-2 hasn't landed")
            return 1
    print("  ok: rag_inference unchanged (Stage-1 purely additive)")

    print("-- 3. POSITIVE: 8 contract surfaces exported --")
    os.environ.pop("LANGFUSE_TRACER_ENABLED", None)
    mod, spec = _load_module(ADAPTER)
    for name in ("is_available", "status", "trace_context", "span",
                 "require_active", "TraceContext", "TraceSpan",
                 "LangfuseTracerDisabled"):
        if not hasattr(mod, name):
            print(f"x langfuse_tracer.{name} missing")
            return 1
    print("  ok: 8 surfaces exported")

    print("-- 4. NEGATIVE: default-deny on require_active() (when env unset) --")
    os.environ.pop("LANGFUSE_TRACER_ENABLED", None)
    spec.loader.exec_module(mod)
    raised = False
    try:
        mod.require_active()
    except mod.LangfuseTracerDisabled as exc:
        raised = True
        if "LANGFUSE_TRACER_ENABLED" not in str(exc):
            print(f"x error msg must cite env flag; got: {exc}")
            return 1
    if not raised:
        print("x require_active() should raise when flag off")
        return 1
    print("  ok: require_active() default-deny preserved")

    print("-- 5. NEGATIVE: trace_context is OFFLINE-SAFE (NO raise when disabled) --")
    # Per the offline-safe contract: trace_context + span MUST be no-op
    # when adapter unavailable. Otherwise wiring into rag_inference
    # would be unsafe (every disabled deployment would crash on /ask).
    os.environ.pop("LANGFUSE_TRACER_ENABLED", None)
    spec.loader.exec_module(mod)
    raised_ctx = False
    try:
        with mod.trace_context(correlation_id="cid", tenant_id="t") as ctx:
            with mod.span(ctx, "test_step", inputs={"q": "x"}) as sp:
                sp.outputs["count"] = 1
    except Exception as exc:
        raised_ctx = True
        print(f"x trace_context must be NO-OP when disabled; raised: {exc}")
        return 1
    if raised_ctx:
        return 1
    # Verify the in-memory TraceContext was still populated (caller can
    # inspect it even when offline)
    if not isinstance(ctx, mod.TraceContext):
        print("x trace_context must yield TraceContext even when offline")
        return 1
    if len(ctx.spans) != 1:
        print(f"x span tracking must work offline; got {len(ctx.spans)} spans")
        return 1
    print("  ok: trace_context + span are offline-safe (NO-OP, no raise)")

    print("-- 6. NEGATIVE: lazy langfuse import (NOT at module top) --")
    # langfuse pulls in httpx, pydantic, opentelemetry. Module top
    # stays light; client loaded inside _get_client() on first call.
    lines_before_def = src[:src.find("def is_available")]
    if re.search(r"^import langfuse\b", lines_before_def, re.MULTILINE):
        print("x langfuse must NOT be imported at module top")
        return 1
    if re.search(r"^from langfuse\b", lines_before_def, re.MULTILINE):
        print("x langfuse must NOT be 'from'-imported at module top")
        return 1
    print("  ok: langfuse lazy-imported")

    print("-- 7. NEGATIVE: missing keys → is_available()=False (no crash) --")
    # Per offline-safe: keys missing must return False, NOT raise.
    # Set env flag but leave keys empty.
    os.environ["LANGFUSE_TRACER_ENABLED"] = "1"
    os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
    os.environ.pop("LANGFUSE_SECRET_KEY", None)
    spec.loader.exec_module(mod)
    if mod.is_available():
        print("x is_available() must be False when keys missing")
        return 1
    # Confirm trace_context still no-ops (doesn't crash)
    raised_keys = False
    try:
        with mod.trace_context(correlation_id="c", tenant_id="t") as ctx:
            pass
    except Exception:
        raised_keys = True
    if raised_keys:
        print("x trace_context must NO-OP when keys missing (not raise)")
        return 1
    print("  ok: missing keys → is_available()=False + trace_context still NO-OP")

    print("-- 8. POSITIVE: status() reports stage=1 + offline_safe=True + Stage-2 path --")
    s = mod.status()
    if s.get("stage") != 1:
        print(f"x stage must be 1; got {s.get('stage')}")
        return 1
    if not s.get("offline_safe"):
        print("x status must declare offline_safe=True")
        return 1
    for key in ("enabled_env", "available", "host", "has_public_key",
                "has_secret_key", "wiring_status", "next_stage"):
        if key not in s:
            print(f"x status missing key: {key}")
            return 1
    if "Stage-2" not in s["next_stage"]:
        print("x next_stage must reference Stage-2")
        return 1
    if "rag_inference" not in s["next_stage"]:
        print("x next_stage must mention rag_inference (Stage-2 wiring site)")
        return 1
    print("  ok: status reports stage=1 + offline_safe=True + Stage-2 path")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
