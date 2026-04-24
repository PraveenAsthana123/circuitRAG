"""
Specialized circuit breakers (Design Area 4 + Extra-CB, plus AI/RAG-specific).

Four specialized breakers, each protecting against a failure mode the base
:class:`.circuit_breaker.CircuitBreaker` does not catch on its own:

1. :class:`RetrievalCircuitBreaker` — **quality-aware**. The retrieval call
   can succeed (HTTP 200) but return garbage (all scores < threshold). The
   base breaker misses this because no exception was raised. This breaker
   samples the *top relevance score* of each retrieval and opens when a
   rolling average drops below ``min_quality`` for ``quality_window``
   consecutive queries.

2. :class:`TokenCircuitBreaker` — **budget-aware, pre-flight**. Rejects
   calls BEFORE they happen, when a tenant's daily / monthly token budget
   is already exhausted, OR when a single request is on track to exceed
   the per-request cap. Integrates with finops-svc's budgets table.

3. :class:`AgentLoopCircuitBreaker` — **per-run**. An agent can be
   misbehaving in ONE user session without the whole process being
   unhealthy. State is scoped to a single agent run. Opens on: max_steps,
   total_timeout, or loop detection (same action N times in a row).

4. :class:`ObservabilityCircuitBreaker` — **inverted polarity**. When OPEN,
   observability export is SKIPPED (not retried). Protects the app from
   a dead OTel collector / Jaeger / Loki hanging every request on export.
   Observability MUST NEVER take the app down.

All four emit Prometheus metrics under distinct names so they're
separately trackable on the SLO dashboard.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, TypeVar

try:
    from prometheus_client import Counter, Gauge
    _METRICS = True
except ImportError:  # pragma: no cover
    _METRICS = False

from .circuit_breaker import CircuitBreaker, State
from .exceptions import (
    AppError,
    CircuitOpenError,
    ExternalServiceError,
    PolicyViolationError,
    RateLimitedError,
)

log = logging.getLogger(__name__)

T = TypeVar("T")


# ============================================================================
# 1. RetrievalCircuitBreaker
# ============================================================================

@dataclass
class RetrievalSample:
    """A single retrieval outcome, used to compute rolling quality."""

    top_score: float
    n_results: int
    latency_ms: float


if _METRICS:
    _retr_quality = Gauge(
        "documind_retrieval_quality",
        "Rolling average of top retrieval score (0.0 to 1.0)",
        labelnames=["name"],
    )
    _retr_opens = Counter(
        "documind_retrieval_quality_opens_total",
        "Times the quality breaker opened",
        labelnames=["name"],
    )


class RetrievalCircuitBreaker(CircuitBreaker):
    """
    Extends the base breaker with a rolling *quality* check.

    Opens when EITHER:

    * ``failure_threshold`` consecutive exceptions (base behaviour), OR
    * rolling average of ``top_score`` over last ``quality_window``
      samples falls below ``min_quality``.

    Usage::

        retr_cb = RetrievalCircuitBreaker(
            "retrieval",
            failure_threshold=5,
            recovery_timeout=60,
            min_quality=0.35,
            quality_window=20,
        )

        async def search(q):
            chunks = await retr_cb.call_async(lambda: do_search(q))
            retr_cb.record_quality(
                top_score=chunks[0].score if chunks else 0.0,
                n_results=len(chunks),
                latency_ms=...,
            )
            return chunks
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        min_quality: float = 0.35,
        quality_window: int = 20,
        min_results: int = 1,
    ) -> None:
        super().__init__(
            name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            expected_exception=(ExternalServiceError, Exception),
        )
        self._min_quality = min_quality
        self._min_results = min_results
        self._samples: deque[RetrievalSample] = deque(maxlen=quality_window)

    def record_quality(
        self,
        *,
        top_score: float,
        n_results: int,
        latency_ms: float,
    ) -> None:
        """Must be called after a successful retrieval. Triggers a quality
        check; opens the breaker if the rolling avg drops below threshold."""
        self._samples.append(
            RetrievalSample(top_score=top_score, n_results=n_results, latency_ms=latency_ms)
        )

        if len(self._samples) < self._samples.maxlen:
            # Not enough data yet — no decision.
            return

        avg = sum(s.top_score for s in self._samples) / len(self._samples)
        if _METRICS:
            _retr_quality.labels(name=self.name).set(avg)

        # Too many empty results also counts as degraded
        empty = sum(1 for s in self._samples if s.n_results < self._min_results)

        if avg < self._min_quality or empty > len(self._samples) // 2:
            # Open the breaker due to quality, not failure count
            if self._state is not State.OPEN:
                log.warning(
                    "retrieval_quality_breach name=%s avg_top_score=%.3f threshold=%.3f empty=%d/%d",
                    self.name, avg, self._min_quality, empty, len(self._samples),
                )
                self._transition(State.OPEN)
                self._opened_at = time.monotonic()
                if _METRICS:
                    _retr_opens.labels(name=self.name).inc()


