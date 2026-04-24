"""Unit tests for the 5 specialized circuit breakers."""
from __future__ import annotations

import pytest

from documind_core.breakers import (
    AgentLoopCircuitBreaker,
    AgentStopReason,
    CitationDeadlineSignal,
    CognitiveCircuitBreaker,
    CognitiveInterrupt,
    ForbiddenPatternSignal,
    ObservabilityCircuitBreaker,
    RepetitionSignal,
    RetrievalCircuitBreaker,
    TokenBreakerDecision,
    TokenCircuitBreaker,
)
from documind_core.circuit_breaker import State
from documind_core.exceptions import PolicyViolationError

# --------------------------------------------------------------------------
# 1. RetrievalCircuitBreaker — quality awareness
# --------------------------------------------------------------------------

def test_retrieval_breaker_opens_when_quality_degrades():
    cb = RetrievalCircuitBreaker(
        "retrieval", failure_threshold=99,  # disable failure-count path
        min_quality=0.5, quality_window=5,
    )
    # 5 samples, all below threshold
    for _ in range(5):
        cb.record_quality(top_score=0.1, n_results=3, latency_ms=100)
    assert cb.state is State.OPEN


def test_retrieval_breaker_stays_closed_when_quality_good():
    cb = RetrievalCircuitBreaker(
        "retrieval", failure_threshold=99, min_quality=0.3, quality_window=5,
    )
    for _ in range(5):
        cb.record_quality(top_score=0.8, n_results=5, latency_ms=100)
    assert cb.state is State.CLOSED


def test_retrieval_breaker_opens_on_mostly_empty_results():
    cb = RetrievalCircuitBreaker(
        "retrieval", failure_threshold=99, min_quality=0.0, quality_window=4,
    )
    # top_score fine, but half the results are empty -> open
    for _ in range(3):
        cb.record_quality(top_score=0.9, n_results=0, latency_ms=50)
    cb.record_quality(top_score=0.9, n_results=1, latency_ms=50)
    assert cb.state is State.OPEN


# --------------------------------------------------------------------------
# 2. TokenCircuitBreaker — budget pre-flight
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_token_breaker_allow_under_budget():
    tcb = TokenCircuitBreaker()
    r = await tcb.check(
        tenant_id="t1", estimated_tokens=1000,
        daily_budget=100_000, monthly_budget=1_000_000,
    )
    assert r.decision is TokenBreakerDecision.ALLOW


@pytest.mark.asyncio
async def test_token_breaker_rejects_over_daily():
    tcb = TokenCircuitBreaker()
    await tcb.record_usage(tenant_id="t1", prompt_tokens=50_000, completion_tokens=40_000)
    r = await tcb.check(
        tenant_id="t1", estimated_tokens=20_000,
        daily_budget=100_000, monthly_budget=10_000_000,
    )
    assert r.decision is TokenBreakerDecision.REJECT_DAILY


@pytest.mark.asyncio
async def test_token_breaker_warns_at_80pct():
    tcb = TokenCircuitBreaker(warn_percent=0.8)
    await tcb.record_usage(tenant_id="t1", prompt_tokens=40_000, completion_tokens=40_000)
    r = await tcb.check(
        tenant_id="t1", estimated_tokens=1_000,
        daily_budget=100_000, monthly_budget=10_000_000,
    )
    assert r.decision is TokenBreakerDecision.WARN


@pytest.mark.asyncio
async def test_token_breaker_rejects_per_request_blow_up():
    tcb = TokenCircuitBreaker(max_tokens_per_request=10_000)
    r = await tcb.check(
        tenant_id="t1", estimated_tokens=50_000,
        daily_budget=1_000_000, monthly_budget=1_000_000_000,
    )
    assert r.decision is TokenBreakerDecision.REJECT_REQUEST


@pytest.mark.asyncio
async def test_token_breaker_raises_on_reject():
    tcb = TokenCircuitBreaker(max_tokens_per_request=10_000)
    with pytest.raises(PolicyViolationError):
        await tcb.check_or_raise(
            tenant_id="t1", estimated_tokens=50_000,
            daily_budget=1_000_000, monthly_budget=10_000_000,
        )


# --------------------------------------------------------------------------
# 3. AgentLoopCircuitBreaker
# --------------------------------------------------------------------------

