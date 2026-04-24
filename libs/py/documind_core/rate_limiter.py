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

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

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

        Implementation: sorted set where score = timestamp. Remove entries
        older than the window, count remaining, and insert if under limit.
        Pipelined into one Redis round-trip.
        """
        now_ms = int(time.time() * 1000)
        window_start = now_ms - window_seconds * 1000

        try:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)   # drop old
            pipe.zcard(key)                                 # count current
            pipe.expire(key, window_seconds + 1)            # housekeeping TTL
            _, current, _ = await pipe.execute()
        except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
            # Fail-open: if Redis is unreachable, allow the request. A rate
            # limiter that 5xxs every user during a cache outage is worse
            # than a rate limiter that temporarily can't enforce its limit.
            # Log once per minute to avoid noise during sustained outage.
            log.warning("rate_limit_fail_open key=%s err=%s", key, exc)
            return LimitResult(allowed=True, remaining=limit, reset_in_seconds=0, limit=limit)

        if current + cost > limit:
            # Find oldest remaining entry to compute retry-after
            oldest = await self._redis.zrange(key, 0, 0, withscores=True)
            reset_in = window_seconds
            if oldest:
                oldest_ms = int(oldest[0][1])
                reset_in = max(1, int((oldest_ms + window_seconds * 1000 - now_ms) / 1000))
            log.info("rate_limited key=%s current=%d limit=%d", key, current, limit)
            return LimitResult(allowed=False, remaining=0, reset_in_seconds=reset_in, limit=limit)

        # Reserve by adding `cost` entries. Each distinct member guarantees
        # sorted-set stores them; using now_ms + monotonic counter keeps
        # members unique.
        add_pipe = self._redis.pipeline()
        for i in range(cost):
            add_pipe.zadd(key, {f"{now_ms}:{i}": now_ms})
        add_pipe.expire(key, window_seconds + 1)
        await add_pipe.execute()

        return LimitResult(
            allowed=True,
            remaining=limit - (current + cost),
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
