#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: W3C trace context + baggage propagation across service boundaries.

User explicitly flagged this gap:
  "check the logs ..service 1 to service 2 baggage concept missing"
  "pass some value in header of the request then go to next service
   from header it will pick. it will create chain of request"

The fix in mcp/server_common.py:
  * Set global propagator to CompositePropagator(traceparent, baggage)
  * Auto-instrument httpx (outbound inject)
  * Expose baggage_set / baggage_get / inject / extract helpers

This drill proves the contract WITHOUT requiring the full app stack:
runs in-process, uses W3C inject/extract directly against a carrier
dict (the same shape that becomes HTTP request headers).

Three exercised steps in this local drill shape:

 1. server_common exports baggage_set / baggage_get / inject /
    extract helpers (API surface).
 2. setup_server_otel idempotent: second call does NOT raise.
 3. baggage_set then baggage_get round-trips a value
    (current-context contract).
 4. inject_propagation_headers writes a 'traceparent' header
    AND a 'baggage' header to the carrier dict (W3C compliance).
 5. extract_propagation_context on a fresh carrier RECONSTRUCTS the
    baggage in the new context — proves cross-service propagation.
 6. NEGATIVE: a service that never called extract MUST see ZERO
    baggage. Without explicit propagation there is no 'magic'
    transfer. Locks in the W3C contract: baggage requires HTTP
    header → extract step.
 7. NEGATIVE: 'baggage' header value MUST be percent-encoded for
    non-ASCII. UTF-8 chars get URL-encoded; raw bytes are forbidden.
 8. NEGATIVE: setting baggage in a CHILD context does NOT leak back
    to the parent (context isolation per OTel).

Run:
    python3 mcp/tests/drill_baggage_propagation.py
