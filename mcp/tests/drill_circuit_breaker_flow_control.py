#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for CB-B2 — exp-backoff + bulkhead + slow-call detection.

Locks 3 flow-control features:

  #9   Exponential backoff on recovery_timeout — repeated trips grow
       the recovery window, no thundering herd
  #10  Bulkhead (max_concurrent) — even when CLOSED, refuse calls
       when in-flight count exceeds cap
  #12  Slow-call detection — slow successes (>threshold) count toward
       a separate slow-call rate; trip even on 0% errors

Negative assertions are the regression locks.
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
    CircuitOpenError = cb_mod.CircuitOpenError

    # -------------------------------------------------------------
    # FIX #9: exponential backoff
    # -------------------------------------------------------------
    print("-- 1. POSITIVE: backoff_factor=2.0 — recovery_timeout doubles per trip --")
    cb = CircuitBreaker(
        "exp-backoff",
        failure_threshold=1,
        recovery_timeout=0.1,
        backoff_factor=2.0,
        backoff_jitter=0.0,  # disable jitter for deterministic test
        recovery_timeout_max=10.0,
    )

    async def _fail() -> None:
        raise ConnectionError("down")

    # Trip 1: recovery = 0.1
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    assert cb._consecutive_open_count == 1
    eff1 = cb._effective_recovery_timeout()
    assert abs(eff1 - 0.1) < 0.01, f"trip 1 should use base 0.1, got {eff1}"
    print(f"  ok: trip 1 recovery={eff1:.3f}s")

    # Trip 2: should be 0.1 * 2 = 0.2
    time.sleep(0.15)
    cb.allow()  # transition to HALF_OPEN
    cb.record_failure(ConnectionError("still down"))
    assert cb._consecutive_open_count == 2
    eff2 = cb._effective_recovery_timeout()
    assert abs(eff2 - 0.2) < 0.01, f"trip 2 should be 0.2, got {eff2}"
    print(f"  ok: trip 2 recovery={eff2:.3f}s (2× base)")

    # Trip 3: 0.4
    time.sleep(0.25)
    cb.allow()
    cb.record_failure(ConnectionError("still"))
    eff3 = cb._effective_recovery_timeout()
    assert abs(eff3 - 0.4) < 0.01, f"trip 3 should be 0.4, got {eff3}"
    print(f"  ok: trip 3 recovery={eff3:.3f}s (4× base)")

    # -------------------------------------------------------------
    # FIX #9 NEGATIVE: clean CLOSED resets backoff
    # -------------------------------------------------------------
    print("-- 2. NEGATIVE: clean CLOSED resets consecutive_open_count to 0 --")
    cb = CircuitBreaker(
        "backoff-reset",
        failure_threshold=1,
        recovery_timeout=0.05,
        backoff_factor=2.0,
        backoff_jitter=0.0,
    )

    async def _ok() -> str:
        return "ok"

    # Trip then recover.
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    assert cb._consecutive_open_count == 1
    time.sleep(0.1)
    cb.allow()  # OPEN→HALF_OPEN
    asyncio.run(cb.call_async(_ok))  # success → CLOSED
    assert cb.state is State.CLOSED
    assert cb._consecutive_open_count == 0, (
        f"FIX #9 BROKEN: clean CLOSED should reset count; got {cb._consecutive_open_count}"
    )
    print("  ok: backoff resets on clean recovery")

    # -------------------------------------------------------------
    # FIX #9 NEGATIVE: backoff caps at recovery_timeout_max
    # -------------------------------------------------------------
    print("-- 3. NEGATIVE: backoff respects recovery_timeout_max --")
    cb = CircuitBreaker(
        "backoff-cap",
        failure_threshold=1,
        recovery_timeout=1.0,
        backoff_factor=10.0,
        backoff_jitter=0.0,
        recovery_timeout_max=5.0,
    )
    cb._consecutive_open_count = 10  # simulate 10 trips
    eff = cb._effective_recovery_timeout()
    assert eff <= 5.0, f"FIX #9 BROKEN: backoff exceeded max ({eff} > 5.0)"
    assert eff >= 4.999, f"backoff should be at the cap, got {eff}"
    print(f"  ok: 10 trips capped at recovery_timeout_max=5.0 (got {eff:.3f})")

    # -------------------------------------------------------------
    # FIX #10: bulkhead — refuse calls when over max_concurrent
    # -------------------------------------------------------------
    print("-- 4. NEGATIVE: bulkhead refuses N+1th concurrent call --")
    cb = CircuitBreaker(
        "bulkhead",
        failure_threshold=10,
        max_concurrent=2,
    )

    async def _slow() -> str:
        await asyncio.sleep(0.1)
        return "ok"

    async def _hit_concurrent() -> list[bool]:
        # Launch 5 concurrent calls; cap=2 means 2 succeed, 3 should
        # raise CircuitOpenError immediately.
        results: list[bool] = []

        async def _one() -> None:
            try:
                await cb.call_async(_slow)
                results.append(True)
            except CircuitOpenError:
                results.append(False)
            except Exception:
                results.append(False)

        await asyncio.gather(*[_one() for _ in range(5)])
        return results

    results = asyncio.run(_hit_concurrent())
    successes = sum(1 for r in results if r)
    rejections = sum(1 for r in results if not r)
    # Bulkhead semantics: at any moment ≤ 2 in-flight. With 5 launches
    # against cap=2 and 0.1s slow fn, the timing means some get
    # admitted serially. Lower bound: at least 2 admitted; upper
    # bound: ≤ 5. Hard requirement: at least 1 rejection (cap fired).
    assert successes >= 2, f"at least 2 should succeed (cap=2); got {successes}"
    assert rejections >= 1, (
        f"FIX #10 BROKEN: 5 concurrent calls under cap=2 with 0.1s slow fn "
        f"produced 0 rejections; bulkhead not enforcing"
    )
    print(f"  ok: cap=2 → {successes} succeeded, {rejections} rejected as bulkhead-overloaded")

    # -------------------------------------------------------------
    # FIX #10 NEGATIVE: max_concurrent=None preserves legacy
    # -------------------------------------------------------------
    print("-- 5. NEGATIVE: max_concurrent=None — no bulkhead, all calls proceed --")
    cb = CircuitBreaker("no-bulkhead", failure_threshold=10)
    assert cb.max_concurrent is None

    async def _hit_unlimited() -> int:
        async def _one() -> bool:
            try:
                await cb.call_async(_slow)
                return True
            except Exception:
                return False
        results = await asyncio.gather(*[_one() for _ in range(10)])
        return sum(1 for r in results if r)

    successes = asyncio.run(_hit_unlimited())
    assert successes == 10, (
        f"max_concurrent=None should admit all; got {successes}/10"
    )
    print(f"  ok: legacy mode (no bulkhead) — all 10 admitted")

    # -------------------------------------------------------------
    # FIX #12: slow-call detection
    # -------------------------------------------------------------
    print("-- 6. POSITIVE: slow_call_threshold trips on slow-call rate --")
    cb = CircuitBreaker(
        "slow-call",
        failure_threshold=999,                # disable error-based trip
        failure_window_size=10,
        slow_call_threshold_s=0.05,
        slow_call_rate=0.5,                   # 50% slow → trip
    )

    async def _quick() -> str:
        return "ok"

    async def _too_slow() -> str:
        await asyncio.sleep(0.08)
        return "slow"

    # 6 slow + 4 fast = 60% slow.
    pattern = [_too_slow] * 6 + [_quick] * 4
    for fn in pattern:
        try:
            asyncio.run(cb.call_async(fn))
        except CircuitOpenError:
            pass
    assert cb.state is State.OPEN, (
        f"FIX #12 BROKEN: 60% slow-call rate did NOT trip; state={cb.state}"
    )
    print(f"  ok: 60% slow-call rate tripped breaker (zero errors)")

    # -------------------------------------------------------------
    # FIX #12 NEGATIVE: slow_call_threshold=None disables detection
    # -------------------------------------------------------------
    print("-- 7. NEGATIVE: slow_call_threshold=None — slow successes don't trip --")
    cb = CircuitBreaker(
        "no-slow-detect",
        failure_threshold=999,
        failure_window_size=10,
    )
    assert cb.slow_call_threshold_s is None
    for _ in range(10):
        asyncio.run(cb.call_async(_too_slow))
    assert cb.state is State.CLOSED, (
        "slow_call_threshold=None must NOT trip on slow successes"
    )
    print("  ok: legacy mode — slow successes don't trip")

    # -------------------------------------------------------------
    # FIX #12 NEGATIVE: fast calls don't trip even at high rate
    # -------------------------------------------------------------
    print("-- 8. NEGATIVE: 100% fast calls do NOT trip slow-call rate --")
    cb = CircuitBreaker(
        "all-fast",
        failure_threshold=999,
        failure_window_size=10,
        slow_call_threshold_s=0.05,
        slow_call_rate=0.5,
    )
    for _ in range(10):
        asyncio.run(cb.call_async(_quick))
    assert cb.state is State.CLOSED, (
        "100% fast calls should never trip slow-call detection"
    )
    print("  ok: all-fast breaker stayed CLOSED (slow_rate=0)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
