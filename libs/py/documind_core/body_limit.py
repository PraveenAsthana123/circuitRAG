"""
Request-body size limit (FastAPI middleware).

Complements the gateway's body limit — defense in depth. A compromised
or misconfigured gateway shouldn't be able to DoS a service with a 2GB
JSON payload.

Use at service startup::

    app.add_middleware(BodyLimitMiddleware, max_bytes=5 * 1024 * 1024)
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger(__name__)


class BodyLimitMiddleware(BaseHTTPMiddleware):
    """Cap request body size. Upload routes should apply a LARGER cap via a
    dedicated middleware instance or route-level guard."""

    def __init__(self, app, *, max_bytes: int, path_overrides: dict[str, int] | None = None) -> None:  # noqa: ANN001
        super().__init__(app)
        self.max_bytes = max_bytes
        self.path_overrides = path_overrides or {}

    def _limit_for(self, path: str) -> int:
        for prefix, limit in self.path_overrides.items():
            if path.startswith(prefix):
                return limit
        return self.max_bytes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable]
    ):  # noqa: ANN201
        limit = self._limit_for(request.url.path)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                size = int(content_length)
            except ValueError:
                size = 0
            if size > limit:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": "request body too large",
                        "error_code": "BODY_TOO_LARGE",
                        "details": {"max_bytes": limit, "got_bytes": size},
                    },
                )
        return await call_next(request)
