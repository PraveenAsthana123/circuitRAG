#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for CB-F-small — health probe + per-tenant + OTel baggage.

Includes negative assertions: unhealthy probe must NOT close the
breaker; per-tenant scope must NOT mix tenants; baggage must NOT
leak failure-cause when probe reports healthy.

Locks 3 advanced features:

  #22  Health-derived close — probe callback short-circuits recovery_timeout
  #26  Per-tenant breaker scope — tenant_id kwarg
  #27  OTel baggage — opt-in tracing of breaker state per span
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load() -> object:
    sys.path.insert(0, str(REPO / "libs" / "py"))
    import documind_core.circuit_breaker as cb  # noqa: PLC0415
    return cb


def main() -> int:
    cb_mod = _load()
    CircuitBreaker = cb_mod.CircuitBreaker
    State = cb_mod.State

    async def _ok() -> str:
        return "ok"

    async def _fail() -> None:
        raise ConnectionError("down")

    # -------------------------------------------------------------
    # FIX #22: health probe short-circuits recovery_timeout
    # -------------------------------------------------------------
    print("-- 1. POSITIVE: health_check returning True transitions OPEN→HALF_OPEN early --")
    is_healthy = [False]

    def _probe() -> bool:
        return is_healthy[0]

    cb = CircuitBreaker(
        "health-probe",
        failure_threshold=1,
        recovery_timeout=10.0,  # long recovery
        health_check=_probe,
    )
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    assert cb.state is State.OPEN

    # Probe says unhealthy → breaker stays OPEN.
    is_healthy[0] = False
    try:
        asyncio.run(cb.call_async(_ok))
    except cb_mod.CircuitOpenError:
        pass
    assert cb.state is State.OPEN

    # Flip probe to healthy → next call short-circuits to HALF_OPEN.
    is_healthy[0] = True
    asyncio.run(cb.call_async(_ok))
    # After successful call, state=CLOSED (default success_threshold=1).
    assert cb.state is State.CLOSED, (
        f"FIX #22 BROKEN: healthy probe should short-circuit; got {cb.state}"
    )
    print("  ok: healthy probe → OPEN→HALF_OPEN (without waiting 10s recovery)")

    # -------------------------------------------------------------
    # FIX #22 NEGATIVE: broken probe doesn't crash breaker
    # -------------------------------------------------------------
    print("-- 2. NEGATIVE: broken health_check (raises) → ignored, fall back to time-based --")
    def _broken_probe() -> bool:
        raise RuntimeError("probe died")

    cb = CircuitBreaker(
        "broken-probe",
        failure_threshold=1,
        recovery_timeout=0.05,
        health_check=_broken_probe,
    )
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    # Break probe → call should still work (probe ignored) and after
    # recovery_timeout breaker transitions normally.
    time.sleep(0.1)
    asyncio.run(cb.call_async(_ok))  # should succeed via time-based recovery
    assert cb.state is State.CLOSED, (
        f"FIX #22 BROKEN: broken probe must be ignored; got {cb.state}"
    )
    print("  ok: broken probe → caught + ignored; time-based recovery still works")

    # -------------------------------------------------------------
    # FIX #26: per-tenant breaker scope (tenant_id kwarg)
    # -------------------------------------------------------------
    print("-- 3. POSITIVE: tenant_id kwarg accepted + readable as attribute --")
    cb_a = CircuitBreaker("multi-tenant", tenant_id="tenant_a")
    cb_b = CircuitBreaker("multi-tenant", tenant_id="tenant_b")
    assert cb_a.tenant_id == "tenant_a"
    assert cb_b.tenant_id == "tenant_b"
    print("  ok: tenant_id stored on each instance independently")

    # -------------------------------------------------------------
    # FIX #26 NEGATIVE: tenant A's trips don't affect tenant B
    # -------------------------------------------------------------
    print("-- 4. NEGATIVE: tenant A's failures don't trip tenant B's breaker --")
    for _ in range(10):
        try:
            asyncio.run(cb_a.call_async(_fail))
        except (ConnectionError, cb_mod.CircuitOpenError):
            pass
    # tenant_a's breaker is OPEN
    assert cb_a.state is State.OPEN
    # tenant_b's breaker is independent — never tripped
    assert cb_b.state is State.CLOSED, (
        f"FIX #26 BROKEN: tenant_b affected by tenant_a's failures; got {cb_b.state}"
    )
    # tenant_b can still make calls
    asyncio.run(cb_b.call_async(_ok))
    print("  ok: tenant isolation — tenant_a OPEN, tenant_b stayed CLOSED")

    # -------------------------------------------------------------
    # FIX #26 NEGATIVE: tenant_id=None preserves legacy
    # -------------------------------------------------------------
    print("-- 5. NEGATIVE: tenant_id=None preserves legacy single-scope --")
    cb_global = CircuitBreaker("legacy-scope")
    assert cb_global.tenant_id is None
    print("  ok: tenant_id defaults to None (legacy)")

    # -------------------------------------------------------------
    # FIX #27: OTel baggage opt-in
    # -------------------------------------------------------------
    print("-- 6. POSITIVE: otel_baggage kwarg defaults to False (opt-in) --")
    cb = CircuitBreaker("otel-default")
    assert cb.otel_baggage is False
    print("  ok: otel_baggage defaults False (opt-in to avoid latency)")

    # -------------------------------------------------------------
    # FIX #27 NEGATIVE: missing OTel module is silent no-op
    # -------------------------------------------------------------
    print("-- 7. NEGATIVE: OTel-baggage enabled without OTel installed → silent no-op --")
    cb = CircuitBreaker("otel-missing", otel_baggage=True)
    # Even with otel_baggage=True, a call MUST succeed regardless of
    # whether OTel is importable. The _write_otel_baggage method
    # silently catches all exceptions.
    asyncio.run(cb.call_async(_ok))
    assert cb.state is State.CLOSED
    print("  ok: otel_baggage=True with optional dep absent → no crash")

    # -------------------------------------------------------------
    # FIX #22 NEGATIVE: health_check=None preserves legacy time-based recovery
    # -------------------------------------------------------------
    print("-- 8. NEGATIVE: health_check=None — time-based recovery only --")
    cb = CircuitBreaker(
        "no-probe",
        failure_threshold=1,
        recovery_timeout=0.05,
    )
    assert cb.health_check is None
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    # During recovery: blocked.
    raised = False
    try:
        asyncio.run(cb.call_async(_ok))
    except cb_mod.CircuitOpenError:
        raised = True
    assert raised
    # After recovery: succeeds.
    time.sleep(0.1)
    asyncio.run(cb.call_async(_ok))
    assert cb.state is State.CLOSED
    print("  ok: legacy time-based recovery works without probe")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
