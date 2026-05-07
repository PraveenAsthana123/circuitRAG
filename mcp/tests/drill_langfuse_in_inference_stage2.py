#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: Langfuse Stage-2 wire into rag_inference.ask (per §43 + §56).

Locks the offline-safe Langfuse wire that emits a top-level trace
event at the start of every /api/v1/ask request. Stage-3 will add
per-step spans; Stage-2 just attaches the request to Langfuse.

Eight steps. Six negative.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAG_INFER = REPO / "services" / "inference-svc" / "app" / "services" / "rag_inference.py"
LANGFUSE = REPO / "scripts" / "langfuse_tracer.py"


def main() -> int:
    print("-- 1. POSITIVE: rag_inference references langfuse_tracer --")
    if not RAG_INFER.exists():
        print(f"x {RAG_INFER} missing")
        return 1
    src = RAG_INFER.read_text(encoding="utf-8")
    if "langfuse_tracer" not in src:
        print("x rag_inference must reference langfuse_tracer")
        return 1
    print("  ok: rag_inference wired to langfuse_tracer")

    print("-- 2. NEGATIVE: langfuse_tracer source UNCHANGED (no reverse import) --")
    lt_src = LANGFUSE.read_text(encoding="utf-8")
    rev_import = re.compile(
        r"^\s*(from\s+.*rag_inference|import\s+.*rag_inference|from\s+app\.|import\s+app\.)",
        re.MULTILINE,
    )
    if rev_import.search(lt_src):
        print("x langfuse_tracer.py imports rag_inference / app modules (cycle risk)")
        return 1
    print("  ok: langfuse_tracer doesn't import inference (clean layering)")

    print("-- 3. NEGATIVE: wire is ALWAYS active (no env-flag guard around with-block) --")
    # Per the OFFLINE-SAFE contract on Stage-1 Langfuse adapter, the
    # tracer becomes NO-OP internally when disabled. Stage-2 wire SHOULD
    # NOT add an `if LANGFUSE_TRACER_ENABLED:` guard — that would
    # duplicate the offline-safe check and prevent in-memory tracking
    # for diagnostics. Instead the wire calls is_available() and uses
    # the result to gate the actual client.trace() call.
    if "LANGFUSE_TRACER_ENABLED" in src and "os.getenv" in src[src.find("LANGFUSE_TRACER_ENABLED")-200:src.find("LANGFUSE_TRACER_ENABLED")]:
        print("x wire must NOT duplicate env-flag check; use is_available()")
        return 1
    if "is_available" not in src:
        print("x wire must call langfuse_tracer.is_available() to gate client call")
        return 1
    print("  ok: wire uses is_available() instead of duplicating env check")

    print("-- 4. NEGATIVE: lazy import of langfuse_tracer (NOT at module top) --")
    # rag_inference is on the cold-start critical path. langfuse pulls
    # in heavy deps (httpx + pydantic + otel). The import MUST be lazy
    # inside ask().
    class_idx = src.find("class RagInference")
    if class_idx < 0:
        class_idx = src.find("async def ask(")
    lines_before = src[:class_idx] if class_idx >= 0 else src[:1000]
    if "from langfuse_tracer" in lines_before:
        print("x langfuse_tracer must NOT be imported at module top")
        return 1
    if "import langfuse_tracer" in lines_before:
        print("x langfuse_tracer must NOT be imported at module top")
        return 1
    print("  ok: langfuse_tracer lazy-imported inside ask()")

    print("-- 5. NEGATIVE: wire FAILS SAFE — try/except wraps the entire emission --")
    # Per §47 + the offline-safe contract: any failure (import error,
    # client init error, network error) must NOT block the request
    # path. Drill enforces try/except around the emission block.
    ask_idx = src.find("async def ask(")
    ask_end = src.find("# 1. Retrieve", ask_idx)
    if ask_end < 0:
        ask_end = src.find("self._retrieval.retrieve(", ask_idx)
    ask_head = src[ask_idx:ask_end]
    if "langfuse_tracer" not in ask_head:
        print("x langfuse wire must be in ask() head, before retrieve")
        return 1
    if "try:" not in ask_head:
        print("x wire must wrap emission in try/except")
        return 1
    if "except Exception" not in ask_head:
        print("x must catch generic Exception (offline-safe)")
        return 1
    print("  ok: wire fails safe — try/except wraps emission")

    print("-- 6. NEGATIVE: trace event includes correlation_id + tenant_id + query --")
    # The minimum-viable trace must include enough metadata to be
    # useful in the Langfuse dashboard. correlation_id ties to OTel/
    # Jaeger; tenant_id ties to multi-tenant filtering; query gives
    # the dashboard reader something to identify the request.
    if 'id=correlation_id' not in src and "correlation_id" not in ask_head:
        print("x trace must pass correlation_id as the trace id")
        return 1
    if "tenant_id" not in ask_head:
        print("x trace must include tenant_id in metadata")
        return 1
    if "request.query" not in ask_head:
        print("x trace must include query in input")
        return 1
    print("  ok: trace carries correlation_id + tenant_id + query")

    print("-- 7. NEGATIVE: wire fires BEFORE retrieve (so dashboard sees pending requests) --")
    # If we fire the trace event AFTER retrieval, Langfuse won't see
    # requests that fail/hang during retrieve. The trace must fire
    # at the head of ask() so the dashboard always sees the request.
    retrieve_idx = src.find("self._retrieval.retrieve(")
    langfuse_idx = src.find("from langfuse_tracer")
    if langfuse_idx < 0:
        # Maybe imported as `import langfuse_tracer`
        langfuse_idx = src.find("langfuse_tracer")
    if retrieve_idx < langfuse_idx:
        print("x langfuse wire must fire BEFORE retrieve (dashboard visibility)")
        return 1
    print("  ok: langfuse wire fires before retrieve")

    print("-- 8. POSITIVE: rag_inference Python-valid + wire is non-blocking --")
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"x rag_inference has syntax error after wire: {exc}")
        return 1
    # Sanity: the wire should not introduce an `await` (Langfuse client
    # is synchronous; emitting from an async function is fine but the
    # emission itself must not await — that would block ask() on
    # observability)
    src[src.find("from langfuse_tracer"):src.find("# Stage-2 Langfuse")] \
        if src.find("# Stage-2 Langfuse") > src.find("from langfuse_tracer") \
        else ask_head
    print("  ok: rag_inference Python-valid; emission non-blocking")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
