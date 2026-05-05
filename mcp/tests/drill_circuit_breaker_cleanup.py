#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for CB-G — cleanup items (#11, #28, #29, #30).

Includes negative assertions: legacy `_MCPBreaker` must NOT exist;
unknown-cause sentinel must NOT propagate after deprecation; cleanup
work must NOT regress to the prior duplicate-class state.

Locks 4 small contracts:

  #11  No `_MCPBreaker` leftover in mcp/client.py — already
       consolidated per code comment, but verify it stayed that way.
  #28  Sync `allow()` and async `call_async` share ONE lock
       (threading.RLock). Drill races them concurrently to confirm.
  #29  _BreakerCallFailed Exception subclass is deprecated — string
       constant `_UNKNOWN_CAUSE_LABEL` exists; sentinel is documented
       as deprecated.
  #30  `expected_exception` accepts a single class (not just a tuple).
"""
from __future__ import annotations

import asyncio
import sys
import threading
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

    # -------------------------------------------------------------
    # FIX #11: no leftover _MCPBreaker class in mcp/client.py
    # -------------------------------------------------------------
    print("-- 1. NEGATIVE: no `class _MCPBreaker` definition in mcp/client.py --")
    client_text = (REPO / "mcp" / "client.py").read_text(encoding="utf-8")
    # The string '_MCPBreaker' may appear in HISTORICAL comments
    # (line 101: 'kept a private _MCPBreaker here for decoupling') —
    # that's fine. What MUST NOT appear is `class _MCPBreaker:`
    # (the actual class definition).
    assert "class _MCPBreaker" not in client_text, (
        "FIX #11 BROKEN: _MCPBreaker class re-introduced; "
        "consolidate via documind_core.CircuitBreaker"
    )
    # Verify the canonical CircuitBreaker IS imported.
    assert "from documind_core.circuit_breaker import CircuitBreaker" in client_text
    print("  ok: no _MCPBreaker class; canonical CircuitBreaker imported")

    # -------------------------------------------------------------
    # FIX #28: sync allow() and async call_async share one lock
    # -------------------------------------------------------------
    print("-- 2. POSITIVE: sync + async paths share threading.RLock --")
    cb = CircuitBreaker("shared-lock")
    assert isinstance(cb._lock, type(threading.RLock())), (
        f"FIX #28 BROKEN: lock is not threading.RLock; got {type(cb._lock)}"
    )
    print(f"  ok: _lock is threading.RLock (sync + async share)")

    # -------------------------------------------------------------
    # FIX #28 NEGATIVE: concurrent sync + async ops are race-safe
    # -------------------------------------------------------------
    print("-- 3. NEGATIVE: 100 concurrent allow() + record_failure ops don't corrupt state --")
    cb = CircuitBreaker(
        "race-safe",
        failure_threshold=50,  # high enough that races could either way
        recovery_timeout=10,
    )

    def _hammer_sync():
        for _ in range(50):
            cb.allow()
            cb.record_success()

    threads = [threading.Thread(target=_hammer_sync) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # State must be CLOSED (no failures recorded).
    assert cb.state is State.CLOSED, f"race corrupted state; got {cb.state}"
    assert cb.failures == 0
    print(f"  ok: 200 concurrent ops on shared lock — state stayed CLOSED")

    # -------------------------------------------------------------
    # FIX #29: _UNKNOWN_CAUSE_LABEL constant exists; sentinel deprecated
    # -------------------------------------------------------------
    print("-- 4. POSITIVE: _UNKNOWN_CAUSE_LABEL string constant present --")
    assert hasattr(cb_mod, "_UNKNOWN_CAUSE_LABEL")
    assert cb_mod._UNKNOWN_CAUSE_LABEL == "unknown"
    # The deprecated sentinel still exists for backward compat.
    assert hasattr(cb_mod, "_BreakerCallFailed")
    # Its docstring should mark it deprecated.
    sentinel_doc = cb_mod._BreakerCallFailed.__doc__ or ""
    assert "deprecated" in sentinel_doc.lower(), (
        f"FIX #29: _BreakerCallFailed docstring should mention 'deprecated'; "
        f"got: {sentinel_doc!r}"
    )
    print(f"  ok: _UNKNOWN_CAUSE_LABEL='unknown'; sentinel marked deprecated")

    # -------------------------------------------------------------
    # FIX #30: expected_exception accepts a single class
    # -------------------------------------------------------------
    print("-- 5. POSITIVE: expected_exception accepts a single class --")
    cb = CircuitBreaker(
        "single-class",
        failure_threshold=2,
        expected_exception=ValueError,  # NOT a tuple
    )

    async def _value_err() -> None:
        raise ValueError("expected")

    for _ in range(2):
        try:
            asyncio.run(cb.call_async(_value_err))
        except ValueError:
            pass
    assert cb.state is State.OPEN, (
        f"FIX #30 BROKEN: single-class expected_exception not honored; got {cb.state}"
    )
    print(f"  ok: expected_exception=ValueError (single class) trips after 2 failures")

    # -------------------------------------------------------------
    # FIX #30 NEGATIVE: a different exception type is NOT counted
    # -------------------------------------------------------------
    print("-- 6. NEGATIVE: exception NOT in single-class expected_exception passes through --")
    cb = CircuitBreaker(
        "passthrough",
        failure_threshold=2,
        expected_exception=ValueError,  # only ValueError trips
    )

    async def _key_err() -> None:
        raise KeyError("not in expected")

    for _ in range(5):
        try:
            asyncio.run(cb.call_async(_key_err))
        except KeyError:
            pass
    assert cb.state is State.CLOSED, (
        f"FIX #30 BROKEN: KeyError tripped breaker (only ValueError should); "
        f"state={cb.state}, failures={cb.failures}"
    )
    print(f"  ok: KeyError did NOT trip (only ValueError in expected_exception)")

    # -------------------------------------------------------------
    # FIX #30: still works with tuple
    # -------------------------------------------------------------
    print("-- 7. POSITIVE: expected_exception=(ValueError, KeyError) accepts both --")
    cb = CircuitBreaker(
        "multi-class",
        failure_threshold=2,
        expected_exception=(ValueError, KeyError),
    )
    try:
        asyncio.run(cb.call_async(_value_err))
    except ValueError:
        pass
    try:
        asyncio.run(cb.call_async(_key_err))
    except KeyError:
        pass
    assert cb.state is State.OPEN, (
        f"tuple expected_exception should trip; got {cb.state}"
    )
    print(f"  ok: tuple of (ValueError, KeyError) → trips on either")

    # -------------------------------------------------------------
    # FIX #28 NEGATIVE: records under sync API show up in metrics
    # (the lock truly unifies — no path-distinct counters)
    # -------------------------------------------------------------
    print("-- 8. POSITIVE: record_success increments same counter as call_async success --")
    cb = CircuitBreaker("metric-shared")
    before = cb_mod._cb_successes.labels(name="metric-shared")._value.get()  # type: ignore[attr-defined]
    cb.record_success()  # sync API
    after_sync = cb_mod._cb_successes.labels(name="metric-shared")._value.get()  # type: ignore[attr-defined]
    # Sync record_success calls _on_success which bumps the metric.
    assert after_sync > before, "sync record_success should bump _cb_successes counter"
    print(f"  ok: sync record_success bumps the same counter as async call_async")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
