#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for CB-D — operator API + callbacks (#19, #20).

Locks the 3-AM-incident-response surface:

  #19  force_open(reason, ttl_s) / force_closed / reset
  #20  on_state_change callback (paging / Slack / audit hooks)

Negative assertions: a forced state MUST survive recovery_timeout
elapsing; a forced-closed MUST allow calls even when the natural
state would be OPEN; a callback raising MUST NOT crash the breaker.
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
    # FIX #19a: force_open survives recovery_timeout
    # -------------------------------------------------------------
    print("-- 1. NEGATIVE: force_open is sticky across recovery_timeout --")
    cb = CircuitBreaker("force-open-sticky", failure_threshold=99, recovery_timeout=0.05)
    cb.force_open(reason="planned_maintenance", ttl_s=None)
    assert cb.state is State.OPEN
    assert cb.is_forced is True
    assert cb.forced_reason == "planned_maintenance"

    async def _ok() -> str:
        return "ok"

    # Even after waiting longer than recovery_timeout, breaker stays OPEN.
    time.sleep(0.1)
    raised = False
    try:
        asyncio.run(cb.call_async(_ok))
    except CircuitOpenError as exc:
        raised = True
        assert exc.details.get("forced") is True, (
            f"FIX #19 BROKEN: forced-open error must include forced=True; got {exc.details}"
        )
    assert raised, "FIX #19 BROKEN: forced-OPEN allowed a call to proceed"
    print(f"  ok: force_open holds OPEN past recovery_timeout (0.1s > 0.05s)")

    # -------------------------------------------------------------
    # FIX #19b: force_closed survives natural OPEN state
    # -------------------------------------------------------------
    print("-- 2. NEGATIVE: force_closed bypasses recovery checks --")
    cb = CircuitBreaker("force-closed-bypass", failure_threshold=1, recovery_timeout=10)

    async def _fail() -> None:
        raise ConnectionError("down")

    # Trip naturally.
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    assert cb.state is State.OPEN

    # Operator forces closed.
    cb.force_closed(reason="downstream_verified_healthy")
    assert cb.is_forced is True
    assert cb.state is State.CLOSED

    # Subsequent call goes through.
    result = asyncio.run(cb.call_async(_ok))
    assert result == "ok", "FIX #19 BROKEN: forced-CLOSED blocked a call"
    print(f"  ok: force_closed bypasses natural OPEN state")

    # -------------------------------------------------------------
    # FIX #19c: reset() clears force + counters
    # -------------------------------------------------------------
    print("-- 3. POSITIVE: reset() clears forced state + counters --")
    cb = CircuitBreaker("reset-test", failure_threshold=99, failure_window_size=10)
    # Accumulate some failures.
    for _ in range(5):
        try:
            asyncio.run(cb.call_async(_fail))
        except ConnectionError:
            pass
    cb.force_open(ttl_s=None)
    assert cb.is_forced is True
    assert cb.failures == 5

    cb.reset()
    assert cb.is_forced is False
    assert cb.failures == 0
    assert cb.state is State.CLOSED
    assert len(cb._window) == 0
    print(f"  ok: reset cleared force + failure_count + window")

    # -------------------------------------------------------------
    # FIX #19d: ttl auto-expires the force
    # -------------------------------------------------------------
    print("-- 4. NEGATIVE: force_open with ttl auto-expires --")
    cb = CircuitBreaker("ttl-expire")
    cb.force_open(reason="brief_maintenance", ttl_s=0.05)
    assert cb.is_forced is True

    time.sleep(0.1)
    # Reading is_forced triggers the expiry check.
    assert cb.is_forced is False, "FIX #19 BROKEN: ttl did NOT auto-expire force"
    print(f"  ok: ttl_s=0.05 expired after 0.1s wait")

    # -------------------------------------------------------------
    # FIX #20a: on_state_change callback fires on every transition
    # -------------------------------------------------------------
    print("-- 5. POSITIVE: on_state_change callback fires per real transition --")
    transitions: list[tuple[str, str, str]] = []

    def _record(prev: State, new: State, name: str) -> None:
        transitions.append((prev.value, new.value, name))

    cb = CircuitBreaker(
        "callback-test",
        failure_threshold=1,
        recovery_timeout=0.05,
        on_state_change=_record,
    )
    try:
        asyncio.run(cb.call_async(_fail))  # CLOSED → OPEN
    except ConnectionError:
        pass
    time.sleep(0.1)
    cb.allow()  # OPEN → HALF_OPEN
    asyncio.run(cb.call_async(_ok))  # HALF_OPEN → CLOSED
    expected = [
        ("closed", "open", "callback-test"),
        ("open", "half_open", "callback-test"),
        ("half_open", "closed", "callback-test"),
    ]
    assert transitions == expected, (
        f"FIX #20 BROKEN: expected {expected}, got {transitions}"
    )
    print(f"  ok: 3 transitions fired callback in correct order")

    # -------------------------------------------------------------
    # FIX #20b: NO duplicate callback for same-state "transitions"
    # -------------------------------------------------------------
    print("-- 6. NEGATIVE: callback does NOT fire when state unchanged --")
    transitions.clear()

    def _record2(prev: State, new: State, name: str) -> None:
        transitions.append((prev.value, new.value, name))

    cb = CircuitBreaker("no-spurious-cb", on_state_change=_record2)
    # 5 successful calls — state stays CLOSED throughout.
    for _ in range(5):
        asyncio.run(cb.call_async(_ok))
    assert transitions == [], (
        f"FIX #20 BROKEN: callback fired on same-state events; got {transitions}"
    )
    print(f"  ok: 5 same-state events triggered 0 callbacks")

    # -------------------------------------------------------------
    # FIX #20c: callback exception MUST NOT crash the breaker
    # -------------------------------------------------------------
    print("-- 7. NEGATIVE: broken callback does NOT crash the breaker --")
    def _broken_cb(prev: State, new: State, name: str) -> None:
        raise RuntimeError("simulated callback bug")

    cb = CircuitBreaker(
        "broken-cb",
        failure_threshold=1,
        on_state_change=_broken_cb,
    )
    # The trip MUST succeed even though the callback raises.
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    assert cb.state is State.OPEN, (
        f"FIX #20 BROKEN: broken callback prevented state transition; got {cb.state}"
    )
    print(f"  ok: broken callback caught + logged; breaker still trips")

    # -------------------------------------------------------------
    # FIX #20d: callback fires for force_open / force_closed too
    # -------------------------------------------------------------
    print("-- 8. POSITIVE: callback fires on operator-forced transitions --")
    transitions.clear()
    cb = CircuitBreaker("force-cb", on_state_change=_record2)
    cb.force_open(ttl_s=None)
    cb.force_closed()
    cb.reset()
    # Sequence: CLOSED→OPEN (force_open), OPEN→CLOSED (force_closed),
    # CLOSED→CLOSED (reset, but already CLOSED — no callback).
    state_pairs = [(t[0], t[1]) for t in transitions]
    assert ("closed", "open") in state_pairs
    assert ("open", "closed") in state_pairs
    print(f"  ok: forced transitions fire callback ({len(transitions)} total)")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