def test_agent_breaker_stops_on_max_steps():
    cb = AgentLoopCircuitBreaker(agent_name="t", max_steps=3)
    cb.start()
    assert cb.check_before_step() is AgentStopReason.NONE
    cb.record_step(action="retrieve")
    cb.record_step(action="retrieve")
    cb.record_step(action="retrieve")
    # Now 3 steps recorded; next check should stop.
    assert cb.check_before_step() is AgentStopReason.MAX_STEPS


def test_agent_breaker_detects_tool_loop():
    cb = AgentLoopCircuitBreaker(agent_name="t", max_steps=20, loop_detection_window=3)
    cb.start()
    cb.record_step(action="retrieve", result_hash="a")
    cb.record_step(action="retrieve", result_hash="b")
    r = cb.record_step(action="retrieve", result_hash="c")
    assert r is AgentStopReason.LOOP_DETECTED


def test_agent_breaker_enforces_tool_budget():
    cb = AgentLoopCircuitBreaker(
        agent_name="t", max_steps=20, max_tool_calls={"search": 2},
    )
    cb.start()
    cb.record_step(action="search")
    cb.record_step(action="search")
    r = cb.record_step(action="search")
    assert r is AgentStopReason.TOOL_BUDGET


def test_agent_breaker_user_abort():
    cb = AgentLoopCircuitBreaker(agent_name="t")
    cb.start()
    cb.abort_by_user()
    assert cb.check_before_step() is AgentStopReason.USER_ABORT


# --------------------------------------------------------------------------
# 4. ObservabilityCircuitBreaker — inverted polarity
# --------------------------------------------------------------------------

def test_obs_breaker_allows_when_closed():
    cb = ObservabilityCircuitBreaker("test", failure_threshold=3, recovery_timeout=1)
    assert cb.allow_export() is True
    cb.record_result(success=True)
    assert cb.state is State.CLOSED


def test_obs_breaker_opens_and_skips():
    cb = ObservabilityCircuitBreaker("test", failure_threshold=2, recovery_timeout=1)
    cb.record_result(success=False)
    cb.record_result(success=False)
    assert cb.state is State.OPEN
    # In OPEN state, allow_export returns False (skip).
    assert cb.allow_export() is False


def test_obs_breaker_never_raises():
    cb = ObservabilityCircuitBreaker("test", failure_threshold=1)
    # Rapid-fire failures should not raise
    for _ in range(100):
        cb.record_result(success=False)
    # Still safe to check:
    _ = cb.allow_export()  # no exception


# --------------------------------------------------------------------------
# 5. CognitiveCircuitBreaker
# --------------------------------------------------------------------------

def test_ccb_blocks_on_repetition():
    ccb = CognitiveCircuitBreaker(
        signals=[RepetitionSignal(ngram=3, max_repeats=2)],
        check_every_tokens=1,
    )
    ccb.start()
    with pytest.raises(CognitiveInterrupt):
        # The bad tail repeats "the foo bar" 4+ times — triggers block.
        text = "the foo bar " * 6
        ccb.on_tokens(text)


def test_ccb_blocks_on_missing_citation_after_deadline():
    ccb = CognitiveCircuitBreaker(
        signals=[CitationDeadlineSignal(deadline_tokens=10, min_citations=1)],
        check_every_tokens=1,
    )
    ccb.start()
    # Way past the 10-token deadline with no [Source:...]
    text = "some long text " * 30
    with pytest.raises(CognitiveInterrupt):
        ccb.on_tokens(text)


def test_ccb_continues_when_citation_present():
    ccb = CognitiveCircuitBreaker(
        signals=[CitationDeadlineSignal(deadline_tokens=5, min_citations=1)],
        check_every_tokens=1,
    )
    ccb.start()
    ccb.on_tokens("Based on [Source: doc.pdf, Page 1] the answer is yes.")
    # No exception means the signal saw the citation and let it through.


def test_ccb_blocks_on_forbidden_pattern():
    ccb = CognitiveCircuitBreaker(
        signals=[ForbiddenPatternSignal(patterns=[r"api[-_]?key"])],
        check_every_tokens=1,
    )
    ccb.start()
    with pytest.raises(CognitiveInterrupt):
        ccb.on_tokens("Your api_key is 12345")


def test_ccb_snapshot_includes_readings():
    ccb = CognitiveCircuitBreaker(
        signals=[RepetitionSignal(ngram=3, max_repeats=99)],  # won't trigger
        check_every_tokens=1,
    )
    ccb.start()
    ccb.on_tokens("hello world this is a test")
    snap = ccb.snapshot()
    assert "tokens_seen" in snap
    assert snap["final_decision"] in ("continue", "warn", "block")
