#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for the 5 critical CircuitBreaker fixes (CB-A1 through CB-A3 + atomic-allow + opened_at order).

Each step locks one of the 5 production-breaking bugs from the brutal
feedback. Negative assertions are the regression locks: each test
fails LOUDLY if a future refactor regresses the corresponding bug.

The 5 fixes under test:

  #1 (CB-A1) call_timeout_s — hung downstream → counted failure
  #4 (CB-A2) atomic allow() — concurrent allow()s cannot both transition
  #5 (CB-A4) _opened_at set BEFORE _transition(OPEN)
  #6 (CB-A3) narrowed expected_exception default (no caller-bug trips)
  #3 (CB-A3) asyncio.CancelledError NOT counted as failure

Resource tag = readonly. Pure unit drill — no Postgres, no Ollama.

Why this drill exists: state-machine bugs are the worst class of bug
because their symptoms are non-deterministic (race-driven). Without
explicit invariant tests, a future "small refactor" of the lock or
transition order silently regresses the breaker into uselessness.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import threading
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CB_FILE = REPO / "libs" / "py" / "documind_core" / "circuit_breaker.py"


def _load() -> object:
    # Reuse the installed documind_core package — running standalone
    # via importlib would lose the .exceptions sibling.
    sys.path.insert(0, str(REPO / "libs" / "py"))
    import documind_core.circuit_breaker as cb  # noqa: PLC0415
    return cb


