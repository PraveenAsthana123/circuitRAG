"""
Tests for documind_core.exceptions — domain exception hierarchy.

Covers:
- AppError init: defaults, per-raise error_code/http_status overrides
- to_dict envelope shape (used by FastAPI handlers)
- 4xx subclasses carry the correct error_code + http_status
- 5xx subclasses carry the correct error_code + http_status
- CircuitOpenError extends ExternalServiceError (isinstance contract —
  callers catching ExternalServiceError must also catch CircuitOpen)
- RateLimitedError stamps retry_after_seconds into details
"""

from __future__ import annotations

from documind_core.exceptions import (
    AppError,
    CircuitOpenError,
    DataError,
    ExternalServiceError,
    ModelError,
    NotFoundError,
    PolicyViolationError,
    RateLimitedError,
    TenantIsolationError,
    ValidationError,
)


class TestAppError:
    def test_defaults(self) -> None:
        e = AppError("boom")
        assert e.message == "boom"
        assert e.error_code == "APP_ERROR"
        assert e.http_status == 500
        assert e.details == {}

    def test_per_raise_error_code_override(self) -> None:
        # Per-raise override path (line 59).
        e = AppError("x", error_code="CUSTOM")
        assert e.error_code == "CUSTOM"

    def test_per_raise_http_status_override(self) -> None:
        # Per-raise override path (line 61).
        e = AppError("x", http_status=418)
        assert e.http_status == 418

    def test_details_passed_through(self) -> None:
        e = AppError("x", details={"k": "v"})
        assert e.details == {"k": "v"}

    def test_to_dict_envelope(self) -> None:
        # The shape FastAPI handlers must produce for the response.
        e = AppError("the message", error_code="X", details={"a": 1})
        envelope = e.to_dict()
        assert envelope == {
            "detail": "the message",
            "error_code": "X",
            "details": {"a": 1},
        }
        # NEGATIVE: correlation_id must NOT be added here — that's the
        # middleware's job. If it ever appears, tests catch the leak.
        assert "correlation_id" not in envelope


class TestSubclassCodes:
    def test_4xx_codes(self) -> None:
        cases = [
            (NotFoundError, "NOT_FOUND", 404),
            (ValidationError, "VALIDATION_ERROR", 400),
            (TenantIsolationError, "TENANT_ISOLATION_VIOLATION", 403),
            (RateLimitedError, "RATE_LIMITED", 429),
            (PolicyViolationError, "POLICY_VIOLATION", 403),
        ]
        for cls, code, status in cases:
            e = cls("x")
            assert e.error_code == code
            assert e.http_status == status

    def test_5xx_codes(self) -> None:
        cases = [
            (DataError, "DATA_ERROR", 500),
            (ModelError, "MODEL_ERROR", 500),
            (ExternalServiceError, "EXTERNAL_SERVICE_ERROR", 502),
            (CircuitOpenError, "CIRCUIT_OPEN", 503),
        ]
        for cls, code, status in cases:
            e = cls("x")
            assert e.error_code == code
            assert e.http_status == status


class TestCircuitOpenError:
    def test_is_external_service_error(self) -> None:
        # Callers catching ExternalServiceError must also catch
        # CircuitOpenError — that's the whole isinstance contract for
        # consolidated error handling.
        assert issubclass(CircuitOpenError, ExternalServiceError)
        e = CircuitOpenError("dep down")
        assert isinstance(e, ExternalServiceError)


class TestRateLimitedError:
    def test_default_message(self) -> None:
        e = RateLimitedError()
        assert e.message == "Rate limit exceeded"

    def test_retry_after_seconds_stamped_into_details(self) -> None:
        e = RateLimitedError(retry_after_seconds=30)
        assert e.details["retry_after_seconds"] == 30

    def test_retry_after_seconds_omitted(self) -> None:
        # When None, the key must NOT be in details (avoid leaking
        # null hints that confuse clients).
        e = RateLimitedError()
        assert "retry_after_seconds" not in e.details

    def test_details_merged_with_retry_after(self) -> None:
        e = RateLimitedError(details={"key": "tenant:x"}, retry_after_seconds=10)
        assert e.details["key"] == "tenant:x"
        assert e.details["retry_after_seconds"] == 10
