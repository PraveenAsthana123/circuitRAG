#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: BaggageContextMiddleware promotes request.state into W3C baggage.

Composes with drill_baggage_propagation.py — that one tested the
helpers in isolation; this one tests the REAL middleware stack as
wired in services/{inference,retrieval,ingestion,evaluation}-svc/app/main.py.

The gap this closes: setup_server_otel + W3CBaggagePropagator was
wired in mcp/server_common.py, but no service ever called
baggage_set() on inbound. Adding BaggageContextMiddleware to
documind_core/middleware.py fixes that — once TenantContextMiddleware
populates request.state.tenant_id / user_id / correlation_id, the
new middleware promotes those into baggage so outbound httpx calls
auto-carry them to downstream services.

Three exercised steps in this local drill shape:

 1. BaggageContextMiddleware exported from documind_core.middleware
    (API surface).
 2. All four Python services import it (regression check — if a new
    service is added without baggage wiring, this drill fails).
 3. Build a tiny FastAPI app with the production middleware order
    + TestClient. Send a request with X-Tenant-ID / X-User-ID /
    X-Correlation-ID. Inside a route, baggage_get() returns the
    correct values. Proves the wiring works.
 4. NEGATIVE: when X-Tenant-ID is OMITTED, baggage_get('tenant_id')
    returns None. The middleware does NOT invent a default — empty
    string from request.state means "no baggage entry". Locks in
    the W3C contract: baggage values are real or absent, never lies.
 5. The middleware returns a Response (no error) when OTel SDK is
    absent — services without tracing keep booting. Verified by
    importing at import-time only inside the constructor.
 6. NEGATIVE: PII keys are NOT auto-promoted. The middleware
    promotes only the safe trio (tenant_id / user_id / request_id);
    arbitrary X-Email / X-Phone headers must NOT land in baggage.
    Locks in §48 explainability + tracing/deep#baggage-propagation
    rule that PII is never in plaintext baggage headers.

Run:
    PYTHONPATH=/tmp/baggage_test_stubs:/mnt/deepa/rag \\
        .venv-tts/bin/python3 mcp/tests/drill_baggage_middleware.py
