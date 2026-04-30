"""
Tests for documind_core.config — Pydantic Settings foundation.

Covers:
- BaseServiceSettings instantiates with defaults (dev sane defaults)
- env-prefix DOCUMIND_ and case_sensitive=False work
- postgres_dsn property formats correctly + uses get_secret_value()
- cors_origins_list splits + strips correctly
- is_production reflects env
- get_settings is LRU-cached and per-class
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from documind_core.config import BaseServiceSettings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Each test gets a fresh cache so env mutations are visible."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestDefaults:
    def test_default_env_is_development(self) -> None:
        s = BaseServiceSettings()
        assert s.env == "development"
        assert s.is_production is False

    def test_default_postgres_credentials(self) -> None:
        s = BaseServiceSettings()
        assert s.pg_host == "localhost"
        assert s.pg_port == 5432
        assert s.pg_db == "documind"

    def test_secret_passwords_default_to_dev_value(self) -> None:
        s = BaseServiceSettings()
        # SecretStr — get_secret_value() unwraps; printing must NOT leak.
        assert s.pg_password.get_secret_value() == "documind"
        # repr must hide the secret.
        assert "documind" not in repr(s.pg_password)

    def test_optional_secrets_default_to_none(self) -> None:
        s = BaseServiceSettings()
        assert s.encryption_key is None
        assert s.admin_api_key is None
        assert s.qdrant_api_key is None


class TestEnvOverride:
    def test_env_prefix_accepted(self, monkeypatch) -> None:
        monkeypatch.setenv("DOCUMIND_ENV", "production")
        s = BaseServiceSettings()
        assert s.env == "production"
        assert s.is_production is True

    def test_invalid_env_value_rejected(self, monkeypatch) -> None:
        monkeypatch.setenv("DOCUMIND_ENV", "not-a-real-env")
        # Literal["development", "staging", "production"] enforces.
        with pytest.raises(ValueError):
            BaseServiceSettings()

    def test_int_coercion(self, monkeypatch) -> None:
        monkeypatch.setenv("DOCUMIND_PG_PORT", "55432")
        s = BaseServiceSettings()
        assert s.pg_port == 55432  # str → int by pydantic

    def test_bool_coercion(self, monkeypatch) -> None:
        monkeypatch.setenv("DOCUMIND_LOG_JSON", "false")
        s = BaseServiceSettings()
        assert s.log_json is False


class TestPostgresDsn:
    def test_basic_format(self) -> None:
        s = BaseServiceSettings()
        dsn = s.postgres_dsn
        assert dsn.startswith("postgresql://documind:")
        assert "localhost" in dsn
        assert "/documind" in dsn

    def test_uses_get_secret_value(self) -> None:
        # Secret extracted into the URL — that's the DSN's whole job.
        # If pydantic ever changes Secret semantics, this test catches
        # any "<SecretStr...>" leak into the DSN.
        s = BaseServiceSettings(pg_password=SecretStr("super-secret"))
        assert "super-secret" in s.postgres_dsn
        assert "SecretStr" not in s.postgres_dsn


class TestCorsOriginsList:
    def test_default_split(self) -> None:
        s = BaseServiceSettings()
        origins = s.cors_origins_list
        assert "http://localhost:3000" in origins
        assert "http://localhost:5173" in origins

    def test_strips_whitespace(self) -> None:
        s = BaseServiceSettings(cors_origins="  https://a.com  , https://b.com  ")
        assert s.cors_origins_list == ["https://a.com", "https://b.com"]

    def test_empty_strings_filtered(self) -> None:
        # Trailing comma must NOT produce empty origins (those would
        # be a CORS allow-empty bug).
        s = BaseServiceSettings(cors_origins="https://a.com,,")
        assert s.cors_origins_list == ["https://a.com"]


class TestGetSettings:
    def test_returns_default_class(self) -> None:
        s = get_settings()
        assert isinstance(s, BaseServiceSettings)

    def test_caches_per_class(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2  # same instance, LRU cache hit

    def test_subclass_isolated(self) -> None:
        # Per-class cache: a subclass and the base class get DIFFERENT
        # cached instances (otherwise an integration test that boots
        # two services in one process would see cross-contamination).
        class IngestionSettings(BaseServiceSettings):
            chunk_size: int = 999

        base = get_settings()
        sub = get_settings(IngestionSettings)
        assert base is not sub
        assert sub.chunk_size == 999
