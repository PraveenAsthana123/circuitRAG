"""
FastAPI middleware for the ``X-Idempotency-Key`` pattern (Design Area 20).

Applies to POST / PUT / PATCH requests. On first sight of a key, the
response (status + body) is cached under the tenant + route + key; any
duplicate request returns the cached response without re-invoking the
handler.

Two-phase flow:

1. Before the handler runs, check for a cached response; if present,
   return it immediately.
2. After the handler runs, cache the response (unless status >= 500 —
   we don't cache transient server errors; callers should retry).

Usage::

    app.add_middleware(
        IdempotencyMiddleware,
        store=IdempotencyStore(redis_client, ttl_seconds=86400),
    )
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .idempotency import IdempotencyStore

log = logging.getLogger(__name__)

_MUTATING = {"POST", "PUT", "PATCH"}
_HEADER = "X-Idempotency-Key"


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, store: IdempotencyStore) -> None:  # noqa: ANN001
        super().__init__(app)
        self.store = store

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method not in _MUTATING:
            return await call_next(request)

        key = request.headers.get(_HEADER, "").strip()
        tenant_id = getattr(request.state, "tenant_id", "") or ""
        if not key or not tenant_id:
            # Missing key or tenant — pass through without caching.
            return await call_next(request)

        route = request.url.path

        # Phase 1 — return cached if we've seen this key.
        cached = await self.store.get(tenant_id=tenant_id, route=route, key=key)
        if cached is not None:
            log.info("idempotency_cache_hit route=%s key_prefix=%s", route, key[:8])
            return JSONResponse(
                status_code=cached.status_code,
                content=cached.body,
                headers={"X-Idempotency-Replay": "true"},
            )

        # Phase 2 — handler runs; we buffer the body to cache it.
        response = await call_next(request)
        if 200 <= response.status_code < 500:
            body_bytes = b""
            async for chunk in response.body_iterator:
                body_bytes += chunk

            # Try to deserialize JSON; if that fails, cache raw text.
            body: Any
            try:
                import json
                body = json.loads(body_bytes.decode("utf-8") or "null")
            except Exception:
                body = body_bytes.decode("utf-8", errors="replace")

            await self.store.put(
                tenant_id=tenant_id,
                route=route,
                key=key,
                status_code=response.status_code,
                body=body,
            )

            # Rebuild the response since we consumed the body iterator.
            new_headers = dict(response.headers)
            new_headers["X-Idempotency-Stored"] = "true"
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=new_headers,
                media_type=response.media_type,
            )

        # 5xx: do NOT cache — let clients retry.
        return response