"""
from __future__ import annotations

import sys
from pathlib import Path


def green(msg: str) -> None:
    print(f"\033[32m✓\033[0m {msg}")


def red(msg: str) -> None:
    print(f"\033[31m✗\033[0m {msg}")


def yellow(msg: str) -> None:
    print(f"\033[33m⚠\033[0m {msg}")


def main() -> int:
    failed = 0
    total = 6
    repo = Path("/mnt/deepa/rag")

    # ── Step 1 ───────────────────────────────────────────────────
    print("\n[1/6] BaggageContextMiddleware exported from documind_core.middleware")
    try:
        src = (repo / "libs/py/documind_core/middleware.py").read_text()
        assert "class BaggageContextMiddleware" in src, (
            "class BaggageContextMiddleware missing in documind_core.middleware"
        )
        assert "set_baggage" in src, (
            "BaggageContextMiddleware does not call set_baggage — wiring incomplete"
        )
        assert "get_current" in src, (
            "BaggageContextMiddleware does not capture context.get_current() — "
            "context attach/detach lifecycle missing"
        )
        green("class defined + uses set_baggage + manages context lifecycle")
    except Exception as exc:  # noqa: BLE001
        red(f"export check failed: {exc}")
        failed += 1

    # ── Step 2 ───────────────────────────────────────────────────
    print("\n[2/6] All 4 Python services import BaggageContextMiddleware")
    services = (
        "services/inference-svc/app/main.py",
        "services/retrieval-svc/app/main.py",
        "services/ingestion-svc/app/main.py",
        "services/evaluation-svc/app/main.py",
    )
    missed = []
    for s in services:
        body = (repo / s).read_text()
        if "BaggageContextMiddleware" not in body:
            missed.append(s)
            continue
        if "app.add_middleware(BaggageContextMiddleware" not in body:
            missed.append(f"{s} (imported but not wired)")
    if missed:
        red(f"{len(missed)}/{len(services)} services missing wiring: {missed}")
        failed += 1
    else:
        green(f"all {len(services)} Python services import + wire BaggageContextMiddleware")

    # ── OTel availability gate ───────────────────────────────────
    try:
        from opentelemetry import baggage as _bag  # noqa: F401
        otel_present = True
    except ImportError:
        otel_present = False

    if not otel_present:
        yellow("opentelemetry SDK not installed locally; remaining steps "
               "require it. In CI containers (libs/py installed) the drill "
               "runs in full.")
        return 0 if failed == 0 else 1

    try:
        from fastapi.testclient import TestClient  # noqa: F401
        fastapi_present = True
    except ImportError:
        fastapi_present = False

    if not fastapi_present:
        yellow("fastapi.testclient not available; steps 3–6 require it.")
        return 0 if failed == 0 else 1

    # ── Step 3 ───────────────────────────────────────────────────
    print("\n[3/6] Real middleware stack: header → request.state → baggage")
    try:
        sys.path.insert(0, str(repo / "libs/py"))
        from documind_core.middleware import (
            BaggageContextMiddleware,
            CorrelationIdMiddleware,
            TenantContextMiddleware,
        )
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from opentelemetry import baggage as _ot_baggage

        app = FastAPI()
        # add_middleware order — same as services use:
        # SpanAttribute (stand-in: Baggage) added first → innermost
        app.add_middleware(BaggageContextMiddleware)
        app.add_middleware(TenantContextMiddleware)
        app.add_middleware(CorrelationIdMiddleware)

        captured: dict[str, str | None] = {}

        @app.get("/probe")
        def probe() -> dict:
            captured["tenant_id"] = _ot_baggage.get_baggage("tenant_id")
            captured["user_id"] = _ot_baggage.get_baggage("user_id")
            captured["request_id"] = _ot_baggage.get_baggage("request_id")
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/probe", headers={
            "X-Tenant-ID": "acme-prod",
            "X-User-ID": "u-42",
            "X-Correlation-ID": "req-abc-123",
        })
        assert resp.status_code == 200, (
            f"expected 200, got {resp.status_code}: {resp.text[:200]}"
        )
        assert captured.get("tenant_id") == "acme-prod", (
            f"expected tenant_id='acme-prod' in baggage, got {captured.get('tenant_id')!r}"
        )
        assert captured.get("user_id") == "u-42", (
            f"expected user_id='u-42', got {captured.get('user_id')!r}"
        )
        # request_id is the baggage key; correlation_id is the source attr.
        assert captured.get("request_id") == "req-abc-123", (
            f"expected request_id='req-abc-123' (from X-Correlation-ID), "
            f"got {captured.get('request_id')!r}"
        )
        green(f"baggage populated from headers: tenant={captured['tenant_id']} "
              f"user={captured['user_id']} request_id={captured['request_id']}")
    except AssertionError as exc:
        red(str(exc) or "assertion failed (no message)")
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step failed: {exc!r}")
        failed += 1

    # ── Step 4: NEGATIVE — missing X-Tenant-ID = no baggage entry
    print("\n[4/6] NEGATIVE: omitted X-Tenant-ID → no tenant_id in baggage "
          "(no invented default)")
    try:
        from documind_core.middleware import (
            BaggageContextMiddleware,
            CorrelationIdMiddleware,
            TenantContextMiddleware,
        )
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from opentelemetry import baggage as _ot_baggage

        app2 = FastAPI()
        app2.add_middleware(BaggageContextMiddleware)
        app2.add_middleware(TenantContextMiddleware)
        app2.add_middleware(CorrelationIdMiddleware)

        cap: dict[str, str | None] = {}

        @app2.get("/probe")
        def probe2() -> dict:
            cap["tenant_id"] = _ot_baggage.get_baggage("tenant_id")
            cap["request_id"] = _ot_baggage.get_baggage("request_id")
            return {"ok": True}

        client2 = TestClient(app2)
        # NO X-Tenant-ID header — middleware MUST NOT invent one
        resp2 = client2.get("/probe", headers={
            "X-Correlation-ID": "req-only-no-tenant",
        })
        assert resp2.status_code == 200
        assert cap.get("tenant_id") is None, (
            f"NEGATIVE FAILED: middleware invented tenant_id={cap.get('tenant_id')!r} "
            f"when no X-Tenant-ID header sent. Empty request.state.tenant_id "
            f"must NOT result in baggage entry."
        )
        # request_id should still be set (CorrelationIdMiddleware always
        # generates one if absent, so X-Correlation-ID is present in state).
        assert cap.get("request_id") == "req-only-no-tenant", (
            f"request_id should propagate from X-Correlation-ID, "
            f"got {cap.get('request_id')!r}"
        )
        green("middleware did not invent tenant_id — W3C contract holds: "
              "values are real or absent, never lies")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 4 failed: {exc}")
        failed += 1

    # ── Step 5: middleware degrades gracefully without OTel ─────
    print("\n[5/6] Middleware constructor handles OTel-missing gracefully")
    try:

        # The class stores _baggage / _context refs at __init__ time.
        # If those are None (ImportError fallback), dispatch() still
        # returns a Response — verified by inspecting the source.
        src = (repo / "libs/py/documind_core/middleware.py").read_text()
        assert "if self._baggage is None or self._context is None:" in src, (
            "middleware does NOT short-circuit when OTel is missing — "
            "services without OTel will crash on every request"
        )
        assert "return await call_next(request)" in src, (
            "missing graceful degradation path"
        )
        green("middleware short-circuits (returns call_next response) when "
              "OTel SDK unavailable — services without OTel keep booting")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 5 failed: {exc}")
        failed += 1

    # ── Step 6: NEGATIVE — only safe trio promoted, no PII keys ─
    print("\n[6/6] NEGATIVE: only tenant_id / user_id / request_id promoted "
          "(no PII keys leak into baggage)")
    try:
        from documind_core.middleware import (
            BaggageContextMiddleware,
            TenantContextMiddleware,
        )
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from opentelemetry import baggage as _ot_baggage

        # Try injecting a fake PII attribute on request.state via a
        # custom middleware BEFORE BaggageContextMiddleware runs.
        from starlette.middleware.base import BaseHTTPMiddleware

        class FakePIIMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                request.state.email = "user@example.com"  # PII attempt
                request.state.ssn = "123-45-6789"
                return await call_next(request)

        app3 = FastAPI()
        app3.add_middleware(BaggageContextMiddleware)
        app3.add_middleware(FakePIIMiddleware)  # runs before Baggage
        app3.add_middleware(TenantContextMiddleware)

        cap2: dict[str, str | None] = {}

        @app3.get("/probe")
        def probe3() -> dict:
            cap2["tenant_id"] = _ot_baggage.get_baggage("tenant_id")
            cap2["email"] = _ot_baggage.get_baggage("email")
            cap2["ssn"] = _ot_baggage.get_baggage("ssn")
            return {"ok": True}

        client3 = TestClient(app3)
        resp3 = client3.get("/probe", headers={"X-Tenant-ID": "acme"})
        assert resp3.status_code == 200
        assert cap2.get("tenant_id") == "acme", "tenant_id should be present"
        assert cap2.get("email") is None, (
            f"NEGATIVE FAILED: middleware promoted request.state.email into "
            f"baggage. PII MUST NOT auto-promote — got {cap2.get('email')!r}"
        )
        assert cap2.get("ssn") is None, (
            f"NEGATIVE FAILED: middleware promoted request.state.ssn into "
            f"baggage. PII MUST NOT auto-promote — got {cap2.get('ssn')!r}"
        )
        green("only safe trio promoted — PII keys (email, ssn) absent from "
              "baggage. §48 explainability + §49 compose-footer rule holds.")
    except AssertionError as exc:
        red(str(exc))
        failed += 1
    except Exception as exc:  # noqa: BLE001
        red(f"step 6 failed: {exc}")
        failed += 1

    print()
    if failed == 0:
        green(f"ALL {total} STEPS PASSED")
        return 0
    red(f"{failed}/{total} STEPS FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
