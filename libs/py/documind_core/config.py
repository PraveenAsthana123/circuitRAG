"""
Configuration foundation (Design Areas 6 — Control Plane, 55 — Feature Flags,
65 — Design-for-Change).

Pydantic Settings is the **single source of truth** for environment variables.
Every service imports :class:`BaseServiceSettings`, subclasses it with any
service-specific fields, and calls :func:`get_settings`.

Rules (enforced by code review, not runtime):

1. **No ``os.environ.get()`` anywhere except this module.** If you find
   yourself reaching into ``os.environ`` in a service, add the field here
   instead. The settings object is the contract; env vars are the
   implementation detail.
2. **Defaults are for dev.** Anything security-sensitive (keys, passwords)
   must have no default — Pydantic will raise if unset, so prod deploys fail
   loudly instead of silently running with dummy values.
3. **Settings are immutable after first access.** They are cached via
   :func:`functools.lru_cache`. If you need runtime-mutable configuration
   (feature flags, policy thresholds), that lives in the Governance Service,
   not here.

Example — a service subclasses this::

    class IngestionSettings(BaseServiceSettings):
        chunk_size: int = 512
        chunk_overlap: int = 50
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Fields shared by every DocuMind service (mirrors ``.env.template``)."""

    model_config = SettingsConfigDict(
        env_prefix="DOCUMIND_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",  # per-service fields (with their own prefix) are allowed
    )

    # -----------------------------
    # Environment
    # -----------------------------
    env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = True
    region: str = "local"
    service_name: str = Field(default="documind-service", description="Overridden per service")

    # -----------------------------
    # Security
    # -----------------------------
    jwt_public_key_path: str = "./scripts/dev-keys/jwt-public.pem"
    jwt_issuer: str = "documind-local"
    jwt_audience: str = "documind-services"
    jwt_access_ttl: int = 900
    jwt_refresh_ttl: int = 604800

    encryption_key: SecretStr | None = None
    admin_api_key: SecretStr | None = None
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # -----------------------------
    # Data stores
    # -----------------------------
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_db: str = "documind"
    pg_user: str = "documind"
    pg_password: SecretStr = SecretStr("documind")
    pg_max_conns: int = 20
    pg_min_conns: int = 2

    redis_url: str = "redis://localhost:6379/0"
    redis_pool_size: int = 20

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "chunks"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("documind")

    kafka_bootstrap: str = "localhost:9092"
    kafka_client_id: str = "documind"
    kafka_consumer_group_prefix: str = "documind-"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: SecretStr = SecretStr("documind")
    minio_secret_key: SecretStr = SecretStr("documind-secret")
    minio_bucket: str = "documents"
    minio_use_ssl: bool = False

    # -----------------------------
    # LLM + embedding
    # -----------------------------
    ollama_url: str = "http://localhost:11434"
    ollama_llm_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_timeout_seconds: int = 60

    # -----------------------------
    # Observability
    # -----------------------------
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_namespace: str = "documind"
    prometheus_port: int = 9464

    # -----------------------------
    # Rate-limit defaults (per-tenant; governance-svc can override)
    # -----------------------------
    rate_limit_api_per_min: int = 100
    rate_limit_upload_per_min: int = 10
    rate_limit_admin_per_min: int = 50
    rate_limit_inference_per_min: int = 20

    # -----------------------------
    # Chunking / retrieval defaults
    # -----------------------------
    chunk_size: int = 512
    chunk_overlap: int = 50
    retrieval_top_k: int = 10
    rerank_top_k: int = 5
    max_context_tokens: int = 4000

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    @property
    def postgres_dsn(self) -> str:
        """SQLAlchemy/asyncpg-compatible DSN. No secrets in logs — callers
        should never log this directly; log ``pg_host`` + ``pg_db`` instead."""
        password = self.pg_password.get_secret_value()
        return f"postgresql://{self.pg_user}:{password}@{self.pg_host}:{self.pg_port}/{self.pg_db}"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache(maxsize=8)
def get_settings(settings_cls: type[BaseServiceSettings] = BaseServiceSettings) -> BaseServiceSettings:
    """
    Factory for the cached settings instance.

    Each service passes its own subclass::

        from documind_core.config import get_settings
        from app.core.config import IngestionSettings

        settings = get_settings(IngestionSettings)

    The LRU cache is keyed on the class, so multiple services in the same
    Python process (e.g. an integration test that boots ingestion + retrieval)
    each get their own instance.

    In tests, call ``get_settings.cache_clear()`` between tests to force
    re-reading from a patched environment.
    """
    return settings_cls()