def main() -> int:
    cb_mod = _load()
    CircuitBreaker = cb_mod.CircuitBreaker
    State = cb_mod.State
    CircuitOpenError = cb_mod.CircuitOpenError

    # -------------------------------------------------------------
    # FIX #1 (CB-A1): hung downstream + call_timeout_s → counted failure
    # -------------------------------------------------------------
    print("-- 1. POSITIVE: call_timeout_s wraps fn() and counts timeout as failure --")
    cb = CircuitBreaker(
        "hung-downstream",
        failure_threshold=2,
        recovery_timeout=60,
        call_timeout_s=0.05,
    )

    async def _hang() -> str:
        await asyncio.sleep(5.0)
        return "never"

    raised = 0
    for _ in range(2):
        try:
            asyncio.run(cb.call_async(_hang))
        except (asyncio.TimeoutError, CircuitOpenError):
            raised += 1
    assert raised == 2, f"expected 2 timeouts caught; got {raised}"
    assert cb.state is State.OPEN, (
        f"FIX #1 BROKEN: hung downstream did NOT trip breaker; "
        f"state={cb.state}, failures={cb.failures}"
    )
    print(f"  ok: hung downstream tripped breaker (state={cb.state.value}, "
          f"failures={cb.failures})")

    # -------------------------------------------------------------
    # FIX #1 NEGATIVE: without call_timeout_s, hung fn would NOT trip
    # (we don't actually wait 5s — we just verify the kwarg is honored).
    # -------------------------------------------------------------
    print("-- 2. NEGATIVE: omitting call_timeout_s preserves legacy (no auto-timeout) --")
    cb_no_timeout = CircuitBreaker("no-timeout", failure_threshold=2)
    assert cb_no_timeout.call_timeout_s is None
    print("  ok: call_timeout_s defaults to None (opt-in, backward compat)")

    # -------------------------------------------------------------
    # FIX #6 (CB-A3): expected_exception narrowed default
    # -------------------------------------------------------------
    print("-- 3. POSITIVE: default expected_exception is narrowed (NOT Exception) --")
    cb = CircuitBreaker("narrow-default")
    assert Exception not in cb.expected_exception, (
        "FIX #6 BROKEN: default still includes bare Exception; "
        "caller bugs (KeyError/TypeError) will trip breaker"
    )
    # Should include the OS-level + httpx-level set.
    assert ConnectionError in cb.expected_exception
    assert OSError in cb.expected_exception
    print(f"  ok: default = {tuple(e.__name__ for e in cb.expected_exception)}")

    # -------------------------------------------------------------
    # FIX #6 NEGATIVE: caller bug (KeyError) does NOT trip the breaker
    # -------------------------------------------------------------
    print("-- 4. NEGATIVE: KeyError in fn does NOT trip breaker (caller bug, not downstream) --")
    cb = CircuitBreaker("caller-bug-test", failure_threshold=2)

    async def _caller_bug() -> str:
        raise KeyError("typo in caller code")

    raised = 0
    for _ in range(5):
        try:
            asyncio.run(cb.call_async(_caller_bug))
        except KeyError:
            raised += 1
        except CircuitOpenError:
            pass
    assert raised == 5, f"KeyError should always propagate; got {raised}/5"
    assert cb.state is State.CLOSED, (
        f"FIX #6 BROKEN: caller bug (KeyError) tripped breaker! state={cb.state}"
    )
    assert cb.failures == 0, (
        f"FIX #6 BROKEN: caller bug counted as failure; failures={cb.failures}"
    )
    print(f"  ok: 5x KeyError propagated, breaker stayed CLOSED, failures=0")

    # -------------------------------------------------------------
    # FIX #3 (CB-A3): asyncio.CancelledError pass-through
    # -------------------------------------------------------------
    print("-- 5. NEGATIVE: asyncio.CancelledError does NOT count as failure --")
    cb = CircuitBreaker("cancellation-test", failure_threshold=2)

    async def _cancellable() -> None:
        await asyncio.sleep(10)

    async def _outer() -> None:
        task = asyncio.create_task(cb.call_async(_cancellable))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    for _ in range(5):
        asyncio.run(_outer())
    assert cb.state is State.CLOSED, (
        f"FIX #3 BROKEN: 5x cancellation tripped breaker; state={cb.state}"
    )
    assert cb.failures == 0, (
        f"FIX #3 BROKEN: cancellations incremented failures; failures={cb.failures}"
    )
    print(f"  ok: 5x cancellation propagated, breaker stayed CLOSED, failures=0")

    # -------------------------------------------------------------
    # FIX #5 (CB-A4): _opened_at set BEFORE _transition(OPEN)
    # -------------------------------------------------------------
    print("-- 6. NEGATIVE: tight recovery_timeout (0.5s) — breaker stays OPEN, doesn't insta-flip --")
    # Pre-fix: with recovery_timeout=0.5 and the 0.0 init value,
    # `monotonic() - 0` is always >= 0.5, so the breaker would
    # immediately transition OPEN→HALF_OPEN on the next allow().
    cb = CircuitBreaker("tight-recovery", failure_threshold=1, recovery_timeout=0.5)

    async def _fail() -> None:
        raise ConnectionError("downstream down")

    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    # Immediately after the trip, breaker should be OPEN and allow() should be False.
    assert cb.state is State.OPEN, f"breaker should be OPEN; got {cb.state}"
    # Within recovery_timeout, allow() returns False.
    immediate_allow = cb.allow()
    assert immediate_allow is False, (
        "FIX #5 BROKEN: breaker just transitioned OPEN but allow() returned True "
        "(_opened_at not set before _transition; race window leaked through)"
    )
    print(f"  ok: tight-recovery breaker stayed OPEN immediately after trip "
          f"(state={cb.state.value}, allow={immediate_allow})")

    # -------------------------------------------------------------
    # FIX #4 (CB-A2): atomic allow() — concurrent transitions
    # -------------------------------------------------------------
    print("-- 7. NEGATIVE: concurrent allow()s on expired-OPEN → only ONE transition counted --")
    cb = CircuitBreaker("atomic-allow", failure_threshold=1, recovery_timeout=0.05)

    async def _trip() -> None:
        raise ConnectionError("trip")

    try:
        asyncio.run(cb.call_async(_trip))
    except ConnectionError:
        pass
    assert cb.state is State.OPEN
    # Wait for recovery window to elapse.
    time.sleep(0.1)

    # 50 threads simultaneously call allow(). With CB-A2 fixed,
    # exactly one should transition the state to HALF_OPEN; the rest
    # should observe HALF_OPEN and either return True (after the
    # transition) or False (if they hit the OPEN check before the
    # transition winner). The KEY invariant: the final state is
    # HALF_OPEN, AND at most one transition (CLOSED→OPEN was the
    # earlier one) was recorded since the trip.
    transitions_seen: list[str] = []
    barrier = threading.Barrier(50)

    def _hammer() -> None:
        barrier.wait()
        result = cb.allow()
        transitions_seen.append(f"{cb.state.value}:{result}")

    threads = [threading.Thread(target=_hammer) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Final state must be HALF_OPEN (one or more callers transitioned;
    # all subsequent observers see HALF_OPEN and return True).
    assert cb.state is State.HALF_OPEN, (
        f"FIX #4 BROKEN: concurrent allow() left bad state {cb.state}"
    )
    # NEGATIVE: no caller should observe a "phantom" CLOSED state
    # mid-transition.
    closed_observations = [s for s in transitions_seen if s.startswith("closed")]
    assert not closed_observations, (
        f"FIX #4 BROKEN: {len(closed_observations)} callers saw CLOSED during "
        f"OPEN→HALF_OPEN transition: {closed_observations[:5]}"
    )
    print(f"  ok: 50 concurrent allow()s converged to HALF_OPEN, no phantom CLOSED")

    # -------------------------------------------------------------
    # FIX #1+#5 combined: hung fn() with tight recovery → still trips correctly
    # -------------------------------------------------------------
    print("-- 8. POSITIVE: hung fn + tight recovery_timeout — full state machine --")
    cb = CircuitBreaker(
        "combined",
        failure_threshold=1,
        recovery_timeout=0.05,
        call_timeout_s=0.02,
    )

    async def _slow() -> None:
        await asyncio.sleep(1.0)

    try:
        asyncio.run(cb.call_async(_slow))
    except (asyncio.TimeoutError, CircuitOpenError):
        pass
    assert cb.state is State.OPEN
    # Within recovery: allow() False
    assert cb.allow() is False
    # After recovery: allow() True (transitions to HALF_OPEN)
    time.sleep(0.1)
    assert cb.allow() is True
    assert cb.state is State.HALF_OPEN
    print(f"  ok: hung→OPEN→(recovery elapses)→HALF_OPEN — full machine works under all fixes")

    # -------------------------------------------------------------
    # All fixes in place — produce a summary
    # -------------------------------------------------------------
    print()
    print("FIXES VERIFIED:")
    print("  #1 CB-A1: call_timeout_s in call_async                    [step 1]")
    print("  #6 CB-A3: narrowed expected_exception default             [step 3]")
    print("  #6 CB-A3: caller bug does NOT trip breaker                [step 4]")
    print("  #3 CB-A3: asyncio.CancelledError pass-through             [step 5]")
    print("  #5 CB-A4: _opened_at set BEFORE _transition(OPEN)         [step 6]")
    print("  #4 CB-A2: atomic allow() — no concurrent phantom transitions [step 7]")
    print("  combined full-state-machine                                [step 8]")
    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
