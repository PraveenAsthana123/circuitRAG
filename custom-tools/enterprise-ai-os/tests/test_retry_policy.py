# Negative drills for Iter 24 (2026-05-17): RetryPolicy primitive.
# Integration-client behavior is exercised via real provider SDKs
# (out of scope for unit tests).

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from integrations.retry_policy import RetryPolicy


def test_succeeds_first_attempt_no_retry():
    calls = {"n": 0}
    def op():
        calls["n"] += 1
        return "ok"
    p = RetryPolicy(max_retries=3, base_delay_ms=1)
    assert p.execute(op) == "ok"
    assert calls["n"] == 1


def test_BACKDOOR_CHECK_retries_on_connection_error():
    """Pre-fix the OpenAI client had no retry path — a single
    transient ConnectionError surfaced to the caller."""
    calls = {"n": 0}
    def op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "ok"
    p = RetryPolicy(max_retries=5, base_delay_ms=1)
    assert p.execute(op) == "ok"
    assert calls["n"] == 3


def test_gives_up_after_max_retries_and_reraises():
    calls = {"n": 0}
    def op():
        calls["n"] += 1
        raise ConnectionError("persistent")
    p = RetryPolicy(max_retries=2, base_delay_ms=1)
    with pytest.raises(ConnectionError, match="persistent"):
        p.execute(op)
    # max_retries=2 → 1 initial attempt + 2 retries = 3 calls
    assert calls["n"] == 3


def test_non_retryable_exception_propagates_immediately():
    """ValueError is not in default retry_on; must NOT be retried."""
    calls = {"n": 0}
    def op():
        calls["n"] += 1
        raise ValueError("bug, not transient")
    p = RetryPolicy(max_retries=5, base_delay_ms=1)
    with pytest.raises(ValueError):
        p.execute(op)
    assert calls["n"] == 1


def test_custom_retry_on_set():
    calls = {"n": 0}
    class Custom(Exception): pass
    def op():
        calls["n"] += 1
        if calls["n"] < 2:
            raise Custom("retry me")
        return "ok"
    p = RetryPolicy(max_retries=3, base_delay_ms=1, retry_on=(Custom,))
    assert p.execute(op) == "ok"
    assert calls["n"] == 2


def test_backoff_seconds_is_jittered():
    p = RetryPolicy(base_delay_ms=100)
    samples = [p._backoff_seconds(2) for _ in range(20)]
    # All within [base*4*0.5, base*4*1.5) ms = [0.2, 0.6) seconds
    assert all(0.2 <= s < 0.6 for s in samples)
    # Spread must not be a single value (jittered, not deterministic).
    assert len(set(samples)) > 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
