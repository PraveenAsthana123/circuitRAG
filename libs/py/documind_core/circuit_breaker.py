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
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

try:
    from prometheus_client import Counter, Gauge
    _METRICS_ENABLED = True
except ImportError:  # pragma: no cover — optional
    _METRICS_ENABLED = False

from .exceptions import CircuitOpenError

T = TypeVar("T")
log = logging.getLogger(__name__)


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
        expected_exception: type[BaseException] | tuple[type[BaseException], ...] = Exception,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self._state: State = State.CLOSED
        self._failure_count = 0
        self._opened_at: float = 0.0
        self._lock = asyncio.Lock()
        self._set_metric_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def state(self) -> State:
        return self._state

    async def call_async(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Invoke ``fn()`` through the breaker. Awaitable entry point."""
        await self._before_call()
        try:
            result = await fn()
        except self.expected_exception as exc:
            await self._on_failure(exc)
            raise
        await self._on_success()
        return result

    def call(self, fn: Callable[[], T]) -> T:
        """Synchronous counterpart. Useful for blocking code paths (rare)."""
        self._before_call_sync()
        try:
            result = fn()
        except self.expected_exception as exc:
            self._on_failure_sync(exc)
            raise
        self._on_success_sync()
        return result

    # ------------------------------------------------------------------
    # State transitions (async)
    # ------------------------------------------------------------------
    async def _before_call(self) -> None:
        async with self._lock:
            if self._state is State.OPEN:
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    self._transition(State.HALF_OPEN)
                else:
                    self._bump_rejections()
                    raise CircuitOpenError(
                        f"Circuit '{self.name}' is OPEN",
                        details={"name": self.name, "recovery_timeout_s": self.recovery_timeout},
                    )

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state is State.HALF_OPEN:
                self._transition(State.CLOSED)
            self._failure_count = 0

    async def _on_failure(self, exc: BaseException) -> None:
        async with self._lock:
            self._failure_count += 1
            self._bump_failures()
            if self._state is State.HALF_OPEN or self._failure_count >= self.failure_threshold:
                self._transition(State.OPEN)
                self._opened_at = time.monotonic()
                self._bump_opens()
                log.warning(
                    "circuit_open name=%s failures=%d cause=%s",
                    self.name, self._failure_count, type(exc).__name__,
                )

    # ------------------------------------------------------------------
    # State transitions (sync — mirror)
    # ------------------------------------------------------------------
    def _before_call_sync(self) -> None:
        if self._state is State.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._transition(State.HALF_OPEN)
            else:
                self._bump_rejections()
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is OPEN",
                    details={"name": self.name},
                )

    def _on_success_sync(self) -> None:
        if self._state is State.HALF_OPEN:
            self._transition(State.CLOSED)
        self._failure_count = 0

    def _on_failure_sync(self, exc: BaseException) -> None:
        self._failure_count += 1
        self._bump_failures()
        if self._state is State.HALF_OPEN or self._failure_count >= self.failure_threshold:
            self._transition(State.OPEN)
            self._opened_at = time.monotonic()
            self._bump_opens()
            log.warning(
                "circuit_open name=%s failures=%d cause=%s",
                self.name, self._failure_count, type(exc).__name__,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _transition(self, new: State) -> None:
        if self._state is not new:
            log.info("circuit_transition name=%s from=%s to=%s", self.name, self._state.value, new.value)
        self._state = new
        self._set_metric_state()

    def _set_metric_state(self) -> None:
        if not _METRICS_ENABLED:
            return
        mapping = {State.CLOSED: 0, State.HALF_OPEN: 1, State.OPEN: 2}
        _cb_state.labels(name=self.name).set(mapping[self._state])

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
