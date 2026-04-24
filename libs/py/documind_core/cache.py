"""
Cache helpers (Design Areas 40 — Cache Architecture, 41 — Cache Consistency,
42 — Tenant-Aware Cache).

Thin Redis wrapper that enforces:

* **Tenant-namespaced keys** — every cache key is prefixed with
  ``tenant:{tenant_id}:`` so cross-tenant hits are structurally impossible.
* **Stampede prevention** — on cache miss, only one coroutine fetches; the
  rest wait briefly for the cached result.
* **JSON serialization** — values are JSON by default; callers can opt into
  raw bytes for binary payloads (embedding vectors, PDFs).
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import redis.asyncio as aioredis

log = logging.getLogger(__name__)

T = TypeVar("T")


class Cache:
    """Tenant-aware cache-aside helper."""

    def __init__(self, redis: aioredis.Redis, *, default_ttl: int = 300) -> None:
        self._redis = redis
        self._default_ttl = default_ttl

    @staticmethod
    def tenant_key(tenant_id: str, *parts: str) -> str:
        """Namespace a key by tenant. Use this EVERYWHERE."""
        assert tenant_id, "tenant_id is required for cache keys"  # noqa: S101
        return "tenant:" + tenant_id + ":" + ":".join(parts)

    async def get_json(self, key: str) -> Any | None:
        # Fail-open on Redis connection errors: treat as a cache miss so
        # the caller falls through to the source. A dead cache must not
        # 5xx the user. Caught during chaos drill #5 (kill Redis).
        try:
            raw = await self._redis.get(key)
        except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
            log.warning("cache_get_fail_open key=%s err=%s", key, exc)
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("cache_get_bad_json key=%s", key)
            return None

    async def set_json(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        payload = json.dumps(value, separators=(",", ":"), default=str)
        try:
            await self._redis.setex(key, ttl or self._default_ttl, payload)
        except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
            # Fail-open on write too — silently drop the cache write.
            log.warning("cache_set_fail_open key=%s err=%s", key, exc)

    async def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        return await self._redis.delete(*keys)

    async def invalidate_prefix(self, prefix: str) -> int:
        """
        Delete all keys starting with ``prefix``. Uses SCAN, not KEYS —
        KEYS blocks the server at scale. Still O(N); only use for explicit
        cache-bust operations (tenant suspension, data-doc reindex).
        """
        count = 0
        async for key in self._redis.scan_iter(match=f"{prefix}*", count=500):
            await self._redis.delete(key)
            count += 1
        log.info("cache_invalidate_prefix prefix=%s removed=%d", prefix, count)
        return count

    async def get_or_load(
        self,
        key: str,
        *,
        loader: Callable[[], Awaitable[T]],
        ttl: int | None = None,
        lock_timeout: float = 5.0,
    ) -> T:
        """
        Cache-aside with simple stampede protection.

        1. Return cached value if present.
        2. Otherwise, acquire a Redis-backed lock (``lock:<key>``).
        3. Double-check the cache (someone else may have filled it).
        4. Call ``loader()``, cache the result, release the lock.
        5. If the lock is contended, wait briefly and retry the cache read.

        Prevents N parallel callers from all hammering the origin.
        """
        cached = await self.get_json(key)
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        lock_key = f"lock:{key}"
        got_lock = await self._redis.set(lock_key, "1", nx=True, ex=int(lock_timeout))
        if not got_lock:
            # Someone else is loading — wait briefly, then read the cache.
            await asyncio.sleep(0.1)
            cached = await self.get_json(key)
            if cached is not None:
                return cached  # type: ignore[no-any-return]
            # Fall through and load anyway rather than block indefinitely.

        try:
            # Double-check (brief race possible)
            cached = await self.get_json(key)
            if cached is not None:
                return cached  # type: ignore[no-any-return]

            value = await loader()
            await self.set_json(key, value, ttl=ttl)
            return value
        finally:
            if got_lock:
                await self._redis.delete(lock_key)
