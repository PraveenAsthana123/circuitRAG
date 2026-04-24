"""
HTTP idempotency (Design Area 20).

Implements the ``X-Idempotency-Key`` pattern: clients send a UUID they
generate; the server caches the response body + status code under that key;
duplicate requests return the cached response without re-executing the
side-effecting handler.

This is what makes "retry on 5xx" safe for POSTs: the client can safely
retry because the server won't double-create.

Storage: Redis with 24-hour TTL. If you need longer windows (billing
compliance, legal replay), swap for a PostgreSQL table.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis

log = logging.getLogger(__name__)


@dataclass
class StoredResponse:
    status_code: int
    body: Any


class IdempotencyStore:
    """Redis-backed idempotency cache."""

    def __init__(self, redis: aioredis.Redis, *, ttl_seconds: int = 86400) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(tenant_id: str, route: str, key: str) -> str:
        # Namespace by tenant + route to prevent cross-tenant or cross-route
        # key reuse.
        return f"tenant:{tenant_id}:idem:{route}:{key}"

    async def get(
        self, *, tenant_id: str, route: str, key: str
    ) -> StoredResponse | None:
        raw = await self._redis.get(self._key(tenant_id, route, key))
        if raw is None:
            return None
        try:
            obj = json.loads(raw)
            return StoredResponse(status_code=obj["status_code"], body=obj["body"])
        except (json.JSONDecodeError, KeyError):
            log.warning("idempotency_bad_payload")
            return None

    async def put(
        self, *, tenant_id: str, route: str, key: str, status_code: int, body: Any
    ) -> None:
        payload = json.dumps(
            {"status_code": status_code, "body": body},
            default=str,
            separators=(",", ":"),
        )
        await self._redis.setex(
            self._key(tenant_id, route, key), self._ttl, payload
        )
