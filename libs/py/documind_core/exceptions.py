"""
Domain exception hierarchy (Design Area 9 — State Model; cross-cutting).

Contract
--------
Services raise ONLY subclasses of :class:`AppError`. The HTTP layer (FastAPI
exception handlers in each service) is the ONLY place that converts these
into :class:`fastapi.HTTPException` / :class:`fastapi.responses.JSONResponse`.

This separation is what makes business logic **transport-agnostic**:

* A service can be called from HTTP, gRPC, Kafka consumer, CLI, or unit test
  without changing — it always raises the same domain error.
* Error responses are consistent across services: same shape, same envelope,
  same ``error_code`` taxonomy.
* Tests assert on the class, not on a status code.

Each error carries:

* ``error_code`` — stable string identifier (never localized), used by
  clients to branch on without string-matching human messages.
* ``http_status`` — default HTTP status for the FastAPI handler.
* ``details`` — optional structured context (safe to log and return).
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """
    Base class for every domain error in DocuMind.

    Never raise :class:`AppError` directly — pick a specific subclass. If none
    fits, add a new subclass rather than stuffing unrelated errors under the
    base class.
    """

    #: Stable machine-readable identifier (UPPER_SNAKE_CASE). Returned to
    #: API callers so they can branch on it.
    error_code: str = "APP_ERROR"

    #: HTTP status code the FastAPI exception handler should return.
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        # Allow per-raise override of class defaults (rare but useful).
        if error_code is not None:
            self.error_code = error_code
        if http_status is not None:
            self.http_status = http_status
        self.details: dict[str, Any] = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the API error envelope. Correlation ID is added by the
        middleware, not here — this class does not know about request context."""
        return {
            "detail": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }

    def __repr__(self) -> str:  # pragma: no cover — cosmetic
        return f"{type(self).__name__}(error_code={self.error_code!r}, message={self.message!r})"


# ---------------------------------------------------------------------------
# 4xx family
# ---------------------------------------------------------------------------
class NotFoundError(AppError):
    """Requested resource does not exist (or is not visible to the caller)."""

    error_code = "NOT_FOUND"
    http_status = 404


class ValidationError(AppError):
    """Input failed validation (schema, semantic, or business-rule)."""

    error_code = "VALIDATION_ERROR"
    http_status = 400


class TenantIsolationError(AppError):
    """
    Caller tried to access a resource in a different tenant.

    Raise this **before** any data leak can happen. Unlike NotFoundError, this
    signals a deliberate cross-tenant attempt — log it loudly, the security
    team may want to see it.
    """

    error_code = "TENANT_ISOLATION_VIOLATION"
    http_status = 403


class RateLimitedError(AppError):
    """Caller exceeded their rate-limit budget."""

    error_code = "RATE_LIMITED"
    http_status = 429

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        retry_after_seconds: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = dict(details or {})
        if retry_after_seconds is not None:
            details["retry_after_seconds"] = retry_after_seconds
        super().__init__(message, details=details)


class PolicyViolationError(AppError):
    """A governance policy rejected the request (PII, budget, content safety …)."""

    error_code = "POLICY_VIOLATION"
    http_status = 403


# ---------------------------------------------------------------------------
# 5xx family
# ---------------------------------------------------------------------------
class DataError(AppError):
    """Data-layer failure: DB unavailable, corrupt payload, migration issue."""

    error_code = "DATA_ERROR"
    http_status = 500


class ModelError(AppError):
    """ML/LLM produced invalid output that can't be salvaged."""

    error_code = "MODEL_ERROR"
    http_status = 500


class ExternalServiceError(AppError):
    """
    A dependency (Ollama, Qdrant, Neo4j, SaaS API) is unreachable, timing
    out, or returned an error we can't handle.

    Services should NOT silently return fallback data when this is raised —
    that violates global CLAUDE.md §10.3 and §38 ("never deploy ML output
    directly to users without a decision layer"). Either degrade explicitly
    (return a cached answer with a ``degraded=true`` flag) or propagate.
    """

    error_code = "EXTERNAL_SERVICE_ERROR"
    http_status = 502


class CircuitOpenError(ExternalServiceError):
    """
    Circuit breaker is open — we are deliberately short-circuiting calls to a
    failing dependency.

    Raising this is FAST (no network round-trip). It tells the caller
    "we know this is down; stop asking". Clients should back off.
    """

    error_code = "CIRCUIT_OPEN"
    http_status = 503