# ============================================================================
# 2. TokenCircuitBreaker
# ============================================================================

class TokenBreakerDecision(str, Enum):
    ALLOW = "allow"
    WARN = "warn"            # approaching limit; proceed but log
    REJECT_DAILY = "reject_daily"
    REJECT_MONTHLY = "reject_monthly"
    REJECT_REQUEST = "reject_request"


@dataclass
class TokenCheck:
    decision: TokenBreakerDecision
    tokens_used_today: int
    daily_budget: int
    tokens_used_month: int
    monthly_budget: int
    percent_used_today: float


if _METRICS:
    _token_rejects = Counter(
        "documind_token_breaker_rejects_total",
        "Pre-flight rejections by the token breaker",
        labelnames=["tenant", "reason"],
    )
    _token_warns = Counter(
        "documind_token_breaker_warns_total",
        "Warnings (>= 80% budget used)",
        labelnames=["tenant"],
    )


class TokenCircuitBreaker:
    """
    Pre-flight token-budget check.

    Call :meth:`check` BEFORE the expensive LLM call. If it returns a reject
    decision, short-circuit by raising :class:`PolicyViolationError`.

    Call :meth:`record_usage` AFTER the call with the actual tokens used
    (prompt + completion). This updates the in-memory counters. In
    production, FinOps consumes the ``cost.events`` Kafka topic and is the
    authoritative source — this breaker is a fast local cache.

    Thresholds:
    * WARN at 80% of daily budget
    * REJECT_DAILY at >= 100% of daily budget
    * REJECT_MONTHLY at >= 100% of monthly budget
    * REJECT_REQUEST if ``request_tokens > max_tokens_per_request``
    """

    def __init__(
        self,
        *,
        max_tokens_per_request: int = 32_000,
        warn_percent: float = 0.8,
    ) -> None:
        self._max_req = max_tokens_per_request
        self._warn = warn_percent
        # Per-tenant counters; in a multi-pod deploy these sync from Redis
        # or via Kafka consumer of cost.events. For the demo, in-process.
        self._daily: dict[str, int] = {}
        self._monthly: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def check(
        self,
        *,
        tenant_id: str,
        estimated_tokens: int,
        daily_budget: int,
        monthly_budget: int,
    ) -> TokenCheck:
        """Pre-flight: decide whether to allow / warn / reject."""
        if estimated_tokens > self._max_req:
            if _METRICS:
                _token_rejects.labels(tenant=tenant_id, reason="per_request").inc()
            return TokenCheck(
                decision=TokenBreakerDecision.REJECT_REQUEST,
                tokens_used_today=self._daily.get(tenant_id, 0),
                daily_budget=daily_budget,
                tokens_used_month=self._monthly.get(tenant_id, 0),
                monthly_budget=monthly_budget,
                percent_used_today=0.0,
            )

        async with self._lock:
            used_today = self._daily.get(tenant_id, 0)
            used_month = self._monthly.get(tenant_id, 0)

        if used_today + estimated_tokens >= daily_budget:
            if _METRICS:
                _token_rejects.labels(tenant=tenant_id, reason="daily").inc()
            return TokenCheck(
                decision=TokenBreakerDecision.REJECT_DAILY,
                tokens_used_today=used_today,
                daily_budget=daily_budget,
                tokens_used_month=used_month,
                monthly_budget=monthly_budget,
                percent_used_today=used_today / max(daily_budget, 1),
            )
        if used_month + estimated_tokens >= monthly_budget:
            if _METRICS:
                _token_rejects.labels(tenant=tenant_id, reason="monthly").inc()
            return TokenCheck(
                decision=TokenBreakerDecision.REJECT_MONTHLY,
                tokens_used_today=used_today,
                daily_budget=daily_budget,
                tokens_used_month=used_month,
                monthly_budget=monthly_budget,
                percent_used_today=used_today / max(daily_budget, 1),
            )

        pct = (used_today + estimated_tokens) / max(daily_budget, 1)
        if pct >= self._warn:
            if _METRICS:
                _token_warns.labels(tenant=tenant_id).inc()
            return TokenCheck(
                decision=TokenBreakerDecision.WARN,
                tokens_used_today=used_today,
                daily_budget=daily_budget,
                tokens_used_month=used_month,
                monthly_budget=monthly_budget,
                percent_used_today=pct,
            )

        return TokenCheck(
            decision=TokenBreakerDecision.ALLOW,
            tokens_used_today=used_today,
            daily_budget=daily_budget,
            tokens_used_month=used_month,
            monthly_budget=monthly_budget,
            percent_used_today=pct,
        )

    async def check_or_raise(
        self,
        *,
        tenant_id: str,
        estimated_tokens: int,
        daily_budget: int,
        monthly_budget: int,
    ) -> TokenCheck:
        """Raise :class:`PolicyViolationError` on reject; return on allow/warn."""
        result = await self.check(
            tenant_id=tenant_id,
            estimated_tokens=estimated_tokens,
            daily_budget=daily_budget,
            monthly_budget=monthly_budget,
        )
        if result.decision in (
            TokenBreakerDecision.REJECT_DAILY,
            TokenBreakerDecision.REJECT_MONTHLY,
            TokenBreakerDecision.REJECT_REQUEST,
        ):
            raise PolicyViolationError(
                f"Token budget exceeded: {result.decision.value}",
                details={
                    "tenant_id": tenant_id,
                    "reason": result.decision.value,
                    "tokens_today": result.tokens_used_today,
                    "daily_budget": result.daily_budget,
                },
            )
        return result

    async def record_usage(
        self,
        *,
        tenant_id: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Update in-memory counters after a successful LLM call."""
        total = prompt_tokens + completion_tokens
        async with self._lock:
            self._daily[tenant_id] = self._daily.get(tenant_id, 0) + total
            self._monthly[tenant_id] = self._monthly.get(tenant_id, 0) + total

    async def reset_daily(self, tenant_id: str | None = None) -> None:
        """Called by a cron at midnight UTC — or on demand via admin API."""
        async with self._lock:
            if tenant_id is None:
                self._daily.clear()
            else:
                self._daily.pop(tenant_id, None)


# ============================================================================
# 3. AgentLoopCircuitBreaker
# ============================================================================

class AgentStopReason(str, Enum):
    NONE = "none"
    MAX_STEPS = "max_steps"
    TIMEOUT = "timeout"
    LOOP_DETECTED = "loop_detected"
    TOOL_BUDGET = "tool_budget"
    USER_ABORT = "user_abort"


@dataclass
class AgentStep:
    action: str
    result_hash: str = ""


if _METRICS:
    _agent_stops = Counter(
        "documind_agent_stops_total",
        "Agent runs stopped by the loop breaker",
        labelnames=["reason"],
    )
    _agent_steps = Counter(
        "documind_agent_steps_total",
        "Total agent steps executed",
        labelnames=["agent"],
    )


class AgentLoopCircuitBreaker:
    """
    One instance PER agent run (not per process). Holds the loop guardrails
    the spec Area 11 requires for safe multi-step reasoning.

    Guardrails:

    * ``max_steps`` — hard cap on steps in one run.
    * ``total_timeout_s`` — wall-clock cap for the whole run.
    * ``per_step_timeout_s`` — per-step wall-clock cap.
    * ``loop_detection_window`` — if the same ``action`` occurs N times in a
      row OR the same ``(action, result_hash)`` repeats, we've looped.
    * ``max_tool_calls`` per tool name — prevents infinite tool storms.

    Usage::

        agent_cb = AgentLoopCircuitBreaker(
            agent_name="multi_hop_rag",
            max_steps=5,
            total_timeout_s=120,
            per_step_timeout_s=30,
        )
        agent_cb.start()
        while True:
            stop = agent_cb.check_before_step()
            if stop is not AgentStopReason.NONE: break
            action = planner.next_action(...)
            result = await dispatcher.run(action, timeout=agent_cb.step_timeout())
            agent_cb.record_step(action=action.name, result_hash=hash_it(result))
    """

    def __init__(
        self,
        *,
        agent_name: str,
        max_steps: int = 5,
        total_timeout_s: float = 120.0,
        per_step_timeout_s: float = 30.0,
        loop_detection_window: int = 3,
        max_tool_calls: dict[str, int] | None = None,
    ) -> None:
        self._name = agent_name
        self._max_steps = max_steps
        self._total_timeout = total_timeout_s
        self._step_timeout = per_step_timeout_s
        self._loop_window = loop_detection_window
        self._max_tool_calls = max_tool_calls or {}

        self._started_at: float = 0.0
        self._steps: list[AgentStep] = []
        self._tool_calls: dict[str, int] = {}
        self._user_aborted = False
        self._stop_reason: AgentStopReason = AgentStopReason.NONE

    def start(self) -> None:
        self._started_at = time.monotonic()
        self._steps.clear()
        self._tool_calls.clear()
        self._user_aborted = False
        self._stop_reason = AgentStopReason.NONE

    def abort_by_user(self) -> None:
        """Cooperative cancel from the UI / caller."""
        self._user_aborted = True

    def step_timeout(self) -> float:
        return self._step_timeout

    def remaining_time(self) -> float:
        return max(0.0, self._total_timeout - (time.monotonic() - self._started_at))

    def check_before_step(self) -> AgentStopReason:
        """Call BEFORE emitting the next step. Returns the reason to stop, or NONE."""
        if self._user_aborted:
            return self._record_stop(AgentStopReason.USER_ABORT)
        if len(self._steps) >= self._max_steps:
            return self._record_stop(AgentStopReason.MAX_STEPS)
        if time.monotonic() - self._started_at >= self._total_timeout:
            return self._record_stop(AgentStopReason.TIMEOUT)
        return AgentStopReason.NONE

    def record_step(self, *, action: str, result_hash: str = "") -> AgentStopReason:
        """Call AFTER a step completes. Returns NONE or LOOP_DETECTED/TOOL_BUDGET."""
        self._steps.append(AgentStep(action=action, result_hash=result_hash))
        self._tool_calls[action] = self._tool_calls.get(action, 0) + 1
        if _METRICS:
            _agent_steps.labels(agent=self._name).inc()

        # Tool budget
        cap = self._max_tool_calls.get(action)
        if cap is not None and self._tool_calls[action] > cap:
            return self._record_stop(AgentStopReason.TOOL_BUDGET)

        # Loop detection: same action run W times in a row
        if len(self._steps) >= self._loop_window:
            tail = self._steps[-self._loop_window:]
            if all(s.action == tail[0].action for s in tail):
                return self._record_stop(AgentStopReason.LOOP_DETECTED)
            # Same (action, result_hash) repeating means we're hallucinating
            # the same step without progress.
            sigs = {(s.action, s.result_hash) for s in tail}
            if result_hash and len(sigs) == 1:
                return self._record_stop(AgentStopReason.LOOP_DETECTED)

        return AgentStopReason.NONE

    def _record_stop(self, reason: AgentStopReason) -> AgentStopReason:
        self._stop_reason = reason
        if _METRICS:
            _agent_stops.labels(reason=reason.value).inc()
        log.info(
            "agent_stop agent=%s reason=%s steps=%d elapsed_s=%.1f",
            self._name, reason.value, len(self._steps),
            time.monotonic() - self._started_at,
        )
        return reason

    def snapshot(self) -> dict:
        return {
            "agent": self._name,
            "steps_taken": len(self._steps),
            "max_steps": self._max_steps,
            "elapsed_s": round(time.monotonic() - self._started_at, 2),
            "total_timeout_s": self._total_timeout,
            "stop_reason": self._stop_reason.value,
            "tool_calls": dict(self._tool_calls),
        }


# ============================================================================
# 4. ObservabilityCircuitBreaker
# ============================================================================

if _METRICS:
    _obs_skips = Counter(
        "documind_obs_breaker_skips_total",
        "Observability exports skipped because breaker was open",
        labelnames=["name"],
    )
    _obs_transitions = Counter(
        "documind_obs_breaker_transitions_total",
        "Observability breaker state transitions",
        labelnames=["name", "to_state"],
    )


class ObservabilityCircuitBreaker:
    """
    **Inverted polarity** breaker.

    Normal breakers fail the request when the dependency is down. This one
    PROTECTS the request from the dependency. When OPEN:

    * :meth:`allow_export` returns False → caller silently skips export.
    * NO exception is ever raised from here. Observability never
      breaks the app.

    Use case: OTel collector / Jaeger / Loki outage. Without this breaker,
    every span export hangs on its timeout, every hang adds latency, cascade.

    Failure model:

    * Register each export attempt with :meth:`record_result`.
    * After ``failure_threshold`` consecutive failures → OPEN.
    * In OPEN state, ``allow_export`` returns False for ``recovery_timeout``
      seconds.
    * Then HALF_OPEN: allow ONE export; success → CLOSED, failure → OPEN.

    Usage (FastAPI middleware, Kafka span exporter, etc.)::

        obs_cb = ObservabilityCircuitBreaker("otlp-exporter",
                                              failure_threshold=3,
                                              recovery_timeout=30)

        async def export(span):
            if not obs_cb.allow_export():
                return              # skip silently
            try:
                await otlp.export(span)
                obs_cb.record_result(success=True)
            except Exception:
                obs_cb.record_result(success=False)
                # NB: we deliberately do NOT re-raise.
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._state: State = State.CLOSED
        self._failures = 0
        self._opened_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> State:
        return self._state

    def allow_export(self) -> bool:
        """Non-blocking, no exceptions. True → go ahead; False → skip."""
        if self._state is State.CLOSED:
            return True
        if self._state is State.OPEN:
            if time.monotonic() - self._opened_at >= self._recovery_timeout:
                self._transition(State.HALF_OPEN)
                return True
            if _METRICS:
                _obs_skips.labels(name=self._name).inc()
            return False
        # HALF_OPEN — allow exactly one probe through
        return True

    def record_result(self, *, success: bool) -> None:
        """Call after each export attempt."""
        if success:
            if self._state is State.HALF_OPEN:
                self._transition(State.CLOSED)
            self._failures = 0
            return
        self._failures += 1
        if self._state is State.HALF_OPEN or self._failures >= self._failure_threshold:
            self._transition(State.OPEN)
            self._opened_at = time.monotonic()

    def _transition(self, new: State) -> None:
        if self._state is not new:
            log.info(
                "obs_breaker name=%s from=%s to=%s",
                self._name, self._state.value, new.value,
            )
            if _METRICS:
                _obs_transitions.labels(name=self._name, to_state=new.value).inc()
        self._state = new


# ============================================================================
# 5. CognitiveCircuitBreaker — intrinsic, inference-time reliability
# ============================================================================
# Inspired by the Cognitive Circuit Breaker pattern (arXiv 2604.13417, simplified):
# instead of checking generation AFTER it's complete (guardrails / LLM-as-judge),
# run the checks DURING generation and INTERRUPT the stream when a signal
# breaches its threshold.
#
# Why this matters:
# * Extrinsic validation adds latency + cost and catches issues late (after
#   the user has seen the tokens stream in).
# * Intrinsic validation fires while the model is still generating — we can
#   stop a bad generation before tokens are emitted to the user.
#
# Integration points in DocuMind:
# * Inference service wraps the Ollama streaming call with a CCB that owns a
#   set of CognitiveSignal instances.
# * For every N tokens emitted, the CCB asks each signal "is this OK?" and
#   aggregates. Any signal returning BLOCK aborts the generation.
# * On abort, the inference service returns a typed fallback
#   (InsufficientContextError / LowConfidenceError) routed to HITL.
#
# Caveats (from the paper's own limitations, noted honestly):
# * Signal calibration is non-trivial — too strict and valid answers get blocked.
# * Does NOT replace: data quality, retrieval grounding, policy governance,
#   offline evaluation. CCB is runtime; the others are lifecycle.


class CognitiveDecision(str, Enum):
    CONTINUE = "continue"
    WARN = "warn"
    BLOCK = "block"


@dataclass
class CognitiveReading:
    """One signal's opinion at a given token position."""

    decision: CognitiveDecision
    score: float
    reason: str
    signal_name: str


class CognitiveSignal:
    """
    Base class for intrinsic-reliability signals.

    Subclasses override :meth:`evaluate`. It receives the partial output so far
    and returns a :class:`CognitiveReading`.

    Signals should be CHEAP — they run on every token-sample event. Anything
    that calls an LLM itself should not be here (that defeats the purpose).
    """

    name: str = "signal"

    def evaluate(self, partial_output: str, token_count: int) -> CognitiveReading:
        raise NotImplementedError

    def reset(self) -> None:
        """Called at the start of each generation."""


class RepetitionSignal(CognitiveSignal):
    """
    Detect degenerate loops: the same 8-gram repeated > N times.

    A classic LLM failure mode, especially at low temperatures or when the
    context doesn't support the requested answer.
    """

    name = "repetition"

    def __init__(self, *, ngram: int = 8, max_repeats: int = 3) -> None:
        self._n = ngram
        self._max = max_repeats

    def evaluate(self, partial_output: str, token_count: int) -> CognitiveReading:
        if len(partial_output) < self._n * 4:
            return CognitiveReading(CognitiveDecision.CONTINUE, 1.0, "too-short", self.name)
        # cheap approximation: count the last n-gram in the tail
        tail = partial_output[-self._n * 8:]
        tail_clean = " ".join(tail.split())
        words = tail_clean.split()
        if len(words) < self._n * 2:
            return CognitiveReading(CognitiveDecision.CONTINUE, 1.0, "ok", self.name)
        window = " ".join(words[-self._n:])
        count = tail_clean.count(window)
        if count > self._max:
            return CognitiveReading(
                CognitiveDecision.BLOCK,
                0.0,
                f"repeated_{self._n}gram_x{count}",
                self.name,
            )
        if count > 1:
            return CognitiveReading(CognitiveDecision.WARN, 0.4, f"repetition_x{count}", self.name)
        return CognitiveReading(CognitiveDecision.CONTINUE, 1.0, "ok", self.name)


class CitationDeadlineSignal(CognitiveSignal):
    """
    RAG-specific: an answer that doesn't cite a source by token N is most
    likely a hallucination. Block to save the user from a confident lie.
    """

    name = "citation_deadline"

    def __init__(self, *, deadline_tokens: int = 400, min_citations: int = 1) -> None:
        self._deadline = deadline_tokens
        self._min = min_citations

    def evaluate(self, partial_output: str, token_count: int) -> CognitiveReading:
        # Crude token proxy: chars / 4
        approx_tokens = len(partial_output) // 4
        if approx_tokens < self._deadline:
            return CognitiveReading(CognitiveDecision.CONTINUE, 1.0, "pending", self.name)
        # Look for citation patterns we teach the prompt to emit
        import re  # local — signals should be import-light
        citations = len(re.findall(r"\[Source:[^\]]+\]", partial_output))
        if citations < self._min:
            return CognitiveReading(
                CognitiveDecision.BLOCK,
                0.1,
                f"no_citation_by_{self._deadline}t",
                self.name,
            )
        return CognitiveReading(CognitiveDecision.CONTINUE, 1.0, f"has_{citations}_citations", self.name)


class ForbiddenPatternSignal(CognitiveSignal):
    """
    Regex allow/deny list. Cheap, useful for catching policy violations
    (e.g. "never mention competitor X", "never output a credit card number").

    Not a replacement for a full PII/safety check — a complement.
    """

    name = "forbidden_pattern"

    def __init__(self, *, patterns: list[str]) -> None:
        import re
        self._patterns = [re.compile(p, re.IGNORECASE) for p in patterns]

    def evaluate(self, partial_output: str, token_count: int) -> CognitiveReading:
        for pat in self._patterns:
            m = pat.search(partial_output)
            if m:
                return CognitiveReading(
                    CognitiveDecision.BLOCK,
                    0.0,
                    f"forbidden:{m.group(0)[:40]}",
                    self.name,
                )
        return CognitiveReading(CognitiveDecision.CONTINUE, 1.0, "ok", self.name)


class LogprobConfidenceSignal(CognitiveSignal):
    """
    When the model provides logprobs, low avg logprob = low confidence.
    Abort if avg logprob falls below threshold for K consecutive token batches.

    If logprobs aren't available (Ollama exposes them inconsistently), this
    signal is a no-op — callers should fall back to :class:`RepetitionSignal`
    and :class:`CitationDeadlineSignal`.
    """

    name = "logprob_confidence"

    def __init__(self, *, min_avg_logprob: float = -3.0, window: int = 3) -> None:
        self._min = min_avg_logprob
        self._window = window
        self._history: deque[float] = deque(maxlen=window)

    def reset(self) -> None:
        self._history.clear()

    def record_logprob(self, avg_logprob: float) -> None:
        self._history.append(avg_logprob)

    def evaluate(self, partial_output: str, token_count: int) -> CognitiveReading:
        if len(self._history) < self._window:
            return CognitiveReading(CognitiveDecision.CONTINUE, 1.0, "warmup", self.name)
        avg = sum(self._history) / len(self._history)
        if avg < self._min:
            return CognitiveReading(
                CognitiveDecision.BLOCK, 0.0,
                f"logprob_avg={avg:.2f}<{self._min:.2f}",
                self.name,
            )
        # Normalize to 0..1 over a reasonable logprob range
        score = max(0.0, min(1.0, (avg + 5.0) / 5.0))
        return CognitiveReading(CognitiveDecision.CONTINUE, score, "ok", self.name)


class CognitiveInterrupt(AppError):
    """Raised to abort a streaming generation when the CCB says BLOCK."""

    error_code = "COGNITIVE_INTERRUPT"
    http_status = 503

    def __init__(self, reasons: list[str], *, partial: str = "") -> None:
        super().__init__(
            f"Generation interrupted by cognitive breaker: {', '.join(reasons)}",
            details={"reasons": reasons, "partial_length": len(partial)},
        )
        self.reasons = reasons
        self.partial = partial


if _METRICS:
    _ccb_interrupts = Counter(
        "documind_ccb_interrupts_total",
        "Cognitive breaker interrupts, by signal that fired",
        labelnames=["signal"],
    )
    _ccb_warns = Counter(
        "documind_ccb_warns_total",
        "Cognitive breaker warnings (not interrupting)",
        labelnames=["signal"],
    )


class CognitiveCircuitBreaker:
    """
    The CCB itself.

    Wraps a streaming generation call and evaluates its signals periodically.
    The inference service uses it like::

        ccb = CognitiveCircuitBreaker(signals=[
            RepetitionSignal(ngram=8, max_repeats=3),
            CitationDeadlineSignal(deadline_tokens=400),
            ForbiddenPatternSignal(patterns=[r"\\b(ssn|social security)\\b"]),
            LogprobConfidenceSignal(min_avg_logprob=-3.0),
        ], check_every_tokens=32)

        ccb.start()
        async for chunk in ollama.stream(...):
            ccb.on_tokens(chunk)   # may raise CognitiveInterrupt
            yield chunk

    The "every N tokens" cadence is important: checking per-token is
    expensive, checking once at the end defeats the purpose. 32-64 tokens is
    the sweet spot for most signals.

    Compatibility with offline evaluation: the same CCB can be run against
    a recorded stream to compute "would this have been interrupted?" metrics.
    """

    def __init__(
        self,
        *,
        signals: list[CognitiveSignal],
        check_every_tokens: int = 32,
        max_warnings_before_block: int = 3,
    ) -> None:
        self._signals = signals
        self._cadence = max(1, check_every_tokens)
        self._max_warnings = max_warnings_before_block
        self._partial = ""
        self._tokens_seen = 0
        self._tokens_since_check = 0
        self._warnings = 0
        self._last_decision: CognitiveDecision = CognitiveDecision.CONTINUE
        self._readings: list[CognitiveReading] = []

    def start(self) -> None:
        self._partial = ""
        self._tokens_seen = 0
        self._tokens_since_check = 0
        self._warnings = 0
        self._last_decision = CognitiveDecision.CONTINUE
        self._readings.clear()
        for s in self._signals:
            s.reset()

    @property
    def readings(self) -> list[CognitiveReading]:
        return list(self._readings)

    def on_tokens(self, new_text: str) -> CognitiveDecision:
        """
        Called as tokens stream in. Raises :class:`CognitiveInterrupt` to
        abort the generation when any signal returns BLOCK, or after
        ``max_warnings_before_block`` accumulated warnings.

        Returns the current decision so the caller can decide whether to
        surface the partial output (``WARN``) or swap it for a fallback
        (``BLOCK``).
        """
        self._partial += new_text
        # Rough token proxy again; wire real tokenizer if you want precision
        new_tokens = max(1, len(new_text) // 4)
        self._tokens_seen += new_tokens
        self._tokens_since_check += new_tokens

        if self._tokens_since_check < self._cadence:
            return self._last_decision
        self._tokens_since_check = 0

        block_reasons: list[str] = []
        for signal in self._signals:
            reading = signal.evaluate(self._partial, self._tokens_seen)
            self._readings.append(reading)

            if reading.decision is CognitiveDecision.BLOCK:
                if _METRICS:
                    _ccb_interrupts.labels(signal=signal.name).inc()
                block_reasons.append(f"{signal.name}:{reading.reason}")
            elif reading.decision is CognitiveDecision.WARN:
                if _METRICS:
                    _ccb_warns.labels(signal=signal.name).inc()
                self._warnings += 1

        if block_reasons:
            self._last_decision = CognitiveDecision.BLOCK
            raise CognitiveInterrupt(block_reasons, partial=self._partial)

        if self._warnings >= self._max_warnings:
            self._last_decision = CognitiveDecision.BLOCK
            raise CognitiveInterrupt(
                [f"warnings_exceeded:{self._warnings}"], partial=self._partial
            )

        self._last_decision = (
            CognitiveDecision.WARN if self._warnings > 0 else CognitiveDecision.CONTINUE
        )
        return self._last_decision

    def record_logprob(self, avg_logprob: float) -> None:
        """Forward a logprob sample to any signal that consumes one."""
        for s in self._signals:
            if isinstance(s, LogprobConfidenceSignal):
                s.record_logprob(avg_logprob)

    def snapshot(self) -> dict:
        """Report the CCB's final state (for logs + spans + debug responses)."""
        return {
            "tokens_seen": self._tokens_seen,
            "warnings": self._warnings,
            "final_decision": self._last_decision.value,
            "readings": [
                {"signal": r.signal_name, "decision": r.decision.value, "reason": r.reason, "score": r.score}
                for r in self._readings[-10:]  # last 10 readings only; spans get bloated otherwise
            ],
        }


__all__ = [
    "RetrievalCircuitBreaker",
    "RetrievalSample",
    "TokenCircuitBreaker",
    "TokenCheck",
    "TokenBreakerDecision",
    "AgentLoopCircuitBreaker",
    "AgentStep",
    "AgentStopReason",
    "ObservabilityCircuitBreaker",
    # Cognitive (intrinsic, inference-time)
    "CognitiveCircuitBreaker",
    "CognitiveDecision",
    "CognitiveReading",
    "CognitiveSignal",
    "CognitiveInterrupt",
    "RepetitionSignal",
    "CitationDeadlineSignal",
    "ForbiddenPatternSignal",
    "LogprobConfidenceSignal",
]
