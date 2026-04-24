"""
FastAPI middleware stack (Design Areas 62 — Observability, 5 — Tenant,
Global CLAUDE.md §4.3 — Security headers, §4.4 — Rate limiting).

Five middlewares, applied in THIS ORDER at every service::

    CorrelationIdMiddleware      # stamps request with UUID + propagates to logs
    SecurityHeadersMiddleware     # CSP, HSTS, X-Frame-Options, …
    TenantContextMiddleware       # extracts tenant_id from JWT, sets contextvars
    RateLimitMiddleware          # per-tenant + per-IP sliding-window limiter
    ExceptionHandlerMiddleware   # converts AppError → JSON error envelope

Order matters: we want correlation IDs on EVERY log line (even for requests
that error before authentication), so CorrelationId comes first. Rate limit
runs *after* tenant extraction so we can apply tenant-specific limits.

Why not ``BaseHTTPMiddleware``
------------------------------
FastAPI's ``BaseHTTPMiddleware`` has a known performance issue under load
(it consumes the body into memory). We use the raw ASGI ``__call__``
interface for anything in the hot path.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .exceptions import AppError, RateLimitedError
from .logging_config import bind_request_context, clear_request_context
from .rate_limiter import RateLimiter, tenant_key, ip_key

log = logging.getLogger(__name__)

CORRELATION_HEADER = "X-Correlation-ID"


# ---------------------------------------------------------------------------
# 1. Correlation ID
# ---------------------------------------------------------------------------
class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Reads (or generates) a correlation ID and binds it to:

    * the ContextVar used by structlog (so every log line includes it);
    * the response header (so clients can report it back to support).

    If the caller sends ``X-Correlation-ID``, we trust + propagate it — this
    is how the frontend links its Sentry trace to our server logs.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        cid = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        bind_request_context(correlation_id=cid)
        request.state.correlation_id = cid

        start = time.monotonic()
        try:
            response: Response = await call_next(request)
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            log.info(
                "request_complete method=%s path=%s duration_ms=%.1f",
                request.method, request.url.path, elapsed_ms,
            )
            clear_request_context()

        response.headers[CORRELATION_HEADER] = cid
        return response


# ---------------------------------------------------------------------------
# 2. Security headers
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add the baseline security headers recommended by OWASP to every response.

    These are CHEAP — a few bytes per response — and fix whole classes of
    vulnerabilities (clickjacking, MIME sniffing, mixed content).
    """

    def __init__(self, app: ASGIApp, csp: str | None = None) -> None:
        super().__init__(app)
        self.csp = csp or "default-src 'self'"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault("Content-Security-Policy", self.csp)
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        return response


# ---------------------------------------------------------------------------
# 3. Tenant context (extract from Authorization JWT or X-Tenant-ID header)
# ---------------------------------------------------------------------------
class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Extract the tenant identifier from the request and bind it to the logging
    context.

    In dev, we accept an ``X-Tenant-ID`` header for ease of testing. In
    production, the API Gateway validates the JWT and forwards the tenant in
    a signed header — services here just read that header and bind it.

    Services should still validate that the authenticated principal HAS
    access to the stated tenant — that's the Identity Service's job, done
    at the gateway. This middleware is about LOGGING + RLS context, not
    access control.
    """

    def __init__(self, app: ASGIApp, *, header: str = "X-Tenant-ID", default: str = "") -> None:
        super().__init__(app)
        self.header = header
        self.default = default

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        tenant_id = request.headers.get(self.header, self.default)
        user_id = request.headers.get("X-User-ID", "")
        bind_request_context(
            correlation_id=getattr(request.state, "correlation_id", ""),
            tenant_id=tenant_id,
            user_id=user_id,
        )
        request.state.tenant_id = tenant_id
        request.state.user_id = user_id
        return await call_next(request)


# ---------------------------------------------------------------------------
# 4. Rate limit
# ---------------------------------------------------------------------------
class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-tenant (authenticated) or per-IP (anonymous) sliding-window limiter.

    Path-specific limits (``/api/v1/admin/*`` stricter than ``/api/v1/docs``)
    are handled by the caller wiring multiple middleware instances or by a
    callback that returns the right (limit, window) tuple per request.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: RateLimiter,
        default_limit_per_min: int = 100,
        admin_limit_per_min: int = 50,
        upload_limit_per_min: int = 10,
    ) -> None:
        super().__init__(app)
        self.limiter = limiter
        self.default_limit = default_limit_per_min
        self.admin_limit = admin_limit_per_min
        self.upload_limit = upload_limit_per_min

    def _select_budget(self, path: str, method: str) -> tuple[int, int, str]:
        """Return ``(limit, window_seconds, endpoint_label)`` for the request."""
        if path.startswith("/api/v1/admin"):
            return self.admin_limit, 60, "admin"
        if method == "POST" and "/upload" in path:
            return self.upload_limit, 60, "upload"
        return self.default_limit, 60, "api"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Skip health + metrics endpoints — they must not be rate-limited
        if request.url.path in ("/health", "/healthz", "/metrics"):
            return await call_next(request)

        tenant_id = getattr(request.state, "tenant_id", "")
        limit, window, endpoint = self._select_budget(request.url.path, request.method)

        key = (
            tenant_key(tenant_id, endpoint)
            if tenant_id
            else ip_key(request.client.host if request.client else "unknown", endpoint)
        )

        try:
            result = await self.limiter.check_or_raise(
                key=key, limit=limit, window_seconds=window
            )
        except RateLimitedError as exc:
            return JSONResponse(
                status_code=429,
                content=exc.to_dict() | {"correlation_id": getattr(request.state, "correlation_id", "")},
                headers={"Retry-After": str(exc.details.get("retry_after_seconds", window))},
            )

        response = await call_next(request)
        # Expose limit state to clients so they can self-throttle
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.reset_in_seconds)
        return response


# ---------------------------------------------------------------------------
# 5. Domain-exception → error envelope
# ---------------------------------------------------------------------------
def register_exception_handlers(app) -> None:  # noqa: ANN001 — FastAPI typing pain
    """
    Install a single handler that converts every :class:`AppError` into the
    consistent error envelope mandated by global CLAUDE.md §6.2::

        {
            "detail": "...",
            "error_code": "...",
            "details": {},
            "correlation_id": "..."
        }

    Services call this in their ``app/main.py`` after instantiating ``app``.
    """
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)  # noqa: S101

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:  # noqa: ANN202
        body = exc.to_dict() | {
            "correlation_id": getattr(request.state, "correlation_id", ""),
        }
        log.warning(
            "app_error error_code=%s status=%d message=%s",
            exc.error_code, exc.http_status, exc.message,
        )
        return JSONResponse(status_code=exc.http_status, content=body)
