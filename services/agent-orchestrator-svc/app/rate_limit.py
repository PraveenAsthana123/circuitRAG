"""In-memory rate limiter for the orchestrator (P1 #33).

Single-pod simple sliding-window. Sufficient for single-pod dev +
small production. Multi-pod prod should use the Redis-backed
documind_core.rate_limiter via RateLimitMiddleware (separate module
to keep the orchestrator's hot path light).

Sliding-window semantics: keep a deque of timestamps per (key, endpoint).
On each request, drop timestamps older than window_s, then check len < cap.

Identity: per-tenant when X-Tenant-Id header present, per-IP when
anonymous. Unit-tested + drilled.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("orchestrator.rate_limit")


class InMemorySlidingWindowLimiter:
    """Token-free sliding-window limiter. Thread-safe via threading.Lock."""

    def __init__(self, *, limit_per_minute: int = 60) -> None:
        self.limit = max(1, limit_per_minute)
        self.window_s = 60.0
        # Per-key timestamp deque. Bounded by the window logic so memory
        # is naturally bounded by (active keys × limit_per_minute).
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int, int]:
        """Returns (allowed, remaining, reset_in_seconds).

        On `allowed=False`, caller returns 429 + Retry-After header.
        """
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            # Drop timestamps outside the window.
            cutoff = now - self.window_s
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                # Reset = when the oldest in-window timestamp will fall out.
                reset_in = max(1, int(bucket[0] + self.window_s - now) + 1)
                return False, 0, reset_in
            bucket.append(now)
            return True, max(0, self.limit - len(bucket)), self.window_s


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-tenant + per-IP sliding-window limiter for orchestrator endpoints."""

    def __init__(
        self,
        app,  # noqa: ANN001
        *,
        limit_per_minute: int = 60,
        path_prefix: str = "/api/v1/agentic/tasks",
    ) -> None:
        super().__init__(app)
        self._limiter = InMemorySlidingWindowLimiter(limit_per_minute=limit_per_minute)
        self._path_prefix = path_prefix

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],  # noqa: F821
    ):
        # Only rate-limit POSTs to the protected path. Reads + admin
        # routes pass through (operator dashboards can poll fast).
        if request.method == "POST" and request.url.path.startswith(self._path_prefix):
            tenant_id = request.headers.get("X-Tenant-Id")
            ident = (
                f"tenant:{tenant_id}" if tenant_id
                else f"ip:{request.client.host if request.client else 'unknown'}"
            )
            key = f"{ident}:{request.url.path}"
            allowed, remaining, reset_in = self._limiter.check(key)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "rate limit exceeded",
                        "error_code": "RATE_LIMIT_EXCEEDED",
                        "limit": self._limiter.limit,
                        "reset_in_seconds": reset_in,
                    },
                    headers={
                        "Retry-After": str(reset_in),
                        "X-RateLimit-Limit": str(self._limiter.limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_in),
                    },
                )

        return await call_next(request)


# Late import to avoid Any-not-imported issue at module load.
from typing import Any  # noqa: E402
