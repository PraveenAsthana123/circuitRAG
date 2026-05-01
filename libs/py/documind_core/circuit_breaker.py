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
    from prometheus_client import Counter, Gauge, Histogram

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
    # CB-C #15: exception_class label so operators can answer
    # "is it timeouts? 503s? connection-refused?" without grepping logs.
    # Cardinality-bounded by the Python exception class names of the
    # caller's downstream — small bounded set in practice.
    _cb_failures = Counter(
        "documind_circuit_breaker_failures_total",
        "Total failed calls observed by the breaker",
        labelnames=["name", "exception_class"],
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
    # CB-C #14: success_total — denominator for calculated failure rate.
    # Without this, operators can't compute rate from Prometheus.
    _cb_successes = Counter(
        "documind_circuit_breaker_successes_total",
        "Total successful calls observed by the breaker",
        labelnames=["name"],
    )
    # CB-C #13: call latency histogram — leading indicator
    # ("p99 climbs before breaker trips").
    _cb_call_seconds = Histogram(
        "documind_circuit_breaker_call_seconds",
        "Call duration through the breaker (seconds). Includes both "
        "successful and failed calls; failures may have shorter or "
        "longer durations depending on whether they hit a timeout.",
        labelnames=["name", "outcome"],  # outcome: success | failure | timeout
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    )
    # CB-C #16: probe outcome — "is downstream actually getting better?"
    # is the single most important signal during incident response.
    _cb_half_open_probes = Counter(
        "documind_circuit_breaker_half_open_probes_total",
        "HALF_OPEN probe outcomes (success | failure)",
        labelnames=["name", "outcome"],
    )
    # CB-C #17: how long has this breaker been OPEN? Operators want
    # the duration at a glance during incidents. Gauge updates on
    # every state-change; cleared to 0 on CLOSED.
    _cb_open_duration = Gauge(
        "documind_circuit_breaker_open_duration_seconds",
        "How long the breaker has been in its current OPEN state. 0 when CLOSED/HALF_OPEN.",
        labelnames=["name"],
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
        # CB-B2 (#9): exponential backoff on recovery_timeout. When
        # backoff_factor > 1.0, each consecutive trip multiplies the
        # recovery delay (capped at recovery_timeout_max). Reset on
        # clean CLOSED. Default 1.0 = no backoff (legacy).
        backoff_factor: float = 1.0,
        recovery_timeout_max: float = 600.0,
        backoff_jitter: float = 0.1,  # ±10% jitter to prevent thundering herd
        # CB-B2 (#10): bulkhead — cap concurrent in-flight calls even
        # when CLOSED. Prevents one slow downstream from monopolising
        # the asyncio task pool. Default None = no cap (legacy).
        max_concurrent: int | None = None,
        # CB-B2 (#12): slow-call detection. A call that returns success
        # in > slow_call_threshold_s counts as a "slow" outcome. When
        # slow_call_rate (over the same sliding window) exceeds the
        # threshold rate, the breaker trips even with 0% errors.
        # Default None = disabled (legacy).
        slow_call_threshold_s: float | None = None,
        slow_call_rate: float = 0.5,
        # CB-D #20: state-change callback. Fires exactly once per real
        # transition. Exceptions raised by the callback are caught and
        # logged — the breaker continues working even if the callback
        # is broken (paging integrations are not on the critical path).
        # Signature: (from_state, to_state, breaker_name) -> None.
        on_state_change: Callable[[State, State, str], None] | None = None,
        # CB-F #22: optional health probe. Returns True when downstream
        # is reachable per its own /health endpoint. When set and probe
        # returns True during OPEN, breaker can short-circuit
        # recovery_timeout and transition to HALF_OPEN. When probe is
        # None (default), breaker uses time-based recovery only (legacy).
        health_check: Callable[[], bool] | None = None,
        # CB-F #26: per-tenant breaker scope. When set, the metric
        # cardinality includes (name, tenant_id) so tenant A's trips
        # don't trip tenant B's view. Each (name, tenant_id) is a
        # logically separate breaker; instances are NOT shared.
        # Default None = global scope (legacy).
        tenant_id: str | None = None,
        # CB-F #27: OTel baggage propagation. When True and
        # opentelemetry-baggage is installed, every call_async writes
        # cb.<name>.state into the active span's baggage so distributed
        # traces show every span's view of every breaker it depended on.
        # Default False (opt-in; adds latency on every call).
        otel_baggage: bool = False,
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
        self.backoff_factor = max(1.0, backoff_factor)
        self.recovery_timeout_max = max(recovery_timeout, recovery_timeout_max)
        self.backoff_jitter = max(0.0, min(1.0, backoff_jitter))
        self.max_concurrent = max_concurrent
        self.slow_call_threshold_s = slow_call_threshold_s
        self.slow_call_rate = max(0.0, min(1.0, slow_call_rate))
        self.on_state_change = on_state_change
        self.health_check = health_check
        self.tenant_id = tenant_id
        self.otel_baggage = otel_baggage
        # CB-D #19: operator-forced state.
        self._forced_state: State | None = None
        self._forced_reason: str | None = None
        self._forced_until: float | None = None

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
        # CB-B2 (#9): exponential backoff state.
        self._consecutive_open_count = 0
        # CB-B2 (#10): bulkhead semaphore. Created lazily so the
        # breaker can be constructed outside an asyncio context.
        self._bulkhead: asyncio.Semaphore | None = None
        # CB-B2 (#12): slow-call rolling window (parallel to failure window).
        # Each entry is True iff the call exceeded slow_call_threshold_s.
        self._slow_window: deque[bool] = (
            deque(maxlen=failure_window_size) if failure_window_size > 0 else deque(maxlen=1)
        )
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
                if time.monotonic() - self._opened_at >= self._effective_recovery_timeout():
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

    # ------------------------------------------------------------------
    # CB-D #19: operator override API.
    #
    # Operators need a knob for: planned maintenance (force_open),
    # known-good downstream after a fix (force_closed), and counter-
    # reset after manually verifying recovery (reset). Each emits a
    # distinct log line so audit can show "this state was forced."
    # ------------------------------------------------------------------
    def force_open(
        self,
        *,
        reason: str = "operator_forced",
        ttl_s: float | None = 3600,
    ) -> None:
        """Force the breaker OPEN. ``ttl_s`` is the auto-expiry — defaults
        to 1 hour so a forgotten force eventually self-clears. Set None
        to force-forever (operator must call reset() to undo).
        """
        with self._lock:
            self._forced_state = State.OPEN
            self._forced_reason = reason
            self._forced_until = (time.monotonic() + ttl_s) if ttl_s is not None else None
            self._opened_at = time.monotonic()
            self._transition(State.OPEN)
            log.warning(
                "circuit_force_open name=%s reason=%s ttl=%s",
                self.name, reason, ttl_s,
            )

    def force_closed(
        self,
        *,
        reason: str = "operator_forced",
        ttl_s: float | None = None,
    ) -> None:
        """Force the breaker CLOSED. ``ttl_s`` defaults to None (until
        operator calls reset()) — a forced-closed should hold until the
        operator explicitly relinquishes control."""
        with self._lock:
            self._forced_state = State.CLOSED
            self._forced_reason = reason
            self._forced_until = (time.monotonic() + ttl_s) if ttl_s is not None else None
            self._failure_count = 0
            self._consecutive_open_count = 0
            self._half_open_successes = 0
            self._half_open_slots = self.half_open_max_concurrent
            self._window.clear()
            self._slow_window.clear()
            self._transition(State.CLOSED)
            log.warning(
                "circuit_force_closed name=%s reason=%s ttl=%s",
                self.name, reason, ttl_s,
            )

    def reset(self, *, reason: str = "operator_reset") -> None:
        """Reset to CLOSED with all counters zeroed. Releases any
        force_open/force_closed override."""
        with self._lock:
            self._forced_state = None
            self._forced_reason = None
            self._forced_until = None
            self._failure_count = 0
            self._consecutive_open_count = 0
            self._half_open_successes = 0
            self._half_open_slots = self.half_open_max_concurrent
            self._window.clear()
            self._slow_window.clear()
            self._transition(State.CLOSED)
            log.warning("circuit_reset name=%s reason=%s", self.name, reason)

    @property
    def is_forced(self) -> bool:
        """True if currently in an operator-forced state (open or closed).
        Caller can check this to decide whether to display a 'forced'
        badge on dashboards."""
        with self._lock:
            self._maybe_clear_expired_force()
            return self._forced_state is not None

    @property
    def forced_reason(self) -> str | None:
        with self._lock:
            self._maybe_clear_expired_force()
            return self._forced_reason

    def _maybe_clear_expired_force(self) -> None:
        """Auto-expire forced state when ttl elapses. Called inside locks."""
        if (
            self._forced_state is not None
            and self._forced_until is not None
            and time.monotonic() >= self._forced_until
        ):
            log.warning(
                "circuit_force_expired name=%s prior_reason=%s",
                self.name, self._forced_reason,
            )
            self._forced_state = None
            self._forced_reason = None
            self._forced_until = None

    async def call_async(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Invoke ``fn()`` through the breaker. Awaitable entry point.

        CB-A1: per-call timeout via asyncio.wait_for.
        CB-A3: CancelledError pass-through.
        CB-B2 #10: bulkhead — `max_concurrent` cap held via Semaphore.
        CB-B2 #12: slow-call detection — calls > slow_call_threshold_s
                   count toward the slow-call rate even on success.
        """
        self._before_call()

        # CB-B2 #10 (bulkhead): acquire a slot or fail fast.
        if self.max_concurrent is not None:
            sem = self._get_bulkhead()
            # Non-blocking acquire — refuse rather than queue.
            if sem.locked() and sem._value <= 0:  # type: ignore[attr-defined]
                # Fail fast: don't await indefinitely.
                self._bump_rejections()
                raise CircuitOpenError(
                    f"Circuit '{self.name}' bulkhead full ({self.max_concurrent})",
                    details={"name": self.name, "reason": "bulkhead_overloaded"},
                )
            await sem.acquire()
        try:
            start = time.monotonic()
            try:
                if self.call_timeout_s is not None:
                    result = await asyncio.wait_for(fn(), timeout=self.call_timeout_s)
                else:
                    result = await fn()
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError as exc:
                # CB-C #13: latency histogram for timeouts.
                self._record_call_duration(time.monotonic() - start, "timeout")
                self._on_failure(exc)
                raise
            except self.expected_exception as exc:
                # CB-C #13: latency histogram for failures.
                self._record_call_duration(time.monotonic() - start, "failure")
                self._on_failure(exc)
                raise

            # Success path — slow-call detection happens inside _on_success.
            duration_s = time.monotonic() - start
            self._on_success(duration_s=duration_s)
            return result
        finally:
            if self.max_concurrent is not None and self._bulkhead is not None:
                self._bulkhead.release()

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
        # CB-F #27: OTel baggage write — outside the lock since baggage
        # API is fast and reads only.
        self._write_otel_baggage()
        with self._lock:
            self._maybe_clear_expired_force()
            # CB-D #19: forced state bypasses the normal state machine.
            if self._forced_state is State.OPEN:
                self._bump_rejections()
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is OPEN (forced)",
                    details={
                        "name": self.name,
                        "forced": True,
                        "reason": self._forced_reason,
                    },
                )
            if self._forced_state is State.CLOSED:
                return
            if self._state is State.OPEN:
                # CB-F #22: health probe can short-circuit recovery_timeout.
                # When probe returns True, transition immediately to
                # HALF_OPEN regardless of how much time elapsed.
                if self.health_check is not None:
                    try:
                        if self.health_check():
                            log.info(
                                "circuit_health_probe_recovered name=%s",
                                self.name,
                            )
                            self._transition(State.HALF_OPEN)
                            self._half_open_slots = self.half_open_max_concurrent
                            self._half_open_successes = 0
                            return
                    except Exception:  # noqa: BLE001 — broken probe → ignore
                        pass
                if time.monotonic() - self._opened_at >= self._effective_recovery_timeout():
                    self._transition(State.HALF_OPEN)
                else:
                    self._bump_rejections()
                    raise CircuitOpenError(
                        f"Circuit '{self.name}' is OPEN",
                        details={"name": self.name, "recovery_timeout_s": self.recovery_timeout},
                    )

    def _write_otel_baggage(self) -> None:
        """CB-F #27: write breaker state into the active OTel span's
        baggage so distributed traces show every span's view of every
        breaker it depended on. Opt-in (default off — adds latency on
        every call). Silent no-op if opentelemetry-api isn't installed.
        """
        if not self.otel_baggage:
            return
        try:
            from opentelemetry import baggage as _baggage  # type: ignore[import-not-found]
            from opentelemetry import context as _ctx  # type: ignore[import-not-found]
            ctx = _baggage.set_baggage(f"cb.{self.name}.state", self._state.value)
            _ctx.attach(ctx)
        except Exception:  # noqa: BLE001 — OTel optional / detach gracefully
            pass

    def _on_success(self, *, duration_s: float | None = None) -> None:
        with self._lock:
            # CB-C #14: success counter
            self._bump_successes()
            # CB-C #13: latency histogram
            if duration_s is not None:
                self._record_call_duration(duration_s, "success")
            # CB-C #16: probe outcome counter
            if self._state is State.HALF_OPEN:
                self._bump_probe("success")
                self._half_open_successes += 1
                self._half_open_slots = min(
                    self._half_open_slots + 1, self.half_open_max_concurrent
                )
                if self._half_open_successes >= self.half_open_success_threshold:
                    self._transition(State.CLOSED)
                    self._half_open_successes = 0
                    self._half_open_slots = self.half_open_max_concurrent
                    # CB-B2 #9: clean CLOSED resets backoff multiplier.
                    self._consecutive_open_count = 0
            self._failure_count = 0
            if self.failure_window_size > 0:
                self._window.append(True)
                # CB-B2 #12: record slow-vs-fast for slow-call detection.
                if duration_s is not None and self.slow_call_threshold_s is not None:
                    is_slow = duration_s > self.slow_call_threshold_s
                    self._slow_window.append(is_slow)
                    # Trip on slow-call rate? Only when we have enough
                    # samples (anti-spurious, mirrors failure-rate logic).
                    if (
                        self._state is State.CLOSED
                        and len(self._slow_window) >= max(1, self.failure_window_size // 2)
                        and self._slow_call_rate() >= self.slow_call_rate
                    ):
                        self._opened_at = time.monotonic()
                        self._transition(State.OPEN)
                        self._consecutive_open_count += 1
                        self._bump_opens()
                        log.warning(
                            "circuit_open name=%s reason=slow_call slow_rate=%.2f",
                            self.name, self._slow_call_rate(),
                        )

    def _slow_call_rate(self) -> float:
        """CB-B2 #12: ratio of slow calls in the rolling window."""
        if not self._slow_window:
            return 0.0
        slow = sum(1 for s in self._slow_window if s)
        return slow / len(self._slow_window)

    def _get_bulkhead(self) -> asyncio.Semaphore:
        """CB-B2 #10: lazily create the bulkhead semaphore.

        Lazy because asyncio.Semaphore() in __init__ would bind to
        whatever event loop happens to be active at construction time
        (often there is none yet). Created on first call_async use.
        """
        if self._bulkhead is None:
            assert self.max_concurrent is not None
            self._bulkhead = asyncio.Semaphore(self.max_concurrent)
        return self._bulkhead

    def _effective_recovery_timeout(self) -> float:
        """CB-B2 #9: exponential backoff with jitter.

        recovery = min(base * factor**(consecutive_open - 1), max) ± jitter.
        First trip uses base directly (no exponent yet). Reset to 0 on
        clean CLOSED via _on_success.
        """
        import random
        if self._consecutive_open_count <= 1 or self.backoff_factor <= 1.0:
            base = self.recovery_timeout
        else:
            base = min(
                self.recovery_timeout * (self.backoff_factor ** (self._consecutive_open_count - 1)),
                self.recovery_timeout_max,
            )
        if self.backoff_jitter > 0:
            base = base * (1.0 + random.uniform(-self.backoff_jitter, self.backoff_jitter))
        return max(0.001, base)

    def _on_failure(self, exc: BaseException) -> None:
        with self._lock:
            self._failure_count += 1
            # CB-C #15: include exception_class label.
            self._bump_failures(exc_class=type(exc).__name__)
            # CB-C #16: probe outcome counter for HALF_OPEN failures.
            if self._state is State.HALF_OPEN:
                self._bump_probe("failure")
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
                # CB-B2 #9: track consecutive trips for backoff calc.
                self._consecutive_open_count += 1
                # Clear half-open state on (re-)trip.
                self._half_open_successes = 0
                self._bump_opens()
                log.warning(
                    "circuit_open name=%s failures=%d cause=%s consecutive_opens=%d",
                    self.name,
                    self._failure_count,
                    type(exc).__name__,
                    self._consecutive_open_count,
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
        prev = self._state
        if prev is not new:
            log.info("circuit_transition name=%s from=%s to=%s", self.name, prev.value, new.value)
        self._state = new
        self._set_metric_state()
        # CB-C #17: update stuck-in-OPEN duration gauge on every transition.
        self._update_open_duration()
        # CB-D #20: fire on_state_change callback exactly once per real
        # transition. Caught + logged — broken callback must NOT crash
        # the breaker (paging hooks are out-of-band, not critical-path).
        if prev is not new and self.on_state_change is not None:
            try:
                self.on_state_change(prev, new, self.name)
            except Exception as cb_exc:  # noqa: BLE001
                log.error(
                    "circuit_breaker_callback_failed name=%s from=%s to=%s err=%s",
                    self.name, prev.value, new.value, type(cb_exc).__name__,
                )

    def _set_metric_state(self) -> None:
        # Delegate to the shared helper so the transition counter
        # increments for THIS breaker's transitions too — keeps the
        # gauge and the counter in lockstep regardless of which kind
        # of breaker is reporting.
        record_breaker_state(self.name, self._state.value)

    def _bump_failures(self, exc_class: str = "unknown") -> None:
        # CB-C #15: include exception_class label. Bounded set in
        # practice — only the caller's expected_exception types.
        if _METRICS_ENABLED:
            _cb_failures.labels(name=self.name, exception_class=exc_class).inc()

    def _bump_opens(self) -> None:
        if _METRICS_ENABLED:
            _cb_opens.labels(name=self.name).inc()

    def _bump_rejections(self) -> None:
        if _METRICS_ENABLED:
            _cb_rejections.labels(name=self.name).inc()

    def _bump_successes(self) -> None:
        # CB-C #14: success counter — the denominator for any
        # calculated failure-rate alert.
        if _METRICS_ENABLED:
            _cb_successes.labels(name=self.name).inc()

    def _bump_probe(self, outcome: str) -> None:
        # CB-C #16: probe outcome counter. outcome ∈ {success, failure}.
        if _METRICS_ENABLED:
            _cb_half_open_probes.labels(name=self.name, outcome=outcome).inc()

    def _record_call_duration(self, duration_s: float, outcome: str) -> None:
        # CB-C #13: call duration histogram. outcome ∈ {success, failure, timeout}.
        if _METRICS_ENABLED:
            _cb_call_seconds.labels(name=self.name, outcome=outcome).observe(duration_s)

    def _update_open_duration(self) -> None:
        # CB-C #17: stuck-in-OPEN gauge. Called on every transition.
        # When OPEN, gauge holds (now - opened_at). When CLOSED/HALF_OPEN,
        # gauge is 0.
        if not _METRICS_ENABLED:
            return
        if self._state is State.OPEN:
            duration = max(0.0, time.monotonic() - self._opened_at)
            _cb_open_duration.labels(name=self.name).set(duration)
        else:
            _cb_open_duration.labels(name=self.name).set(0.0)

    def __repr__(self) -> str:  # pragma: no cover — cosmetic
        return (
            f"CircuitBreaker(name={self.name!r}, state={self._state.value}, "
            f"failures={self._failure_count}/{self.failure_threshold})"
        )
