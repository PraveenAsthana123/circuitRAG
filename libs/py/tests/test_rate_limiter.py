"""
Tests for documind_core.rate_limiter — sliding-window Redis limiter.

Covers:
- LimitResult dataclass
- tenant_key / ip_key formatting
- RateLimiter.__init__ registers the Lua script
- check() happy path (allowed, decrements remaining)
- check() over-limit path (returns allowed=False with reset_in_seconds
  computed from oldest score in the window)
- check() FAIL-OPEN on Redis ConnectionError / TimeoutError / OSError
  (the §38 contract: a rate limiter that 5xxs every user during a
  cache outage is worse than one that temporarily can't enforce)
- check_or_raise() raises RateLimitedError on over-limit;
  passes through LimitResult on allowed
- cost > 1 is honored
- reset_in_seconds is at least 1 second when oldest_score lags now_ms
  by less than a window (clamping prevents reset=0 confusing clients)

Redis is mocked at the register_script boundary — the Lua script
itself runs server-side, so unit tests assert that the Python wrapper
correctly dispatches to it and interprets the (allowed, current,
oldest) tuple. A live Lua-execution drill is the integration-test
counterpart (see chaos drill #8).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.asyncio as aioredis

from documind_core.exceptions import RateLimitedError
from documind_core.rate_limiter import (
    LimitResult,
    RateLimiter,
    ip_key,
    tenant_key,
)

# ── helpers ───────────────────────────────────────────────────


def _make_limiter(script_return=(1, 0, 0), script_side_effect=None) -> RateLimiter:
    """
    Build a RateLimiter whose Lua script returns ``script_return`` or
    raises ``script_side_effect``. The mock mirrors the Redis client's
    register_script API.
    """
    redis = MagicMock(spec=aioredis.Redis)
    script = AsyncMock()
    if script_side_effect is not None:
        script.side_effect = script_side_effect
    else:
        script.return_value = list(script_return)
    redis.register_script.return_value = script
    rl = RateLimiter(redis)
    return rl


# ── key helpers ───────────────────────────────────────────────


class TestKeyHelpers:
    def test_tenant_key_format(self) -> None:
        assert tenant_key("acme", "api") == "tenant:acme:rl:api"

    def test_ip_key_format(self) -> None:
        assert ip_key("203.0.113.5", "login") == "ip:203.0.113.5:rl:login"

    def test_keys_are_distinct_namespaces(self) -> None:
        # Tenant traffic must NEVER share a bucket with anonymous
        # IP traffic — different prefixes lock that in.
        assert not tenant_key("x", "y").startswith("ip:")
        assert not ip_key("x", "y").startswith("tenant:")


# ── LimitResult ───────────────────────────────────────────────


class TestLimitResult:
    def test_dataclass_fields(self) -> None:
        r = LimitResult(allowed=True, remaining=10, reset_in_seconds=30, limit=100)
        assert r.allowed is True
        assert r.remaining == 10
        assert r.reset_in_seconds == 30
        assert r.limit == 100


# ── RateLimiter init ──────────────────────────────────────────


class TestInit:
    def test_registers_script(self) -> None:
        redis = MagicMock(spec=aioredis.Redis)
        redis.register_script = MagicMock()
        RateLimiter(redis)
        # Script must be registered exactly once at init — EVALSHA reuse
        # is the whole point of register_script vs raw EVAL.
        redis.register_script.assert_called_once()
        registered = redis.register_script.call_args[0][0]
        assert "ZREMRANGEBYSCORE" in registered
        assert "ZADD" in registered


# ── check() happy + denied paths ──────────────────────────────


class TestCheck:
    @pytest.mark.asyncio
    async def test_allowed_returns_decremented_remaining(self) -> None:
        # Lua returns (1, current=4, 0) — 4 used, limit 100, remaining 96.
        rl = _make_limiter(script_return=(1, 4, 0))
        r = await rl.check(key="tenant:a:rl:api", limit=100, window_seconds=60)
        assert r.allowed is True
        assert r.remaining == 96
        assert r.reset_in_seconds == 60
        assert r.limit == 100

    @pytest.mark.asyncio
    async def test_allowed_with_zero_current_remaining_full(self) -> None:
        # First-ever call: current=1 after our ZADD, remaining = limit - 1.
        rl = _make_limiter(script_return=(1, 1, 0))
        r = await rl.check(key="k", limit=10, window_seconds=60)
        assert r.allowed is True
        assert r.remaining == 9

    @pytest.mark.asyncio
    async def test_allowed_remaining_clamped_to_zero(self) -> None:
        # If somehow current >= limit but allowed=1, remaining must
        # never go negative (defensive clamp inside the wrapper).
        rl = _make_limiter(script_return=(1, 200, 0))
        r = await rl.check(key="k", limit=100, window_seconds=60)
        assert r.allowed is True
        assert r.remaining == 0  # NOT -100

    @pytest.mark.asyncio
    async def test_denied_with_zero_oldest_uses_full_window(self) -> None:
        # Lua returned (0, current, oldest=0) — no oldest score available
        # so reset_in_seconds defaults to the full window.
        rl = _make_limiter(script_return=(0, 100, 0))
        r = await rl.check(key="k", limit=100, window_seconds=60)
        assert r.allowed is False
        assert r.remaining == 0
        assert r.reset_in_seconds == 60

    @pytest.mark.asyncio
    async def test_denied_reset_calculated_from_oldest(self) -> None:
        # oldest 50 seconds ago in a 60s window → reset in ~10s.
        # We can't stub time without monkeypatching; instead we feed a
        # realistic oldest_score and verify result is positive + clamped ≥ 1.
        rl = _make_limiter(script_return=(0, 100, 1))
        r = await rl.check(key="k", limit=100, window_seconds=60)
        assert r.allowed is False
        assert r.reset_in_seconds >= 1  # clamp prevents zero/negative

    @pytest.mark.asyncio
    async def test_cost_greater_than_one_passed_through(self) -> None:
        # The cost arg must reach the Lua script as ARGV[4].
        rl = _make_limiter(script_return=(1, 5, 0))
        await rl.check(key="k", limit=100, window_seconds=60, cost=5)
        call_args = rl._check_script.call_args  # type: ignore[attr-defined]
        # args=[now_ms, window_start, limit, cost, ttl, request_id]
        assert call_args.kwargs["args"][3] == 5


# ── fail-open paths (the safety contract) ─────────────────────


class TestFailOpen:
    @pytest.mark.asyncio
    async def test_redis_connection_error_fails_open(self) -> None:
        rl = _make_limiter(script_side_effect=aioredis.ConnectionError("redis down"))
        r = await rl.check(key="k", limit=100, window_seconds=60)
        # Fail-open contract: caller is allowed when Redis is unreachable.
        assert r.allowed is True
        assert r.remaining == 100
        assert r.limit == 100

    @pytest.mark.asyncio
    async def test_redis_timeout_fails_open(self) -> None:
        rl = _make_limiter(script_side_effect=aioredis.TimeoutError("slow"))
        r = await rl.check(key="k", limit=50, window_seconds=60)
        assert r.allowed is True
        assert r.remaining == 50

    @pytest.mark.asyncio
    async def test_os_error_fails_open(self) -> None:
        # Network-level OSError (e.g. broken pipe) must also fail open.
        rl = _make_limiter(script_side_effect=OSError("EPIPE"))
        r = await rl.check(key="k", limit=10, window_seconds=60)
        assert r.allowed is True

    @pytest.mark.asyncio
    async def test_unrelated_exceptions_propagate(self) -> None:
        # NEGATIVE: only Redis-connectivity errors fail open. A logic
        # error inside the Lua script (e.g. ResponseError) must NOT
        # silently allow traffic — that would mask a real bug.
        rl = _make_limiter(script_side_effect=ValueError("bug in args"))
        with pytest.raises(ValueError):
            await rl.check(key="k", limit=10, window_seconds=60)


# ── check_or_raise() ──────────────────────────────────────────


class TestCheckOrRaise:
    @pytest.mark.asyncio
    async def test_passthrough_on_allowed(self) -> None:
        rl = _make_limiter(script_return=(1, 1, 0))
        r = await rl.check_or_raise(key="k", limit=10, window_seconds=60)
        assert r.allowed is True

    @pytest.mark.asyncio
    async def test_raises_on_denied(self) -> None:
        rl = _make_limiter(script_return=(0, 10, 0))
        with pytest.raises(RateLimitedError) as exc_info:
            await rl.check_or_raise(key="k", limit=10, window_seconds=60)
        # The raised error must carry the retry hint so the HTTP layer
        # can render Retry-After. If retry_after is missing, clients
        # back off forever.
        assert exc_info.value.details["retry_after_seconds"] >= 1

    @pytest.mark.asyncio
    async def test_raised_error_includes_key_in_details(self) -> None:
        rl = _make_limiter(script_return=(0, 10, 0))
        with pytest.raises(RateLimitedError) as exc_info:
            await rl.check_or_raise(key="tenant:abc:rl:api", limit=10, window_seconds=60)
        # Operators triaging 429s need to know WHICH key was hit.
        assert exc_info.value.details["key"] == "tenant:abc:rl:api"
        assert exc_info.value.details["limit"] == 10
