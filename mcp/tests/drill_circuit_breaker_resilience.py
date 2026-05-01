#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for CB-B1 — sliding-window + HALF_OPEN cap + success_threshold.

Locks 3 resilience features that fix Tier-2 silent-degradation bugs:

  #2  Consecutive-failure counter, not rate-based — flapping never trips
  #7  No HALF_OPEN concurrency cap — thundering herd on recovery
  #8  One success closes HALF_OPEN — flapping CLOSED↔OPEN forever

Negative assertions are the regression locks: each test would fail
loudly if a future refactor regressed any of these.
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

    # -------------------------------------------------------------
    # FIX #2: sliding-window failure rate
    # -------------------------------------------------------------
    print("-- 1. POSITIVE: sliding-window mode trips on rate, not consecutive --")
    cb = CircuitBreaker(
        "rate-mode",
        failure_window_size=10,
        failure_threshold_rate=0.6,  # 60%
        failure_threshold=999,        # legacy counter effectively disabled
    )

    async def _ok() -> str:
        return "ok"

    async def _fail() -> str:
        raise ConnectionError("down")

    # Pattern: 6 fails + 4 successes interleaved → 60% rate exactly.
    pattern = [_fail, _ok, _fail, _ok, _fail, _ok, _fail, _ok, _fail, _fail]
    for fn in pattern:
        try:
            asyncio.run(cb.call_async(fn))
        except (ConnectionError, cb_mod.CircuitOpenError):
            pass
    assert cb.state is State.OPEN, (
        f"FIX #2 BROKEN: 60% failure rate did not trip; state={cb.state}, "
        f"window={list(cb._window)}"
    )
    print(f"  ok: 60% failure-rate window tripped breaker (state={cb.state.value})")

    # -------------------------------------------------------------
    # FIX #2 NEGATIVE: legacy mode (window_size=0) ignores rate
    # -------------------------------------------------------------
    print("-- 2. NEGATIVE: window_size=0 → legacy consecutive counter only --")
    cb_legacy = CircuitBreaker("legacy-mode", failure_threshold=2)
    assert cb_legacy.failure_window_size == 0
    assert cb_legacy.failure_threshold_rate is None
    # Pre-fix flapping: fail, success, fail, success — never trips.
    for fn in [_fail, _ok, _fail, _ok, _fail]:
        try:
            asyncio.run(cb_legacy.call_async(fn))
        except (ConnectionError, cb_mod.CircuitOpenError):
            pass
    # Legacy: success between failures resets counter → never reaches 2.
    assert cb_legacy.state is State.CLOSED, (
        "legacy mode should NOT trip on flapping (compat); "
        f"state={cb_legacy.state}"
    )
    print("  ok: legacy mode preserved (window_size=0)")

    # -------------------------------------------------------------
    # FIX #7: HALF_OPEN concurrency cap
    # -------------------------------------------------------------
    print("-- 3. NEGATIVE: HALF_OPEN admits only N concurrent probes (N=1) --")
    cb = CircuitBreaker(
        "half-open-cap",
        failure_threshold=1,
        recovery_timeout=0.05,
        half_open_max_concurrent=1,
    )
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    assert cb.state is State.OPEN
    time.sleep(0.1)  # recovery elapses

    # First allow() transitions OPEN→HALF_OPEN AND consumes the slot.
    first = cb.allow()
    assert first is True
    assert cb.state is State.HALF_OPEN
    # Second allow() in HALF_OPEN with 0 slots left → False.
    second = cb.allow()
    assert second is False, (
        "FIX #7 BROKEN: 2nd concurrent probe admitted; HALF_OPEN cap not enforced"
    )
    third = cb.allow()
    assert third is False
    print("  ok: cap=1 — second/third probes correctly rejected")

    # -------------------------------------------------------------
    # FIX #7: cap=3 admits 3, rejects 4th
    # -------------------------------------------------------------
    print("-- 4. POSITIVE: half_open_max_concurrent=3 admits exactly 3 probes --")
    cb = CircuitBreaker(
        "cap-3",
        failure_threshold=1,
        recovery_timeout=0.05,
        half_open_max_concurrent=3,
    )
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    time.sleep(0.1)
    admitted = sum(1 for _ in range(10) if cb.allow())
    assert admitted == 3, f"expected 3 admitted, got {admitted}"
    print(f"  ok: 3 of 10 admitted under cap=3")

    # -------------------------------------------------------------
    # FIX #8: half_open_success_threshold=3 — 1 success not enough
    # -------------------------------------------------------------
    print("-- 5. NEGATIVE: 1 success in HALF_OPEN does NOT close (threshold=3) --")
    cb = CircuitBreaker(
        "success-threshold-3",
        failure_threshold=1,
        recovery_timeout=0.05,
        half_open_success_threshold=3,
    )
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    time.sleep(0.1)
    # Manually walk: allow + record_success; assert state stays HALF_OPEN
    # until 3rd success.
    cb.allow()
    cb.record_success()
    assert cb.state is State.HALF_OPEN, "1st success should NOT close"
    cb.allow()
    cb.record_success()
    assert cb.state is State.HALF_OPEN, "2nd success should NOT close"
    cb.allow()
    cb.record_success()
    assert cb.state is State.CLOSED, "3rd success SHOULD close"
    print("  ok: required 3 consecutive successes to close (was 1 pre-fix)")

    # -------------------------------------------------------------
    # FIX #8 NEGATIVE: a single failure in HALF_OPEN re-trips immediately
    # (regardless of how many successes preceded it)
    # -------------------------------------------------------------
    print("-- 6. NEGATIVE: HALF_OPEN failure re-trips immediately --")
    cb = CircuitBreaker(
        "half-open-fail",
        failure_threshold=1,
        recovery_timeout=0.05,
        half_open_success_threshold=3,
    )
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    time.sleep(0.1)
    cb.allow()
    cb.record_success()  # 1 success
    cb.allow()
    cb.record_success()  # 2 successes
    assert cb.state is State.HALF_OPEN
    cb.allow()
    cb.record_failure(ConnectionError("fail in half-open"))
    assert cb.state is State.OPEN, (
        f"FIX #8 BROKEN: HALF_OPEN failure should re-trip; got {cb.state}"
    )
    print("  ok: HALF_OPEN failure re-trips even after 2 successes")

    # -------------------------------------------------------------
    # FIX #2 NEGATIVE: window-mode does NOT trip on early calls (anti-spurious)
    # -------------------------------------------------------------
    print("-- 7. NEGATIVE: window-mode requires N//2 calls before tripping --")
    cb = CircuitBreaker(
        "no-spurious-trip",
        failure_window_size=20,
        failure_threshold_rate=0.5,
        failure_threshold=999,
    )
    # 1 failure on window_size=20 should NOT trip (rate is 100% but only 1 sample).
    try:
        asyncio.run(cb.call_async(_fail))
    except (ConnectionError, cb_mod.CircuitOpenError):
        pass
    assert cb.state is State.CLOSED, (
        f"FIX #2 spurious-trip protection BROKEN: 1 failure on size=20 tripped; "
        f"window={list(cb._window)}"
    )
    print("  ok: 1 failure on size-20 window did NOT trip (anti-spurious)")

    # -------------------------------------------------------------
    # FIX #7 + atomic-allow combined: race-safe under load
    # -------------------------------------------------------------
    print("-- 8. POSITIVE: cap+atomic-allow together — full state machine --")
    cb = CircuitBreaker(
        "combined",
        failure_threshold=1,
        recovery_timeout=0.05,
        half_open_max_concurrent=2,
        half_open_success_threshold=2,
    )
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    time.sleep(0.1)
    # 5 concurrent allow() — only 2 admitted.
    import threading

    barrier = threading.Barrier(5)
    results: list[bool] = []

    def _probe():
        barrier.wait()
        results.append(cb.allow())

    threads = [threading.Thread(target=_probe) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    admitted = sum(1 for r in results if r)
    assert admitted == 2, f"cap=2 should admit exactly 2, got {admitted}"
    # Both admitted probes succeed → close.
    cb.record_success()
    cb.record_success()
    assert cb.state is State.CLOSED, f"expected CLOSED after 2 successes; got {cb.state}"
    print(f"  ok: 5 concurrent probes → 2 admitted; 2 successes → CLOSED")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
