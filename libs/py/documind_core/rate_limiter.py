"""
Rate limiting (Design Areas 42 — Tenant-Aware Cache, 45 — Backpressure).

Redis-backed sliding-window rate limiter. Per-tenant + per-endpoint.

Why sliding window instead of fixed window or token bucket
----------------------------------------------------------
* **Fixed window** (Redis INCR with TTL) is cheap but lets a caller burst
  2x the limit at window boundaries — bad for downstream protection.
* **Token bucket** (Redis Lua script) gives smooth rate + burst allowance
  but adds Lua complexity.
* **Sliding window** (sorted set of timestamps) is O(log N) per call,
  accurate, and doesn't allow boundary-bursting. Good default.

For VERY high-traffic endpoints (>10k req/s), swap to a token-bucket
implementation or Envoy/Istio ratelimit service. The abstraction here
(the :class:`RateLimiter` interface) stays the same.

Multi-tenancy
-------------
Every key is namespaced ``tenant:{tenant_id}:rl:{endpoint}`` so no
cross-tenant interference. Global limits (anonymous, per-IP) use
``ip:{ip}:rl:...``.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

import redis.asyncio as aioredis

from .exceptions import RateLimitedError

log = logging.getLogger(__name__)


@dataclass
class LimitResult:
    """Result of a :meth:`RateLimiter.check` call."""

    allowed: bool
    remaining: int
    reset_in_seconds: int
    limit: int


class RateLimiter:
    """
    Sliding-window rate limiter.

    Usage::

        rl = RateLimiter(redis_client)
        result = await rl.check(
            key="tenant:abc:rl:api",
            limit=100,
            window_seconds=60,
        )
        if not result.allowed:
            raise RateLimitedError(
                f"Rate limit {result.limit}/min exceeded",
                retry_after_seconds=result.reset_in_seconds,
            )
    """

    # -------------------------------------------------------------------
    # Atomic sliding-window Lua script.
    #
    # Previous impl had a check-then-act race (caught in chaos drill #8):
    # concurrent requests all read ZCARD before any ZADD, so 150 parallel
    # requests under a limit of 100 all succeeded. This Lua script runs
    # ENTIRELY on the Redis server in one round-trip, so the read + decide
    # + reserve are a single serialized operation.
    #
    # KEYS[1] = rate-limit key
    # ARGV[1] = now_ms            (current time in ms)
    # ARGV[2] = window_start_ms   (cutoff for expiration)
    # ARGV[3] = limit             (max allowed in window)
    # ARGV[4] = cost              (units this request consumes)
    # ARGV[5] = ttl_seconds       (key TTL for housekeeping)
    #
    # Returns: {allowed (0|1), current, oldest_score_ms_or_zero}
    # -------------------------------------------------------------------
    # ARGV[6] = request_id  (unique per call — prevents concurrent requests
    #                       in the same millisecond from collapsing onto the
    #                       same ZADD member. Caught in chaos drill #8 re-run.)
    _CHECK_LUA = """
    redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[2])
    local current = tonumber(redis.call('ZCARD', KEYS[1]))
    local limit = tonumber(ARGV[3])
    local cost = tonumber(ARGV[4])
    if current + cost > limit then
      local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
      local oldest_score = 0
      if oldest[2] then oldest_score = tonumber(oldest[2]) end
      return {0, current, oldest_score}
    end
    for i = 1, cost do
      redis.call('ZADD', KEYS[1], ARGV[1], ARGV[6] .. ':' .. tostring(i))
    end
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[5]))
    return {1, current + cost, 0}
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        # Register the script once — EVALSHA is faster than EVAL on reuse.
        self._check_script = redis.register_script(self._CHECK_LUA)

    async def check(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
        cost: int = 1,
    ) -> LimitResult:
        """
        Reserve ``cost`` units from the bucket. Non-blocking — returns
        a :class:`LimitResult` you act on.

        Implementation: atomic Lua script — ZREM + ZCARD + conditional
        ZADD in one Redis round-trip. Fixed sliding-window TOCTOU race
        caught in chaos drill #8 where 150 concurrent requests all
        bypassed a limit of 100.
        """
        now_ms = int(time.time() * 1000)
        window_start = now_ms - window_seconds * 1000
        # Unique member suffix — without this, concurrent requests within the
        # same millisecond collapse onto the same ZADD member (Redis ZADD is
        # upsert-by-member). Caught in chaos drill #8 re-run: zcard=73 after
        # 150 concurrent requests hitting the same millisecond bucket.
        request_id = uuid.uuid4().hex

        try:
            allowed, current, oldest_score = await self._check_script(
                keys=[key],
                args=[now_ms, window_start, limit, cost, window_seconds + 1, request_id],
            )
        except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
            # Fail-open: if Redis is unreachable, allow the request. A rate
            # limiter that 5xxs every user during a cache outage is worse
            # than a rate limiter that temporarily can't enforce its limit.
            log.warning("rate_limit_fail_open key=%s err=%s", key, exc)
            return LimitResult(allowed=True, remaining=limit, reset_in_seconds=0, limit=limit)

        if not allowed:
            reset_in = window_seconds
            if oldest_score:
                reset_in = max(1, int((int(oldest_score) + window_seconds * 1000 - now_ms) / 1000))
            log.info("rate_limited key=%s current=%d limit=%d", key, int(current), limit)
            return LimitResult(allowed=False, remaining=0, reset_in_seconds=reset_in, limit=limit)

        return LimitResult(
            allowed=True,
            remaining=max(0, limit - int(current)),
            reset_in_seconds=window_seconds,
            limit=limit,
        )

    async def check_or_raise(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
        cost: int = 1,
    ) -> LimitResult:
        """Convenience: raise :class:`RateLimitedError` if over limit."""
        result = await self.check(
            key=key, limit=limit, window_seconds=window_seconds, cost=cost
        )
        if not result.allowed:
            raise RateLimitedError(
                f"Rate limit exceeded ({result.limit} per {window_seconds}s)",
                retry_after_seconds=result.reset_in_seconds,
                details={"key": key, "limit": result.limit, "window_seconds": window_seconds},
            )
        return result


def tenant_key(tenant_id: str, endpoint: str) -> str:
    """Build a tenant-namespaced rate-limit key."""
    return f"tenant:{tenant_id}:rl:{endpoint}"


def ip_key(ip: str, endpoint: str) -> str:
    """Build an IP-namespaced rate-limit key for anonymous traffic."""
    return f"ip:{ip}:rl:{endpoint}"