"""
from __future__ import annotations

import sys


def green(msg: str) -> None:
    print(f"\033[32m✓\033[0m {msg}")


def red(msg: str) -> None:
    print(f"\033[31m✗\033[0m {msg}")


def yellow(msg: str) -> None:
    print(f"\033[33m⚠\033[0m {msg}")


def main() -> int:
    failed = 0
    total = 8

    # ── Step 1 ───────────────────────────────────────────────────
    # Source-text scan instead of import so this passes even without
    # documind_core / OTel installed locally. CI containers run the
    # full import path in steps 2+.
    print("\n[1/8] server_common exports baggage helpers (source scan)")
    try:
        import re
        from pathlib import Path

        src_path = Path("/mnt/deepa/rag/mcp/server_common.py")
        src = src_path.read_text()
        required = (
            "baggage_set",
            "baggage_get",
            "baggage_get_all",
            "inject_propagation_headers",
            "extract_propagation_context",
        )
        for name in required:
            # Function defined?
            assert re.search(rf"^def {name}\b", src, re.MULTILINE), (
                f"server_common.py missing 'def {name}'"
            )
            # In __all__?
            all_match = re.search(r"__all__\s*=\s*\[(.*?)\]", src, re.DOTALL)
            assert all_match, "no __all__ in server_common.py"
            assert f'"{name}"' in all_match.group(1), (
                f"{name!r} not listed in __all__"
            )
        # Propagator wired?
        assert "set_global_textmap" in src, (
            "set_global_textmap call missing — propagator not wired"
        )
        assert "CompositePropagator" in src, (
            "CompositePropagator missing — only tracecontext OR baggage, not both"
        )
        assert "W3CBaggagePropagator" in src, (
            "W3CBaggagePropagator missing — baggage header will not be emitted"
        )
        assert "HTTPXClientInstrumentor" in src, (
            "HTTPXClientInstrumentor missing — outbound httpx will not "
            "auto-inject traceparent + baggage"
        )
        green("all 5 helper exports + propagator + httpx instrumentor wired")
    except Exception as exc:  # noqa: BLE001
        red(f"export check failed: {exc}")
        failed += 1

    # ── OTel availability gate ───────────────────────────────────
    try:
        from opentelemetry import trace as _t  # noqa: F401
        otel_present = True
    except ImportError:
        otel_present = False

    if not otel_present:
        yellow("opentelemetry SDK not installed locally — remaining "
               "steps require the SDK. Skipping with neutral exit. "
               "In a service container (libs/py installed), the "
               "drill runs in full.")
        # Don't fail CI on local laptop without venv — but DO fail
        # if step 1 (pure-Python API surface) regressed.
        return 0 if failed == 0 else 1

    # ── Step 2 ───────────────────────────────────────────────────
    print("\n[2/8] setup_server_otel is idempotent (second call no-op)")
    try:
        from fastapi import FastAPI

        from mcp.server_common import setup_server_otel

        app1 = FastAPI()
        app2 = FastAPI()
        setup_server_otel(app1, service_name="drill-svc-1")
        setup_server_otel(app2, service_name="drill-svc-2")  # second call
        green("setup_server_otel ran twice without raising — idempotent")
    except Exception as exc:  # noqa: BLE001
        red(f"idempotency failed: {exc}")
        failed += 1

    # ── Step 3 ───────────────────────────────────────────────────
    print("\n[3/8] baggage_set → baggage_get round-trip")
    try:
        from opentelemetry import context as _ctx

        from mcp.server_common import baggage_get, baggage_set

        token = baggage_set("tenant_id", "acme-prod")
        got = baggage_get("tenant_id")
        assert got == "acme-prod", f"expected acme-prod, got {got!r}"
        # cleanup so later steps start fresh
        if token is not None:
            _ctx.detach(token)
        green("baggage_set('tenant_id', 'acme-prod') → baggage_get == 'acme-prod'")
    except Exception as exc:  # noqa: BLE001
        red(f"round-trip failed: {exc}")
        failed += 1

    # ── Step 4 ───────────────────────────────────────────────────
    print("\n[4/8] inject_propagation_headers writes traceparent + baggage")
    try:
        from opentelemetry import context as _ctx
        from opentelemetry import trace as _tr

        from mcp.server_common import baggage_set, inject_propagation_headers

        tracer = _tr.get_tracer("drill")
        with tracer.start_as_current_span("svc-A.handle_request"):
            tok = baggage_set("tenant_id", "acme-prod")
            tok2 = baggage_set("request_id", "req-abc-123")
            carrier: dict[str, str] = {}
            inject_propagation_headers(carrier)
            # Lower-case header names (W3C convention; HTTP/2 enforces).
            keys = {k.lower() for k in carrier.keys()}
            assert "traceparent" in keys, (
                f"traceparent header MISSING from carrier {carrier!r}"
            )
            assert "baggage" in keys, (
                f"baggage header MISSING from carrier {carrier!r}"
            )
            # Value must contain both entries
            bag_val = next(v for k, v in carrier.items()
                           if k.lower() == "baggage")
            assert "tenant_id=acme-prod" in bag_val, (
                f"tenant_id missing from baggage value: {bag_val!r}"
            )
            assert "request_id=req-abc-123" in bag_val, (
                f"request_id missing from baggage value: {bag_val!r}"
            )
            for t in (tok, tok2):
                if t is not None:
                    _ctx.detach(t)
        green(f"carrier carried traceparent + baggage; "
              f"baggage value = {bag_val!r}")
    except Exception as exc:  # noqa: BLE001
        red(f"inject failed: {exc}")
        failed += 1

    # ── Step 5 ───────────────────────────────────────────────────
    print("\n[5/8] extract_propagation_context reconstructs baggage in svc-B")
    try:
        from opentelemetry import context as _ctx
        from opentelemetry import trace as _tr

        from mcp.server_common import (
            baggage_get,
            baggage_set,
            extract_propagation_context,
            inject_propagation_headers,
        )

        # Service A: set baggage + inject into carrier
        tracer = _tr.get_tracer("drill")
        with tracer.start_as_current_span("svc-A.handle_request"):
            tok = baggage_set("tenant_id", "acme-prod")
            tok2 = baggage_set("user_id", "user-42")
            carrier: dict[str, str] = {}
            inject_propagation_headers(carrier)
            for t in (tok, tok2):
                if t is not None:
                    _ctx.detach(t)

        # Service B: receive carrier, extract → context
        # (simulates inbound HTTP request landing on next service)
        b_token = extract_propagation_context(carrier)
        try:
            assert baggage_get("tenant_id") == "acme-prod", (
                f"tenant_id NOT propagated: got {baggage_get('tenant_id')!r}"
            )
            assert baggage_get("user_id") == "user-42", (
                f"user_id NOT propagated: got {baggage_get('user_id')!r}"
            )
            green("svc-B sees tenant_id=acme-prod and user_id=user-42 "
                  "from extracted carrier — chain proven")
        finally:
            if b_token is not None:
                _ctx.detach(b_token)
    except Exception as exc:  # noqa: BLE001
        red(f"extract chain failed: {exc}")
        failed += 1

    # ── Step 6: NEGATIVE — no extract = no baggage ───────────────
    print("\n[6/8] NEGATIVE: service that skips extract sees ZERO baggage")
    try:
        from mcp.server_common import baggage_get, baggage_get_all

        # Fresh context — no baggage_set, no extract
        # baggage_get and baggage_get_all should return None / {}
        got = baggage_get("tenant_id")
        all_b = baggage_get_all()
        assert got is None, (
            f"NEGATIVE FAILED: tenant_id leaked into a service "
            f"that did NOT extract: got={got!r}"
        )
        assert all_b == {}, (
            f"NEGATIVE FAILED: baggage leaked into a service "
            f"that did NOT extract: all={all_b!r}"
        )
        green("service that did not extract → zero baggage. "
              "W3C contract holds: explicit extract required.")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 6 failed: {exc}")
        failed += 1

    # ── Step 7: NEGATIVE — non-ASCII baggage URL-encoded ─────────
    print("\n[7/8] NEGATIVE: non-ASCII baggage value is percent-encoded")
    try:
        from opentelemetry import context as _ctx
        from opentelemetry import trace as _tr

        from mcp.server_common import baggage_set, inject_propagation_headers

        tracer = _tr.get_tracer("drill")
        with tracer.start_as_current_span("svc-A.utf8"):
            # Japanese chars — must be percent-encoded per W3C baggage spec
            tok = baggage_set("region", "東京")
            carrier: dict[str, str] = {}
            inject_propagation_headers(carrier)
            bag_val = next(v for k, v in carrier.items()
                           if k.lower() == "baggage")
            # Must NOT contain raw multibyte UTF-8 (HTTP headers are
            # ASCII-only per RFC 7230). Must contain a percent-encoded
            # token.
            assert "東京" not in bag_val, (
                f"NEGATIVE FAILED: raw multibyte UTF-8 leaked into "
                f"baggage header: {bag_val!r}. HTTP headers MUST be "
                f"ASCII; baggage values must be percent-encoded."
            )
            # Percent-encoded form should appear (e.g. %E6%9D%B1%E4%BA%AC)
            assert "%" in bag_val, (
                f"NEGATIVE FAILED: expected percent-encoding for non-ASCII; "
                f"got {bag_val!r}"
            )
            if tok is not None:
                _ctx.detach(tok)
        green(f"non-ASCII value percent-encoded in header — "
              f"W3C compliance: {bag_val!r}")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 7 failed: {exc}")
        failed += 1

    # ── Step 8: NEGATIVE — child baggage does not leak to parent ─
    print("\n[8/8] NEGATIVE: child-context baggage does not leak to parent")
    try:
        from opentelemetry import baggage as _bag
        from opentelemetry import context as _ctx

        # Parent context: empty.
        parent_baggage_before = dict(_bag.get_all())
        assert "child_only" not in parent_baggage_before, (
            "test setup wrong — parent context already has 'child_only'"
        )

        # Set baggage in a CHILD context (don't attach).
        child_ctx = _bag.set_baggage("child_only", "yes")
        # In child_ctx, the value exists; in current context it does not.
        assert _bag.get_baggage("child_only", context=child_ctx) == "yes"
        # CRITICAL negative: the global / parent context was NOT mutated.
        assert _bag.get_baggage("child_only") is None, (
            f"NEGATIVE FAILED: child baggage leaked to parent context "
            f"without explicit attach. Got "
            f"{_bag.get_baggage('child_only')!r}"
        )
        green("child-context baggage isolated from parent — "
              "OTel context immutability holds")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 8 failed: {exc}")
        failed += 1

    # ── Summary ──────────────────────────────────────────────────
    print()
    if failed == 0:
        green(f"ALL {total} STEPS PASSED")
        return 0
    red(f"{failed}/{total} STEPS FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
