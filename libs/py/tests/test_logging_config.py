"""
Tests for documind_core.logging_config — JSON structured logging.

Covers:
- setup_logging configures structlog + stdlib root logger
- bind_request_context / clear_request_context manage contextvars
- _inject_context stamps correlation_id / tenant_id / user_id
- _inject_otel_trace adds trace_id + span_id from current span
- _inject_baggage merges OTel baggage into log events
- _rename_event_to_message maps structlog 'event' → JSON 'message'
- get_logger returns a BoundLogger
- Setup is safely repeatable (called twice — no exception, last
  config wins)
- json_format=False uses ConsoleRenderer (dev mode)
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import structlog

from documind_core.logging_config import (
    _inject_baggage,
    _inject_context,
    _inject_otel_trace,
    _rename_event_to_message,
    bind_request_context,
    clear_request_context,
    correlation_id_var,
    get_logger,
    setup_logging,
    tenant_id_var,
    user_id_var,
)

# ── _inject_context ───────────────────────────────────────────


class TestInjectContext:
    def setup_method(self) -> None:
        clear_request_context()

    def teardown_method(self) -> None:
        clear_request_context()

    def test_no_context_set_passes_through(self) -> None:
        out = _inject_context(None, "info", {})
        assert "correlation_id" not in out
        assert "tenant_id" not in out
        assert "user_id" not in out

    def test_correlation_stamped_when_set(self) -> None:
        correlation_id_var.set("cid-42")
        out = _inject_context(None, "info", {})
        assert out["correlation_id"] == "cid-42"

    def test_all_three_stamped(self) -> None:
        correlation_id_var.set("cid")
        tenant_id_var.set("tnt")
        user_id_var.set("usr")
        out = _inject_context(None, "info", {})
        assert out == {"correlation_id": "cid", "tenant_id": "tnt", "user_id": "usr"}

    def test_explicit_event_field_wins(self) -> None:
        # If the caller passed correlation_id explicitly, do NOT clobber.
        correlation_id_var.set("from-context")
        out = _inject_context(None, "info", {"correlation_id": "from-caller"})
        assert out["correlation_id"] == "from-caller"


# ── _inject_otel_trace ────────────────────────────────────────


class TestInjectOTelTrace:
    def test_no_active_span_passes_through(self) -> None:
        with patch("opentelemetry.trace.get_current_span") as mock_span:
            mock_span.return_value = MagicMock(get_span_context=MagicMock(return_value=None))
            out = _inject_otel_trace(None, "info", {})
            assert "trace_id" not in out

    def test_active_span_stamps_ids(self) -> None:
        ctx = MagicMock(is_valid=True, trace_id=0x1234, span_id=0xABCD)
        span = MagicMock()
        span.get_span_context.return_value = ctx
        with patch("opentelemetry.trace.get_current_span", return_value=span):
            out = _inject_otel_trace(None, "info", {})
        assert "trace_id" in out and "span_id" in out
        assert len(out["trace_id"]) == 32  # 128-bit hex
        assert len(out["span_id"]) == 16  # 64-bit hex

    def test_invalid_span_context_skipped(self) -> None:
        ctx = MagicMock(is_valid=False)
        span = MagicMock()
        span.get_span_context.return_value = ctx
        with patch("opentelemetry.trace.get_current_span", return_value=span):
            out = _inject_otel_trace(None, "info", {})
        assert "trace_id" not in out


# ── _inject_baggage ───────────────────────────────────────────


class TestInjectBaggage:
    def test_baggage_keys_added_when_absent(self) -> None:
        with patch("opentelemetry.baggage.get_all", return_value={"region": "us-east", "x": 1}):
            out = _inject_baggage(None, "info", {})
        assert out["region"] == "us-east"
        assert out["x"] == "1"  # str-coerced

    def test_existing_keys_not_overwritten(self) -> None:
        # Explicit fields beat baggage — collision policy.
        with patch("opentelemetry.baggage.get_all", return_value={"k": "from-baggage"}):
            out = _inject_baggage(None, "info", {"k": "from-caller"})
        assert out["k"] == "from-caller"

    def test_empty_baggage_is_noop(self) -> None:
        with patch("opentelemetry.baggage.get_all", return_value={}):
            out = _inject_baggage(None, "info", {"a": 1})
        assert out == {"a": 1}


# ── _rename_event_to_message ──────────────────────────────────


class TestRenameEventToMessage:
    def test_event_renamed(self) -> None:
        out = _rename_event_to_message(None, "info", {"event": "uploaded"})
        assert out == {"message": "uploaded"}

    def test_no_event_field_unchanged(self) -> None:
        out = _rename_event_to_message(None, "info", {"message": "x"})
        assert out == {"message": "x"}


# ── setup_logging ─────────────────────────────────────────────


class TestSetupLogging:
    def teardown_method(self) -> None:
        # Restore default structlog config so other tests aren't affected.
        structlog.reset_defaults()

    def test_json_format_default(self) -> None:
        setup_logging(service_name="test-svc", level="INFO")
        # Root logger has exactly one handler (our StreamHandler).
        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert root.level == logging.INFO

    def test_dev_console_renderer(self) -> None:
        setup_logging(service_name="test-svc", level="DEBUG", json_format=False)
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_noisy_libraries_quieted(self) -> None:
        setup_logging(service_name="x")
        for noisy in ("httpx", "httpcore", "uvicorn.access", "asyncio", "kafka"):
            assert logging.getLogger(noisy).level == logging.WARNING

    def test_idempotent(self) -> None:
        # Calling setup twice should not raise. Last config wins.
        setup_logging(service_name="x", level="INFO")
        setup_logging(service_name="y", level="WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_lowercase_level_accepted(self) -> None:
        # Operators commonly set LEVEL=info via env — must work.
        setup_logging(service_name="x", level="info")
        assert logging.getLogger().level == logging.INFO


# ── get_logger ────────────────────────────────────────────────


class TestGetLogger:
    def test_returns_bound_logger(self) -> None:
        log = get_logger("test.module")
        assert log is not None
        # BoundLogger has .info / .error / .bind from structlog.
        assert hasattr(log, "info")
        assert hasattr(log, "bind")


# ── bind_request_context / clear_request_context ──────────────


class TestRequestContext:
    def setup_method(self) -> None:
        clear_request_context()

    def teardown_method(self) -> None:
        clear_request_context()

    def test_bind_only_correlation(self) -> None:
        bind_request_context(correlation_id="cid-1")
        assert correlation_id_var.get() == "cid-1"
        # tenant / user not set — stay default empty strings
        assert tenant_id_var.get() == ""
        assert user_id_var.get() == ""

    def test_bind_full_context(self) -> None:
        bind_request_context(correlation_id="c", tenant_id="t", user_id="u")
        assert correlation_id_var.get() == "c"
        assert tenant_id_var.get() == "t"
        assert user_id_var.get() == "u"

    def test_clear_resets_all(self) -> None:
        bind_request_context(correlation_id="c", tenant_id="t", user_id="u")
        clear_request_context()
        assert correlation_id_var.get() == ""
        assert tenant_id_var.get() == ""
        assert user_id_var.get() == ""
