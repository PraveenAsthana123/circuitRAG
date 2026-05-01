"""
Tests for documind_core.embedding_cache.

Covers:
- vector_to_bytes / bytes_to_vector roundtrip
- bytes_to_vector raises on non-aligned data (corrupt)
- Init requires non-empty model
- get / put roundtrip with stats updated
- Miss returns None + stats.misses incremented
- Fail-open on Redis error (no exception, no crash)
- Corrupt cached bytes returns None + logs (no crash)
- Empty tenant_id rejected (cross-tenant safety)
- Empty vector NOT cached (would mask real misses)
- Different model namespaces don't collide
- invalidate_tenant scans + deletes
- hit_rate calculation, including zero-total edge
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.asyncio as aioredis

from documind_core.embedding_cache import (
    EmbeddingCache,
    EmbeddingCacheStats,
    bytes_to_vector,
    vector_to_bytes,
)


def _make_redis() -> MagicMock:
    redis = MagicMock(spec=aioredis.Redis)
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock(return_value=0)
    return redis


class TestVectorBytes:
    def test_roundtrip(self) -> None:
        v = [0.1, -0.5, 1e-3, 100.0]
        out = bytes_to_vector(vector_to_bytes(v))
        # float32 precision — can't expect exact equality.
        assert len(out) == len(v)
        assert all(abs(a - b) < 1e-5 for a, b in zip(v, out, strict=True))

    def test_bytes_misaligned_raises(self) -> None:
        # NEGATIVE: corrupt cache bytes that aren't a multiple of 4
        # bytes can't be a float32 array. Catch at unpack time.
        with pytest.raises(ValueError, match="not divisible by 4"):
            bytes_to_vector(b"abc")

    def test_empty_roundtrip(self) -> None:
        # Edge: empty vector is technically valid but useless.
        # vector_to_bytes returns b''; bytes_to_vector returns [].
        assert bytes_to_vector(vector_to_bytes([])) == []


class TestStats:
    def test_hit_rate_normal(self) -> None:
        s = EmbeddingCacheStats(hits=8, misses=2)
        assert s.hit_rate == 0.8

    def test_hit_rate_zero_total_no_div_zero(self) -> None:
        # NEGATIVE: brand-new cache with zero requests must return
        # 0.0, not raise ZeroDivisionError.
        s = EmbeddingCacheStats()
        assert s.hit_rate == 0.0


class TestInit:
    def test_empty_model_rejected(self) -> None:
        # Without a model, the whole point of versioning is lost.
        with pytest.raises(ValueError, match="model is required"):
            EmbeddingCache(_make_redis(), model="")

    def test_model_property(self) -> None:
        cache = EmbeddingCache(_make_redis(), model="nomic-v1")
        assert cache.model == "nomic-v1"


class TestGetPut:
    @pytest.mark.asyncio
    async def test_miss_returns_none_increments_misses(self) -> None:
        redis = _make_redis()
        redis.get.return_value = None
        cache = EmbeddingCache(redis, model="m")
        result = await cache.get(tenant_id="t", text="hello")
        assert result is None
        assert cache.stats.misses == 1
        assert cache.stats.hits == 0

    @pytest.mark.asyncio
    async def test_hit_returns_vector_increments_hits(self) -> None:
        redis = _make_redis()
        redis.get.return_value = vector_to_bytes([0.5, -0.5])
        cache = EmbeddingCache(redis, model="m")
        result = await cache.get(tenant_id="t", text="hello")
        assert result is not None
        assert len(result) == 2
        assert cache.stats.hits == 1
        assert cache.stats.misses == 0

    @pytest.mark.asyncio
    async def test_put_calls_setex_with_packed_bytes(self) -> None:
        redis = _make_redis()
        cache = EmbeddingCache(redis, model="m", ttl_seconds=600)
        await cache.put(tenant_id="t", text="hello", vector=[1.0, 2.0])
        args = redis.setex.await_args[0]
        assert "tenant:t:emb:m:" in args[0]
        assert args[1] == 600
        # Packed bytes round-trip back.
        assert bytes_to_vector(args[2]) == pytest.approx([1.0, 2.0])

    @pytest.mark.asyncio
    async def test_put_skips_empty_vector(self) -> None:
        # NEGATIVE: an empty vector would be cached as zero bytes
        # and look like a miss on read — silent corruption. Skip.
        redis = _make_redis()
        cache = EmbeddingCache(redis, model="m")
        await cache.put(tenant_id="t", text="hello", vector=[])
        redis.setex.assert_not_called()


class TestFailOpen:
    @pytest.mark.asyncio
    async def test_get_connection_error_fails_open(self) -> None:
        # §38 contract: dead cache must NOT 5xx; treat as miss.
        redis = _make_redis()
        redis.get.side_effect = aioredis.ConnectionError("down")
        cache = EmbeddingCache(redis, model="m")
        assert await cache.get(tenant_id="t", text="x") is None
        assert cache.stats.misses == 1

    @pytest.mark.asyncio
    async def test_get_timeout_fails_open(self) -> None:
        redis = _make_redis()
        redis.get.side_effect = aioredis.TimeoutError("slow")
        cache = EmbeddingCache(redis, model="m")
        assert await cache.get(tenant_id="t", text="x") is None

    @pytest.mark.asyncio
    async def test_put_connection_error_fails_open(self) -> None:
        redis = _make_redis()
        redis.setex.side_effect = aioredis.ConnectionError("down")
        cache = EmbeddingCache(redis, model="m")
        # Must NOT raise.
        await cache.put(tenant_id="t", text="x", vector=[1.0])

    @pytest.mark.asyncio
    async def test_corrupt_bytes_treated_as_miss(self) -> None:
        # If a key holds garbage (e.g. partial overwrite by a buggy
        # writer), get() must NOT crash — treat as miss.
        redis = _make_redis()
        redis.get.return_value = b"abc"  # 3 bytes, not divisible by 4
        cache = EmbeddingCache(redis, model="m")
        assert await cache.get(tenant_id="t", text="x") is None
        assert cache.stats.misses == 1


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_empty_tenant_id_rejected_on_get(self) -> None:
        # Cross-tenant cache key construction MUST be impossible.
        cache = EmbeddingCache(_make_redis(), model="m")
        with pytest.raises(ValueError, match="tenant_id is required"):
            await cache.get(tenant_id="", text="x")

    @pytest.mark.asyncio
    async def test_empty_tenant_id_rejected_on_put(self) -> None:
        cache = EmbeddingCache(_make_redis(), model="m")
        with pytest.raises(ValueError, match="tenant_id is required"):
            await cache.put(tenant_id="", text="x", vector=[1.0])

    @pytest.mark.asyncio
    async def test_empty_tenant_id_rejected_on_invalidate(self) -> None:
        cache = EmbeddingCache(_make_redis(), model="m")
        with pytest.raises(ValueError, match="tenant_id is required"):
            await cache.invalidate_tenant("")


class TestModelNamespacing:
    @pytest.mark.asyncio
    async def test_different_models_different_keys(self) -> None:
        redis = _make_redis()
        cache_v1 = EmbeddingCache(redis, model="nomic-v1")
        cache_v2 = EmbeddingCache(redis, model="nomic-v2")

        # Trigger a get on each — peek at the call args.
        await cache_v1.get(tenant_id="t", text="hello")
        v1_key = redis.get.await_args[0][0]
        redis.get.reset_mock()
        await cache_v2.get(tenant_id="t", text="hello")
        v2_key = redis.get.await_args[0][0]

        assert v1_key != v2_key
        assert "nomic-v1" in v1_key
        assert "nomic-v2" in v2_key


class TestInvalidate:
    @pytest.mark.asyncio
    async def test_invalidate_tenant_scans_and_deletes(self) -> None:
        redis = _make_redis()

        async def fake_iter(*_a, **_kw):
            for k in (b"tenant:t:emb:m:hash1", b"tenant:t:emb:m:hash2"):
                yield k

        redis.scan_iter = fake_iter
        cache = EmbeddingCache(redis, model="m")
        count = await cache.invalidate_tenant("t")
        assert count == 2
        assert redis.delete.await_count == 2
