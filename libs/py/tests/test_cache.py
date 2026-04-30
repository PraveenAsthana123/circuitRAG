"""
Tests for documind_core.cache — tenant-aware Redis cache helper.

Covers:
- Cache.tenant_key namespacing + assertion on empty tenant_id
- get_json: hit, miss, fail-open on Redis errors, bad-JSON safety
- set_json: success, fail-open on Redis errors
- delete: zero keys is no-op; multiple keys forwarded
- invalidate_prefix: scan_iter walk + per-key delete; count returned
- get_or_load: cache hit; miss + lock acquired path; miss + lock
  contended path (retries cache); miss + lock contended + still
  miss path (falls through to load anyway — never block forever)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.asyncio as aioredis

from documind_core.cache import Cache

# ── helpers ───────────────────────────────────────────────────


def _make_redis() -> MagicMock:
    redis = MagicMock(spec=aioredis.Redis)
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock(return_value=0)
    redis.set = AsyncMock(return_value=True)
    return redis


# ── tenant_key ────────────────────────────────────────────────


class TestTenantKey:
    def test_basic(self) -> None:
        assert Cache.tenant_key("acme", "doc", "123") == "tenant:acme:doc:123"

    def test_single_part(self) -> None:
        assert Cache.tenant_key("t", "x") == "tenant:t:x"

    def test_empty_tenant_id_rejected(self) -> None:
        # Cross-tenant cache poisoning vector — must be impossible to
        # build a key without a tenant prefix.
        with pytest.raises(AssertionError):
            Cache.tenant_key("", "x")


# ── get_json ──────────────────────────────────────────────────


class TestGetJson:
    @pytest.mark.asyncio
    async def test_hit_returns_parsed(self) -> None:
        redis = _make_redis()
        redis.get.return_value = b'{"x": 1}'
        c = Cache(redis)
        assert await c.get_json("k") == {"x": 1}

    @pytest.mark.asyncio
    async def test_miss_returns_none(self) -> None:
        redis = _make_redis()
        redis.get.return_value = None
        c = Cache(redis)
        assert await c.get_json("k") is None

    @pytest.mark.asyncio
    async def test_connection_error_fails_open(self) -> None:
        # §38 contract: dead cache must NOT 5xx the user; treat as miss.
        redis = _make_redis()
        redis.get.side_effect = aioredis.ConnectionError("down")
        c = Cache(redis)
        assert await c.get_json("k") is None

    @pytest.mark.asyncio
    async def test_timeout_fails_open(self) -> None:
        redis = _make_redis()
        redis.get.side_effect = aioredis.TimeoutError("slow")
        c = Cache(redis)
        assert await c.get_json("k") is None

    @pytest.mark.asyncio
    async def test_os_error_fails_open(self) -> None:
        redis = _make_redis()
        redis.get.side_effect = OSError("EPIPE")
        c = Cache(redis)
        assert await c.get_json("k") is None

    @pytest.mark.asyncio
    async def test_bad_json_returns_none(self) -> None:
        # Corrupted cache rows must NOT crash callers — treat as miss.
        redis = _make_redis()
        redis.get.return_value = b"not-json"
        c = Cache(redis)
        assert await c.get_json("k") is None


# ── set_json ──────────────────────────────────────────────────


class TestSetJson:
    @pytest.mark.asyncio
    async def test_success_uses_default_ttl(self) -> None:
        redis = _make_redis()
        c = Cache(redis, default_ttl=300)
        await c.set_json("k", {"x": 1})
        assert redis.setex.call_args[0][0] == "k"
        assert redis.setex.call_args[0][1] == 300

    @pytest.mark.asyncio
    async def test_explicit_ttl_overrides(self) -> None:
        redis = _make_redis()
        c = Cache(redis, default_ttl=300)
        await c.set_json("k", "v", ttl=60)
        assert redis.setex.call_args[0][1] == 60

    @pytest.mark.asyncio
    async def test_connection_error_fails_open(self) -> None:
        # Write fail-open: silently drop. Don't crash the caller because
        # the cache layer is unreachable.
        redis = _make_redis()
        redis.setex.side_effect = aioredis.ConnectionError("down")
        c = Cache(redis)
        await c.set_json("k", "v")  # no exception

    @pytest.mark.asyncio
    async def test_serializes_with_default_str(self) -> None:
        # default=str makes datetimes / UUIDs survive JSON encoding.
        from datetime import datetime

        redis = _make_redis()
        c = Cache(redis)
        await c.set_json("k", {"ts": datetime(2026, 1, 1)})
        assert "2026" in redis.setex.call_args[0][2]


# ── delete ────────────────────────────────────────────────────


class TestDelete:
    @pytest.mark.asyncio
    async def test_zero_keys_returns_zero_no_call(self) -> None:
        redis = _make_redis()
        c = Cache(redis)
        assert await c.delete() == 0
        redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_keys_forwarded(self) -> None:
        redis = _make_redis()
        redis.delete.return_value = 2
        c = Cache(redis)
        result = await c.delete("a", "b")
        assert result == 2
        redis.delete.assert_awaited_once_with("a", "b")


# ── invalidate_prefix ─────────────────────────────────────────


class TestInvalidatePrefix:
    @pytest.mark.asyncio
    async def test_no_matches_returns_zero(self) -> None:
        redis = _make_redis()

        async def empty_iter(*_a, **_kw):
            for _ in []:
                yield  # never

        redis.scan_iter = empty_iter
        c = Cache(redis)
        assert await c.invalidate_prefix("tenant:x:") == 0

    @pytest.mark.asyncio
    async def test_multiple_matches_deleted(self) -> None:
        redis = _make_redis()

        async def fake_iter(*_a, **_kw):
            for k in (b"tenant:x:a", b"tenant:x:b", b"tenant:x:c"):
                yield k

        redis.scan_iter = fake_iter
        c = Cache(redis)
        assert await c.invalidate_prefix("tenant:x:") == 3
        assert redis.delete.await_count == 3


# ── get_or_load ───────────────────────────────────────────────


class TestGetOrLoad:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_loader(self) -> None:
        redis = _make_redis()
        redis.get.return_value = b'"cached"'
        c = Cache(redis)
        loader = AsyncMock()  # would explode if called
        result = await c.get_or_load("k", loader=loader)
        assert result == "cached"
        loader.assert_not_called()

    @pytest.mark.asyncio
    async def test_miss_with_lock_calls_loader(self) -> None:
        redis = _make_redis()
        # All gets miss; lock acquired (set returns True).
        redis.get.return_value = None
        redis.set.return_value = True
        c = Cache(redis)
        loader = AsyncMock(return_value={"loaded": True})
        result = await c.get_or_load("k", loader=loader)
        assert result == {"loaded": True}
        loader.assert_awaited_once()
        # Lock released
        assert any(call.args == ("lock:k",) for call in redis.delete.await_args_list)

    @pytest.mark.asyncio
    async def test_miss_lock_contended_retry_hit(self, monkeypatch) -> None:
        # First get: miss. Lock contended. After sleep, second get: HIT.
        redis = _make_redis()
        results = [None, b'"after-sleep"']
        redis.get.side_effect = lambda _k: results.pop(0)
        redis.set.return_value = False  # someone else holds the lock

        # Skip the asyncio.sleep delay for fast tests.
        async def no_sleep(_d):
            return None

        import documind_core.cache as cache_mod

        monkeypatch.setattr(cache_mod.asyncio, "sleep", no_sleep)
        c = Cache(redis)
        loader = AsyncMock()
        result = await c.get_or_load("k", loader=loader)
        assert result == "after-sleep"
        loader.assert_not_called()  # other coroutine filled the cache

    @pytest.mark.asyncio
    async def test_miss_lock_acquired_double_check_hits(self) -> None:
        # Race: between miss-1 and lock-acquire, another coroutine filled
        # the cache. The double-check inside the lock catches it and
        # returns the cached value WITHOUT calling the loader.
        redis = _make_redis()
        # get sequence: miss, then HIT inside the lock.
        results = [None, b'"raced-in"']
        redis.get.side_effect = lambda _k: results.pop(0)
        redis.set.return_value = True  # lock acquired
        c = Cache(redis)
        loader = AsyncMock()  # must NOT be called
        result = await c.get_or_load("k", loader=loader)
        assert result == "raced-in"
        loader.assert_not_called()

    @pytest.mark.asyncio
    async def test_miss_lock_contended_still_miss_falls_through(self, monkeypatch) -> None:
        # Lock contended AND retry still misses → load anyway, never block.
        redis = _make_redis()
        redis.get.return_value = None  # always miss
        redis.set.return_value = False  # lock contended

        async def no_sleep(_d):
            return None

        import documind_core.cache as cache_mod

        monkeypatch.setattr(cache_mod.asyncio, "sleep", no_sleep)
        c = Cache(redis)
        loader = AsyncMock(return_value="finally")
        result = await c.get_or_load("k", loader=loader)
        # Loader was called as the fall-through guard against
        # indefinite blocking.
        assert result == "finally"
        loader.assert_awaited_once()
