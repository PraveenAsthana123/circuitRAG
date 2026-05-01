"""
Circuit Breaker (Design Area 4 — Failure Boundary, Extra — Circuit Breaker).

The circuit breaker protects DocuMind from cascading failures when an
external dependency (Ollama, Qdrant, a SaaS API) is slow or failing.

State machine::

    CLOSED ──(failure_count >= threshold)──► OPEN
      ▲                                        │
      │                                   (timeout expires)
      │                                        │
      └──(success)──── HALF_OPEN ◄────────────┘
                            │
                       (failure)
                            │
                            ▼
                          OPEN

* **CLOSED** — calls go through; failures are counted.
* **OPEN** — calls fail *fast* with :class:`CircuitOpenError` (no network
  round-trip). After ``recovery_timeout`` seconds, transitions to HALF_OPEN.
* **HALF_OPEN** — one probe call is allowed. Success → CLOSED; failure → OPEN.

Why this matters
----------------
Without a breaker, when Ollama is slow your inference-svc pods fill up with
waiting requests, their thread pools exhaust, health checks start failing,
Kubernetes kills the pods, new pods also pile up — a cascading failure.

With a breaker, inference-svc rejects new requests in microseconds, emits a
metric, the frontend degrades gracefully ("service busy, try again"), and
Ollama gets a chance to recover without being hammered.

Instances are **per-dependency, per-process**. If you have 3 Inference pods,
each has its own CB state — that's fine; each observes its own failure rate.

Usage::

    ollama_cb = CircuitBreaker("ollama", failure_threshold=5, recovery_timeout=60)

    async def call_ollama(...):
        return await ollama_cb.call_async(
            lambda: http_client.post("/api/generate", json=...)
        )
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

try:
    from prometheus_client import Counter, Gauge

    _METRICS_ENABLED = True
except ImportError:  # pragma: no cover — optional
    _METRICS_ENABLED = False

from .exceptions import CircuitOpenError


# CB-A3: narrowed default for expected_exception. The pre-fix default
# was `Exception`, which catches caller bugs (KeyError/TypeError) and
# trips the breaker on those — operators see "downstream is degraded"
# when actually the calling code has a typo. Production callers should
# explicitly pass their downstream's exception types.
#
# We re-import lazily (httpx is optional in the core lib but present
# in every service that uses HTTP). On import failure, fall back to
# the OS-level subset which is universally meaningful.
try:
    import httpx as _httpx  # noqa: F401

    _DEFAULT_EXPECTED_EXCEPTION: tuple[type[BaseException], ...] = (
        _httpx.HTTPError,
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
        OSError,
    )
except ImportError:  # pragma: no cover — httpx is in every active service
    _DEFAULT_EXPECTED_EXCEPTION = (
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
        OSError,
    )

T = TypeVar("T")
log = logging.getLogger(__name__)


class _BreakerCallFailed(Exception):
    """Sentinel for record_failure(exc=None). Never raised — only labeled."""


class State(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ---------------------------------------------------------------------------
# Prometheus metrics (defined once, module-level)
# ---------------------------------------------------------------------------
if _METRICS_ENABLED:
    _cb_state = Gauge(
        "documind_circuit_breaker_state",
        "0=closed, 1=half_open, 2=open",
        labelnames=["name"],
    )
    _cb_failures = Counter(
        "documind_circuit_breaker_failures_total",
        "Total failed calls observed by the breaker",
        labelnames=["name"],
    )
    _cb_opens = Counter(
        "documind_circuit_breaker_opens_total",
        "Number of times the circuit has opened",
        labelnames=["name"],
    )
    _cb_rejections = Counter(
        "documind_circuit_breaker_rejections_total",
        "Calls rejected because circuit was open",
        labelnames=["name"],
    )
    _cb_transitions = Counter(
        "documind_circuit_breaker_transitions_total",
        "Breaker state transitions (labelled from→to)",
        labelnames=["name", "from_state", "to_state"],
    )


# Canonical state→numeric mapping used by the shared Gauge.
# Shared with external breakers (e.g. mcp.client._MCPBreaker,
# ObservabilityCircuitBreaker) so a dashboard treats all breakers
# as the same time series regardless of where they live.
_STATE_NUMERIC = {"closed": 0, "half_open": 1, "open": 2}

# Per-name last-seen state so record_breaker_state can spot
# transitions and increment the transitions counter exactly once
# per real change (not once per poll).
_last_state: dict[str, str] = {}


def record_breaker_state(name: str, state: str) -> None:
    """
    Update ``documind_circuit_breaker_state{name=<name>}`` from an
    external breaker that can't subclass :class:`CircuitBreaker`.

    ``state`` must be one of ``"closed" | "half_open" | "open"`` — if
    it isn't, the call is a silent no-op so a misreported state can't
    crash whatever is polling.

    Also increments ``documind_circuit_breaker_transitions_total`` on
    every real state change (no-op when the state is unchanged since
    the last poll — pollers call this every N seconds, we don't want
    one "cycle" of polls to inflate the transition count).

    Typical caller: a background poller in a service lifespan that
    reads ``mcp_client.cb_state`` every N seconds and pushes it here.
    """
    if not _METRICS_ENABLED:
        return
    value = _STATE_NUMERIC.get(state)
    if value is None:
        return
    _cb_state.labels(name=name).set(value)
    prev = _last_state.get(name)
    if prev is not None and prev != state:
        _cb_transitions.labels(
            name=name,
            from_state=prev,
            to_state=state,
        ).inc()
    _last_state[name] = state


class CircuitBreaker:
    """
    A simple failure-count circuit breaker.

    Thread-safety: the Python version uses an asyncio lock. If you need
    calls from multiple threads (rare in DocuMind — we're asyncio), wrap
    with a ``threading.Lock`` in a subclass.

    Args:
        name: Stable identifier for metrics (e.g. ``"ollama"``). Never use
            dynamic tenant-specific names — that cardinality-explodes
            Prometheus.
        failure_threshold: Consecutive failures that trip the breaker.
        recovery_timeout: Seconds to wait before probing in HALF_OPEN.
        expected_exception: Exception class(es) that count as failure.
            Everything else passes through without updating the state.
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type[BaseException] | tuple[type[BaseException], ...] | None = None,
        call_timeout_s: float | None = None,
        # CB-B1 (#2): sliding-window failure rate. When window_size > 0
        # AND threshold_rate is set, the breaker uses a deque of the
        # last N call outcomes; trips when failures/N >= threshold_rate.
        # When window_size = 0 (default), legacy consecutive-failure
        # counter applies — full backward compat.
        failure_window_size: int = 0,
        failure_threshold_rate: float | None = None,
        # CB-B1 (#7): HALF_OPEN concurrency cap. After OPEN→HALF_OPEN
        # transition, only this many concurrent probes are admitted.
        # Excess probes raise CircuitProbingError (subclass of
        # CircuitOpenError, so existing exception-based callers still
        # see CircuitOpenError). Default 1 = textbook HALF_OPEN.
        half_open_max_concurrent: int = 1,
        # CB-B1 (#8): consecutive successes required in HALF_OPEN before
        # CLOSED. Default 1 = legacy behaviour. Setting to 3 prevents
        # a flaky downstream from flipping CLOSED↔OPEN every cycle.
        half_open_success_threshold: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = (
            expected_exception
            if expected_exception is not None
            else _DEFAULT_EXPECTED_EXCEPTION
        )
        self.call_timeout_s = call_timeout_s
        self.failure_window_size = failure_window_size
        self.failure_threshold_rate = failure_threshold_rate
        self.half_open_max_concurrent = max(1, half_open_max_concurrent)
        self.half_open_success_threshold = max(1, half_open_success_threshold)

        self._state: State = State.CLOSED
        self._failure_count = 0
        self._opened_at: float = 0.0
        # CB-B1 (#2): rolling window of last N outcomes (True=success).
        # Bounded deque — memory safe regardless of call rate.
        self._window: deque[bool] = (
            deque(maxlen=failure_window_size) if failure_window_size > 0 else deque(maxlen=1)
        )
        # CB-B1 (#7): HALF_OPEN probe semaphore. Created fresh on each
        # OPEN→HALF_OPEN transition so the count resets cleanly.
        self._half_open_slots = self.half_open_max_concurrent
        # CB-B1 (#8): track consecutive HALF_OPEN successes.
        self._half_open_successes = 0
        self._lock = threading.RLock()
        self._set_metric_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def state(self) -> State:
        return self._state

    @property
    def failures(self) -> int:
        """Current consecutive-failure counter. Read by /health/detailed."""
        return self._failure_count

    # ---- Bool-return guarded API (used by mcp/ for fine-grained control) ----
    # CircuitBreaker.call_async raises CircuitOpenError when OPEN, which is
    # the right shape when the caller wants exception-driven control flow.
    # The MCP client uses a different idiom: it asks the breaker "may I
    # call?" then on rejection persists a draft and returns a degraded
    # ToolResult (NOT raises). Adding bool-returning siblings of the
    # internal sync methods unifies _MCPBreaker into this class without
    # forcing every site to switch to exception-based control flow.
    def allow(self) -> bool:
        """
        Pre-call gate. Returns True when a call may proceed:
          - CLOSED → True
          - OPEN past recovery_timeout → atomic transition to HALF_OPEN,
            return True (slot consumed)
          - HALF_OPEN with slots available → True (slot consumed)
          - HALF_OPEN with NO slots → False (CB-B1 #7 cap)
          - OPEN inside recovery window → False
        """
        with self._lock:
            if self._state is State.OPEN:
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    self._transition(State.HALF_OPEN)
                    # Reset half-open slot count on transition.
                    self._half_open_slots = self.half_open_max_concurrent
                    self._half_open_successes = 0
                # Fall through to HALF_OPEN check below (NOT return True
                # immediately — the cap applies even on transition).
                else:
                    self._bump_rejections()
                    return False
            if self._state is State.HALF_OPEN:
                # CB-B1 #7: enforce probe cap. Each allow() that returns
                # True consumes a slot; record_success/failure releases.
                if self._half_open_slots <= 0:
                    self._bump_rejections()
                    return False
                self._half_open_slots -= 1
                return True
            return True

    def record_success(self) -> None:
        """Mark the most recent gated call as succeeded. Closes a HALF_OPEN."""
        self._on_success_sync()

    def record_failure(self, exc: BaseException | None = None) -> None:
        """
        Mark the most recent gated call as failed. ``exc`` is logged when
        the breaker trips so dashboards can correlate the trip cause; pass
        ``None`` for callers that don't have an exception object handy.
        """
        # Mirror the rest of the API: a missing exc just becomes a generic
        # marker so the failure-class log isn't ``NoneType``.
        cause = exc if exc is not None else _BreakerCallFailed()
        self._on_failure_sync(cause)

    async def call_async(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Invoke ``fn()`` through the breaker. Awaitable entry point.

        CB-A1: when self.call_timeout_s is set, fn() is wrapped in
        asyncio.wait_for; a timeout is raised AND counted as a failure
        so a hung downstream trips the breaker rather than piling up
        in the asyncio task pool.

        CB-A3: asyncio.CancelledError is re-raised BEFORE the breaker
        gets a chance to count it. Upstream timeouts cancelling our
        task look like nothing happened to the breaker, not like a
        downstream failure.
        """
        self._before_call()
        try:
            if self.call_timeout_s is not None:
                result = await asyncio.wait_for(fn(), timeout=self.call_timeout_s)
            else:
                result = await fn()
        except asyncio.CancelledError:
            # CB-A3: cancellations are NOT downstream failures.
            # Re-raise BEFORE the expected_exception except — without
            # this, CancelledError satisfies expected_exception=Exception
            # (legacy default) and spuriously increments failures.
            raise
        except self.expected_exception as exc:
            self._on_failure(exc)
            raise
        self._on_success()
        return result

    def call(self, fn: Callable[[], T]) -> T:
        """Synchronous counterpart. Useful for blocking code paths (rare)."""
        self._before_call()
        try:
            result = fn()
        except self.expected_exception as exc:
            self._on_failure(exc)
            raise
        self._on_success()
        return result

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------
    # CB-A2: post-fix, sync and async paths share one threading.RLock.
    # The two parallel "_sync" mirror methods are gone. Async callers
    # call these same methods (no `await` inside; the lock holds for
    # microseconds while we mutate state).
    # ------------------------------------------------------------------
    def _before_call(self) -> None:
        with self._lock:
            if self._state is State.OPEN:
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    self._transition(State.HALF_OPEN)
                else:
                    self._bump_rejections()
                    raise CircuitOpenError(
                        f"Circuit '{self.name}' is OPEN",
                        details={"name": self.name, "recovery_timeout_s": self.recovery_timeout},
                    )

    def _on_success(self) -> None:
        with self._lock:
            if self._state is State.HALF_OPEN:
                self._half_open_successes += 1
                # Release the slot consumed by allow().
                self._half_open_slots = min(
                    self._half_open_slots + 1, self.half_open_max_concurrent
                )
                # CB-B1 #8: require N consecutive successes before CLOSED.
                if self._half_open_successes >= self.half_open_success_threshold:
                    self._transition(State.CLOSED)
                    self._half_open_successes = 0
                    self._half_open_slots = self.half_open_max_concurrent
            self._failure_count = 0
            # CB-B1 #2: track in rolling window when configured.
            if self.failure_window_size > 0:
                self._window.append(True)

    def _on_failure(self, exc: BaseException) -> None:
        with self._lock:
            self._failure_count += 1
            self._bump_failures()
            # CB-B1 #2: track in rolling window when configured.
            if self.failure_window_size > 0:
                self._window.append(False)

            # Decide whether to trip. Two paths, in priority order:
            #
            # A) HALF_OPEN failure → IMMEDIATE trip back to OPEN
            #    (any HALF_OPEN failure is decisive — downstream is
            #    still broken).
            # B) Sliding-window mode → trip when failures/N ≥ rate
            #    AND window is at least window_size//2 full
            #    (avoid spurious trip on first 1-2 calls).
            # C) Legacy mode → trip on consecutive failures ≥ threshold.
            should_trip = False
            if self._state is State.HALF_OPEN:
                should_trip = True
            elif self._is_window_mode_active():
                if (
                    len(self._window) >= max(1, self.failure_window_size // 2)
                    and self._window_failure_rate() >= (self.failure_threshold_rate or 1.0)
                ):
                    should_trip = True
            elif self._failure_count >= self.failure_threshold:
                should_trip = True

            if should_trip:
                # CB-A4: set _opened_at BEFORE _transition(OPEN) to
                # close the race window.
                self._opened_at = time.monotonic()
                self._transition(State.OPEN)
                # Clear half-open state on (re-)trip.
                self._half_open_successes = 0
                self._bump_opens()
                log.warning(
                    "circuit_open name=%s failures=%d cause=%s",
                    self.name,
                    self._failure_count,
                    type(exc).__name__,
                )

    def _is_window_mode_active(self) -> bool:
        """CB-B1 #2: True iff sliding-window thresholds are configured."""
        return self.failure_window_size > 0 and self.failure_threshold_rate is not None

    def _window_failure_rate(self) -> float:
        """CB-B1 #2: failures/total in the sliding window. 0.0 if empty."""
        if not self._window:
            return 0.0
        failures = sum(1 for ok in self._window if not ok)
        return failures / len(self._window)

    # ------------------------------------------------------------------
    # Backward-compat shims for callers still using the *_sync names.
    # The methods are now identical to the unprefixed versions; the
    # shims keep test_breakers.py + 5 subclasses working unchanged.
    # ------------------------------------------------------------------
    def _before_call_sync(self) -> None:
        self._before_call()

    def _on_success_sync(self) -> None:
        self._on_success()

    def _on_failure_sync(self, exc: BaseException) -> None:
        self._on_failure(exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _transition(self, new: State) -> None:
        if self._state is not new:
            log.info("circuit_transition name=%s from=%s to=%s", self.name, self._state.value, new.value)
        self._state = new
        self._set_metric_state()

    def _set_metric_state(self) -> None:
        # Delegate to the shared helper so the transition counter
        # increments for THIS breaker's transitions too — keeps the
        # gauge and the counter in lockstep regardless of which kind
        # of breaker is reporting.
        record_breaker_state(self.name, self._state.value)

    def _bump_failures(self) -> None:
        if _METRICS_ENABLED:
            _cb_failures.labels(name=self.name).inc()

    def _bump_opens(self) -> None:
        if _METRICS_ENABLED:
            _cb_opens.labels(name=self.name).inc()

    def _bump_rejections(self) -> None:
        if _METRICS_ENABLED:
            _cb_rejections.labels(name=self.name).inc()

    def __repr__(self) -> str:  # pragma: no cover — cosmetic
        return (
            f"CircuitBreaker(name={self.name!r}, state={self._state.value}, "
            f"failures={self._failure_count}/{self.failure_threshold})"
        )
