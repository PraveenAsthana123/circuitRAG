"""
Tests for documind_core.error_tracking — Sentry init wrapper.

Covers:
- init_sentry without DSN is silent no-op (dev/test path)
- init_sentry with DSN initializes once; second call is no-op
- set_tenant_context no-op before init (must NOT raise)
- set_tenant_context tags scope after init
- capture_exception no-op before init returns None
- is_initialized reflects state
- Reset helper restores clean state for sequential tests
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from documind_core.error_tracking import (
    _reset_for_tests,
    capture_exception,
    init_sentry,
    is_initialized,
    set_tenant_context,
)


@pytest.fixture(autouse=True)
def reset_module():
    _reset_for_tests()
    yield
    _reset_for_tests()


class TestInitWithoutDSN:
    def test_no_env_no_arg_returns_false(self, monkeypatch) -> None:
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        assert init_sentry(service_name="x") is False
        assert not is_initialized()

    def test_empty_env_returns_false(self, monkeypatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", "")
        assert init_sentry(service_name="x") is False

    def test_whitespace_env_returns_false(self, monkeypatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", "   ")
        assert init_sentry(service_name="x") is False


class TestInitWithDSN:
    def test_dsn_argument_initializes(self) -> None:
        # Patch the underlying sentry_sdk.init so the test doesn't
        # actually network out.
        with patch("sentry_sdk.init") as mock_init, patch("sentry_sdk.set_tag"):
            assert init_sentry(service_name="x", dsn="https://fake@sentry/1") is True
            assert is_initialized()
            mock_init.assert_called_once()

    def test_env_dsn_initializes(self, monkeypatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry/2")
        with patch("sentry_sdk.init"), patch("sentry_sdk.set_tag"):
            assert init_sentry(service_name="x") is True

    def test_explicit_dsn_overrides_env(self, monkeypatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", "from-env")
        with patch("sentry_sdk.init") as mock_init, patch("sentry_sdk.set_tag"):
            init_sentry(service_name="x", dsn="from-arg")
            # Verify the explicit DSN was used.
            assert mock_init.call_args.kwargs["dsn"] == "from-arg"

    def test_double_init_returns_false(self) -> None:
        # NEGATIVE: silent re-init would create duplicate event
        # streams. Second call MUST be a no-op.
        with patch("sentry_sdk.init"), patch("sentry_sdk.set_tag"):
            init_sentry(service_name="x", dsn="https://fake@sentry/1")
            assert init_sentry(service_name="x", dsn="https://fake@sentry/1") is False


class TestTenantContext:
    def test_noop_before_init(self) -> None:
        # Must NOT raise even when nothing is initialized — keeps
        # test/dev paths free of Sentry concerns.
        set_tenant_context(tenant_id="acme")  # no exception

    def test_sets_tag_after_init(self) -> None:
        with patch("sentry_sdk.init"), patch("sentry_sdk.set_tag"):
            init_sentry(service_name="x", dsn="https://fake@sentry/1")

        with patch("sentry_sdk.get_isolation_scope") as mock_scope:
            scope = mock_scope.return_value
            set_tenant_context(tenant_id="acme", user_id="u1")
            scope.set_tag.assert_called_with("tenant_id", "acme")
            scope.set_user.assert_called_with({"id": "u1"})

    def test_no_tenant_no_user_safe(self) -> None:
        with patch("sentry_sdk.init"), patch("sentry_sdk.set_tag"):
            init_sentry(service_name="x", dsn="https://fake@sentry/1")
        with patch("sentry_sdk.get_isolation_scope") as mock_scope:
            scope = mock_scope.return_value
            set_tenant_context(tenant_id=None)
            scope.set_tag.assert_not_called()
            scope.set_user.assert_not_called()


class TestCaptureException:
    def test_returns_none_before_init(self) -> None:
        # NEGATIVE: capture before init must NOT raise + must NOT
        # silently send to a default DSN.
        result = capture_exception(ValueError("test"))
        assert result is None

    def test_captures_after_init_with_extras(self) -> None:
        with patch("sentry_sdk.init"), patch("sentry_sdk.set_tag"):
            init_sentry(service_name="x", dsn="https://fake@sentry/1")

        with (
            patch("sentry_sdk.get_isolation_scope") as mock_scope,
            patch("sentry_sdk.capture_exception", return_value="event-id-123") as mock_capture,
        ):
            event_id = capture_exception(ValueError("boom"), correlation_id="cid-1")
            assert event_id == "event-id-123"
            scope = mock_scope.return_value
            scope.set_extra.assert_called_with("correlation_id", "cid-1")
            mock_capture.assert_called_once()


class TestIsInitialized:
    def test_false_initially(self) -> None:
        assert not is_initialized()

    def test_true_after_successful_init(self) -> None:
        with patch("sentry_sdk.init"), patch("sentry_sdk.set_tag"):
            init_sentry(service_name="x", dsn="https://fake@sentry/1")
        assert is_initialized()

    def test_false_after_skipped_init(self, monkeypatch) -> None:
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        init_sentry(service_name="x")
        assert not is_initialized()
