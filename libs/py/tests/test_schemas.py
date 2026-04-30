"""
Tests for documind_core.schemas — shared API response envelopes.

Covers:
- SuccessResponse / PaginatedResponse / ErrorResponse / HealthResponse
  field shapes + defaults
- PaginatedResponse limit clamps (ge=1, le=500) — guards against
  unbounded list endpoints (the §6 pagination contract)
- offset/total ge=0 — negative paging is a 422, not silent garbage
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from documind_core.schemas import (
    ErrorResponse,
    HealthResponse,
    PaginatedResponse,
    SuccessResponse,
)


class TestSuccessResponse:
    def test_minimal_payload(self) -> None:
        r = SuccessResponse[int](data=42)
        assert r.data == 42
        assert r.correlation_id == ""

    def test_correlation_id_passes_through(self) -> None:
        r = SuccessResponse[str](data="ok", correlation_id="abc-123")
        assert r.correlation_id == "abc-123"

    def test_generic_dict_data(self) -> None:
        r = SuccessResponse[dict](data={"k": "v"})
        assert r.data == {"k": "v"}


class TestPaginatedResponse:
    def test_basic(self) -> None:
        r = PaginatedResponse[int](items=[1, 2, 3], total=10, offset=0, limit=3)
        assert r.items == [1, 2, 3]
        assert r.has_more is False  # default

    def test_has_more_flag(self) -> None:
        r = PaginatedResponse[str](items=["a"], total=100, offset=0, limit=1, has_more=True)
        assert r.has_more is True

    def test_negative_offset_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PaginatedResponse[int](items=[], total=0, offset=-1, limit=10)

    def test_negative_total_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PaginatedResponse[int](items=[], total=-1, offset=0, limit=10)

    def test_limit_zero_rejected(self) -> None:
        # ge=1 — limit=0 is meaningless and reaches the unbounded-list bug
        # (an endpoint accepting limit=0 may return everything).
        with pytest.raises(ValidationError):
            PaginatedResponse[int](items=[], total=0, offset=0, limit=0)

    def test_limit_above_500_rejected(self) -> None:
        # le=500 — guards against expensive scans.
        with pytest.raises(ValidationError):
            PaginatedResponse[int](items=[], total=0, offset=0, limit=501)


class TestErrorResponse:
    def test_default_details_is_empty_dict(self) -> None:
        r = ErrorResponse(detail="bad", error_code="VALIDATION")
        assert r.details == {}
        assert r.correlation_id == ""

    def test_with_details(self) -> None:
        r = ErrorResponse(
            detail="missing field",
            error_code="VALIDATION",
            details={"field": "email"},
            correlation_id="cid-1",
        )
        assert r.details == {"field": "email"}


class TestHealthResponse:
    def test_minimal(self) -> None:
        r = HealthResponse(status="ok", service="x")
        assert r.version == "0.1.0"
        assert r.checks == {}

    def test_with_checks(self) -> None:
        r = HealthResponse(
            status="degraded",
            service="ingestion-svc",
            checks={"postgres": "ok", "redis": "down"},
        )
        assert r.checks["redis"] == "down"
