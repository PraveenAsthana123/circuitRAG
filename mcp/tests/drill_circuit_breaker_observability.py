#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill for CB-C — 5 observability metrics (#13–#17).

Locks the metric surface that operators need during incident response:

  #13  documind_circuit_breaker_call_seconds (Histogram, labels: name, outcome)
  #14  documind_circuit_breaker_successes_total (Counter, labels: name)
  #15  documind_circuit_breaker_failures_total (Counter, labels: name, exception_class)
  #16  documind_circuit_breaker_half_open_probes_total (Counter, labels: name, outcome)
  #17  documind_circuit_breaker_open_duration_seconds (Gauge, labels: name)

Negative assertions: each metric MUST be present with the right shape;
missing metric = incident-response gap = drill rejects.
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


def _metric_value(metric, **labels) -> float:
    """Read current value of a labelled prometheus metric."""
    return metric.labels(**labels)._value.get()  # type: ignore[attr-defined]


def main() -> int:
    cb_mod = _load()
    CircuitBreaker = cb_mod.CircuitBreaker
    State = cb_mod.State

    # Verify the module exports the new metrics.
    print("-- 1. POSITIVE: 5 new metrics declared at module level --")
    for metric_name in (
        "_cb_successes",
        "_cb_call_seconds",
        "_cb_half_open_probes",
        "_cb_open_duration",
    ):
        assert hasattr(cb_mod, metric_name), f"missing module-level {metric_name}"
    # Verify _cb_failures has exception_class label by checking labels.
    failures = cb_mod._cb_failures
    assert "exception_class" in failures._labelnames, (
        f"FIX #15 BROKEN: _cb_failures missing 'exception_class' label; "
        f"got {failures._labelnames}"
    )
    print("  ok: 5 new metrics declared; failures has exception_class label")

    # -------------------------------------------------------------
    # FIX #14: success_total counter increments on success
    # -------------------------------------------------------------
    print("-- 2. POSITIVE: successes_total increments on each success --")
    cb = CircuitBreaker("metrics-success")

    async def _ok() -> str:
        return "ok"

    before = _metric_value(cb_mod._cb_successes, name="metrics-success")
    for _ in range(5):
        asyncio.run(cb.call_async(_ok))
    after = _metric_value(cb_mod._cb_successes, name="metrics-success")
    assert after - before == 5, (
        f"FIX #14 BROKEN: 5 successes → counter delta {after - before}"
    )
    print(f"  ok: successes_total: {before} → {after} (Δ=5)")

    # -------------------------------------------------------------
    # FIX #15: exception_class label captures real exception type
    # -------------------------------------------------------------
    print("-- 3. POSITIVE: failures_total carries exception_class label --")
    cb = CircuitBreaker("metrics-fail-label", failure_threshold=99)

    async def _conn_err() -> None:
        raise ConnectionError("net down")

    async def _timeout_err() -> None:
        raise TimeoutError("too slow")

    for _ in range(3):
        try:
            asyncio.run(cb.call_async(_conn_err))
        except ConnectionError:
            pass
    for _ in range(2):
        try:
            asyncio.run(cb.call_async(_timeout_err))
        except TimeoutError:
            pass

    conn_count = _metric_value(
        cb_mod._cb_failures, name="metrics-fail-label", exception_class="ConnectionError"
    )
    timeout_count = _metric_value(
        cb_mod._cb_failures, name="metrics-fail-label", exception_class="TimeoutError"
    )
    assert conn_count == 3, f"ConnectionError label count {conn_count}, expected 3"
    assert timeout_count == 2, f"TimeoutError label count {timeout_count}, expected 2"
    print("  ok: ConnectionError=3, TimeoutError=2 (operator can grep by class)")

    # -------------------------------------------------------------
    # FIX #16: half_open_probe outcome counter
    # -------------------------------------------------------------
    print("-- 4. POSITIVE: probe outcomes counted with success/failure label --")
    cb = CircuitBreaker(
        "probe-counter",
        failure_threshold=1,
        recovery_timeout=0.05,
        half_open_success_threshold=2,
    )

    async def _fail() -> None:
        raise ConnectionError("fail")

    # Trip → wait → 1 probe success + 1 probe failure pattern.
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    time.sleep(0.1)

    probe_success_before = _metric_value(
        cb_mod._cb_half_open_probes, name="probe-counter", outcome="success"
    )
    probe_failure_before = _metric_value(
        cb_mod._cb_half_open_probes, name="probe-counter", outcome="failure"
    )

    asyncio.run(cb.call_async(_ok))   # probe success #1
    # State should still be HALF_OPEN (need 2 successes)
    assert cb.state is State.HALF_OPEN
    try:
        asyncio.run(cb.call_async(_fail))  # probe failure → re-trip
    except ConnectionError:
        pass

    probe_success_after = _metric_value(
        cb_mod._cb_half_open_probes, name="probe-counter", outcome="success"
    )
    probe_failure_after = _metric_value(
        cb_mod._cb_half_open_probes, name="probe-counter", outcome="failure"
    )
    assert probe_success_after - probe_success_before == 1
    assert probe_failure_after - probe_failure_before == 1
    print("  ok: probe success +1, failure +1 (real recovery signal)")

    # -------------------------------------------------------------
    # FIX #13: latency histogram observed on every call
    # -------------------------------------------------------------
    print("-- 5. POSITIVE: call_seconds histogram observes every call --")
    cb = CircuitBreaker("metrics-latency")

    async def _quick() -> str:
        await asyncio.sleep(0.01)
        return "ok"

    # Histogram count is per labelled (name, outcome).
    histogram_metric = cb_mod._cb_call_seconds
    sample_count_before = sum(
        s.value for s in histogram_metric.collect()[0].samples
        if s.name.endswith("_count") and s.labels.get("name") == "metrics-latency"
        and s.labels.get("outcome") == "success"
    )
    for _ in range(5):
        asyncio.run(cb.call_async(_quick))
    sample_count_after = sum(
        s.value for s in histogram_metric.collect()[0].samples
        if s.name.endswith("_count") and s.labels.get("name") == "metrics-latency"
        and s.labels.get("outcome") == "success"
    )
    assert sample_count_after - sample_count_before == 5, (
        f"FIX #13 BROKEN: 5 calls → histogram count delta "
        f"{sample_count_after - sample_count_before}, expected 5"
    )
    print("  ok: 5 calls observed in histogram (success outcome)")

    # -------------------------------------------------------------
    # FIX #17: open_duration gauge tracks stuck-in-OPEN time
    # -------------------------------------------------------------
    print("-- 6. POSITIVE: open_duration_seconds gauge increments while OPEN --")
    cb = CircuitBreaker("open-duration", failure_threshold=1, recovery_timeout=10)
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    assert cb.state is State.OPEN

    # On transition, gauge is set to 0 (we just opened, monotonic - opened_at ~ 0).
    initial = _metric_value(cb_mod._cb_open_duration, name="open-duration")
    assert 0 <= initial < 0.1, f"initial gauge should be ~0, got {initial}"
    # Sleep a bit, then refresh by triggering _update_open_duration.
    time.sleep(0.2)
    cb._update_open_duration()
    after_sleep = _metric_value(cb_mod._cb_open_duration, name="open-duration")
    assert after_sleep >= 0.15, f"gauge after 0.2s should be ≥0.15, got {after_sleep}"
    print(f"  ok: open-duration gauge {initial:.3f}s → {after_sleep:.3f}s after 0.2s sleep")

    # -------------------------------------------------------------
    # FIX #17 NEGATIVE: open_duration resets to 0 on CLOSED
    # -------------------------------------------------------------
    print("-- 7. NEGATIVE: open_duration drops to 0 on transition to CLOSED --")
    cb = CircuitBreaker("close-resets", failure_threshold=1, recovery_timeout=0.05)
    try:
        asyncio.run(cb.call_async(_fail))
    except ConnectionError:
        pass
    time.sleep(0.1)
    asyncio.run(cb.call_async(_ok))  # HALF_OPEN, then with default threshold=1 → CLOSED
    assert cb.state is State.CLOSED
    duration_after_close = _metric_value(cb_mod._cb_open_duration, name="close-resets")
    assert duration_after_close == 0.0, (
        f"FIX #17 BROKEN: gauge should reset to 0 on CLOSED; got {duration_after_close}"
    )
    print("  ok: open-duration reset to 0 on CLOSED")

    # -------------------------------------------------------------
    # FIX #13: timeout has its own histogram outcome label
    # -------------------------------------------------------------
    print("-- 8. POSITIVE: timeout outcome labelled separately in histogram --")
    cb = CircuitBreaker("timeout-label", failure_threshold=99, call_timeout_s=0.02)

    async def _hang() -> str:
        await asyncio.sleep(5.0)
        return "never"

    timeout_count_before = sum(
        s.value for s in histogram_metric.collect()[0].samples
        if s.name.endswith("_count") and s.labels.get("name") == "timeout-label"
        and s.labels.get("outcome") == "timeout"
    )
    for _ in range(3):
        try:
            asyncio.run(cb.call_async(_hang))
        except (TimeoutError, cb_mod.CircuitOpenError):
            pass
    timeout_count_after = sum(
        s.value for s in histogram_metric.collect()[0].samples
        if s.name.endswith("_count") and s.labels.get("name") == "timeout-label"
        and s.labels.get("outcome") == "timeout"
    )
    assert timeout_count_after - timeout_count_before == 3, (
        f"timeout outcome should be labelled separately; got delta "
        f"{timeout_count_after - timeout_count_before}"
    )
    print("  ok: 3 timeouts → 3 histogram samples with outcome='timeout'")

    print()
    print("ALL 8 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
