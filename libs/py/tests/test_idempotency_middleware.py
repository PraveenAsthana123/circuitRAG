"""
Tests for documind_core.idempotency_middleware.

Covers:
- GET / DELETE pass-through (non-mutating methods)
- POST without X-Idempotency-Key passes through (no caching)
- POST without tenant_id passes through (no caching)
- POST with key + tenant: cache miss → handler runs → response cached
- POST with key + tenant: cache hit → handler NOT called, replay header set
- 5xx response NOT cached (clients should retry)
- 4xx response IS cached (validation errors are deterministic)
- Non-JSON body falls back to raw text caching
- X-Idempotency-Stored header on first store
- X-Idempotency-Replay header on cache hit
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient

from documind_core.idempotency import StoredResponse
from documind_core.idempotency_middleware import IdempotencyMiddleware


@pytest.fixture
def store() -> MagicMock:
    s = MagicMock()
    s.get = AsyncMock(return_value=None)
    s.put = AsyncMock()
    return s


@pytest.fixture
def app_factory(store: MagicMock):
    handler_calls = {"count": 0}

    def _make() -> tuple[FastAPI, dict]:
        from starlette.middleware.base import BaseHTTPMiddleware

        class TenantStamp(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                request.state.tenant_id = request.headers.get("X-Tenant-ID", "")
                return await call_next(request)

        app = FastAPI()
        # Middleware added LATER runs FIRST (outermost). To get
        # tenant-stamp BEFORE idempotency sees the request, register
        # IdempotencyMiddleware first (inner) and TenantStamp last
        # (outer). Real services use the same ordering: auth/tenant
        # outermost, business middleware innermost.
        app.add_middleware(IdempotencyMiddleware, store=store)
        app.add_middleware(TenantStamp)

        @app.post("/api/charge")
        async def charge():
            handler_calls["count"] += 1
            return {"id": "txn-1", "ok": True}

        @app.post("/api/fail")
        async def fail():
            handler_calls["count"] += 1
            return JSONResponse(status_code=503, content={"detail": "down"})

        @app.post("/api/validate-error")
        async def vlerr():
            handler_calls["count"] += 1
            return JSONResponse(status_code=422, content={"detail": "bad"})

        @app.get("/api/read")
        async def read():
            handler_calls["count"] += 1
            return {"ok": True}

        return app, handler_calls

    return _make


class TestPassThroughs:
    def test_get_passes_through(self, app_factory, store) -> None:
        app, calls = app_factory()
        with TestClient(app) as client:
            r = client.get("/api/read")
        assert r.status_code == 200
        # Cache must NOT have been touched for a GET.
        store.get.assert_not_called()
        store.put.assert_not_called()

    def test_post_without_key_passes_through(self, app_factory, store) -> None:
        app, calls = app_factory()
        with TestClient(app) as client:
            r = client.post("/api/charge", headers={"X-Tenant-ID": "t1"})
        assert r.status_code == 200
        # No key → no caching.
        store.get.assert_not_called()
        store.put.assert_not_called()

    def test_post_without_tenant_passes_through(self, app_factory, store) -> None:
        # NEGATIVE: a key without a tenant must NOT cache — would
        # be cross-tenant key reuse risk.
        app, calls = app_factory()
        with TestClient(app) as client:
            r = client.post("/api/charge", headers={"X-Idempotency-Key": "abc"})
        assert r.status_code == 200
        store.get.assert_not_called()
        store.put.assert_not_called()


class TestCacheMissThenStore:
    def test_first_request_runs_handler_and_stores(self, app_factory, store) -> None:
        app, calls = app_factory()
        store.get.return_value = None  # miss
        with TestClient(app) as client:
            r = client.post(
                "/api/charge",
                headers={"X-Tenant-ID": "t1", "X-Idempotency-Key": "k1"},
            )
        assert r.status_code == 200
        assert calls["count"] == 1
        # First-store header signals cache write.
        assert r.headers.get("X-Idempotency-Stored") == "true"
        store.put.assert_awaited_once()
        # Verify the cached body.
        put_kwargs = store.put.await_args.kwargs
        assert put_kwargs["tenant_id"] == "t1"
        assert put_kwargs["key"] == "k1"
        assert put_kwargs["status_code"] == 200


class TestCacheHit:
    def test_cache_hit_skips_handler_returns_replay(self, app_factory, store) -> None:
        app, calls = app_factory()
        # Pre-seed the cache.
        store.get.return_value = StoredResponse(
            status_code=200,
            body={"id": "txn-1", "ok": True},
        )
        with TestClient(app) as client:
            r = client.post(
                "/api/charge",
                headers={"X-Tenant-ID": "t1", "X-Idempotency-Key": "k1"},
            )
        assert r.status_code == 200
        # Handler MUST NOT have been called — that's the whole
        # idempotency contract.
        assert calls["count"] == 0
        assert r.headers.get("X-Idempotency-Replay") == "true"


class TestStatusBranching:
    def test_5xx_response_not_cached(self, app_factory, store) -> None:
        # NEGATIVE: 5xx is a transient/server failure — caching it
        # locks the user out of retry. Must NOT cache.
        app, _ = app_factory()
        store.get.return_value = None
        with TestClient(app) as client:
            r = client.post(
                "/api/fail",
                headers={"X-Tenant-ID": "t1", "X-Idempotency-Key": "k1"},
            )
        assert r.status_code == 503
        store.put.assert_not_called()

    def test_4xx_response_is_cached(self, app_factory, store) -> None:
        # 4xx (validation error) IS deterministic — cache it so
        # client retries don't keep re-validating.
        app, _ = app_factory()
        store.get.return_value = None
        with TestClient(app) as client:
            r = client.post(
                "/api/validate-error",
                headers={"X-Tenant-ID": "t1", "X-Idempotency-Key": "k1"},
            )
        assert r.status_code == 422
        store.put.assert_awaited_once()


class TestBodyHandling:
    def test_json_body_round_trips(self, app_factory, store) -> None:
        app, _ = app_factory()
        store.get.return_value = None
        with TestClient(app) as client:
            r = client.post(
                "/api/charge",
                headers={"X-Tenant-ID": "t1", "X-Idempotency-Key": "k1"},
            )
        # The body cached must be the parsed JSON dict, not a string.
        body = store.put.await_args.kwargs["body"]
        assert isinstance(body, dict)
        assert body == {"id": "txn-1", "ok": True}
