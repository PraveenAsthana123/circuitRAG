"""
Tests for documind_core.idempotency — Redis-backed X-Idempotency-Key cache.

Covers:
- StoredResponse dataclass shape
- IdempotencyStore._key namespacing (tenant + route + key)
- get(): cache miss returns None
- get(): cache hit returns StoredResponse with status_code + body
- get(): bad JSON returns None (corrupt cache must not crash)
- get(): missing required fields returns None (KeyError safety)
- put(): writes JSON payload via setex with TTL
- put(): default=str fallback for non-JSON-native bodies (datetime)
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.asyncio as aioredis

from documind_core.idempotency import IdempotencyStore, StoredResponse


def _make_redis() -> MagicMock:
    redis = MagicMock(spec=aioredis.Redis)
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    return redis


class TestStoredResponse:
    def test_dataclass_fields(self) -> None:
        r = StoredResponse(status_code=200, body={"ok": True})
        assert r.status_code == 200
        assert r.body == {"ok": True}


class TestKey:
    def test_namespaces_by_tenant_route_key(self) -> None:
        # Cross-tenant or cross-route key reuse must be impossible —
        # the prefix is the contract.
        k = IdempotencyStore._key("tnt-1", "/api/v1/charge", "uuid-abc")
        assert k == "tenant:tnt-1:idem:/api/v1/charge:uuid-abc"

    def test_different_tenants_get_different_keys(self) -> None:
        a = IdempotencyStore._key("t1", "/r", "k")
        b = IdempotencyStore._key("t2", "/r", "k")
        assert a != b


class TestGet:
    @pytest.mark.asyncio
    async def test_miss_returns_none(self) -> None:
        redis = _make_redis()
        redis.get.return_value = None
        store = IdempotencyStore(redis)
        r = await store.get(tenant_id="t", route="/r", key="k")
        assert r is None

    @pytest.mark.asyncio
    async def test_hit_returns_stored_response(self) -> None:
        redis = _make_redis()
        redis.get.return_value = b'{"status_code": 201, "body": {"id": "doc-1"}}'
        store = IdempotencyStore(redis)
        r = await store.get(tenant_id="t", route="/r", key="k")
        assert r is not None
        assert r.status_code == 201
        assert r.body == {"id": "doc-1"}

    @pytest.mark.asyncio
    async def test_bad_json_returns_none(self) -> None:
        # Corrupt cache must NOT crash callers — treat as miss + log.
        redis = _make_redis()
        redis.get.return_value = b"not-json"
        store = IdempotencyStore(redis)
        r = await store.get(tenant_id="t", route="/r", key="k")
        assert r is None

    @pytest.mark.asyncio
    async def test_missing_required_field_returns_none(self) -> None:
        # KeyError safety — JSON parsed but schema mismatch (older
        # writer wrote a different shape, etc.).
        redis = _make_redis()
        redis.get.return_value = b'{"status_code": 200}'  # no body
        store = IdempotencyStore(redis)
        r = await store.get(tenant_id="t", route="/r", key="k")
        assert r is None


class TestPut:
    @pytest.mark.asyncio
    async def test_write_uses_setex_with_ttl(self) -> None:
        redis = _make_redis()
        store = IdempotencyStore(redis, ttl_seconds=3600)
        await store.put(tenant_id="t", route="/r", key="k", status_code=201, body={"x": 1})
        args = redis.setex.await_args[0]
        assert args[0] == "tenant:t:idem:/r:k"
        assert args[1] == 3600  # TTL
        # Payload is canonical JSON we can round-trip.
        payload = json.loads(args[2])
        assert payload["status_code"] == 201
        assert payload["body"] == {"x": 1}

    @pytest.mark.asyncio
    async def test_default_str_fallback_for_datetime(self) -> None:
        # default=str makes datetime / UUID survive JSON serialization.
        # Without it, put() would crash on real-world payloads.
        redis = _make_redis()
        store = IdempotencyStore(redis)
        await store.put(
            tenant_id="t",
            route="/r",
            key="k",
            status_code=200,
            body={"created_at": datetime(2026, 1, 1)},
        )
        payload_str = redis.setex.await_args[0][2]
        assert "2026" in payload_str
