"""
Ingestion-service FastAPI application.

This module wires every component together. Read top-to-bottom to understand
the service's dependency graph.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from documind_core.body_limit import BodyLimitMiddleware
from documind_core.cache import Cache
from documind_core.config import get_settings
from documind_core.db_client import DbClient
from documind_core.idempotency import IdempotencyStore
from documind_core.idempotency_middleware import IdempotencyMiddleware
from documind_core.logging_config import setup_logging
from documind_core.middleware import (
    CorrelationIdMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    TenantContextMiddleware,
    register_exception_handlers,
)
from documind_core.observability import (
    instrument_asyncpg,
    instrument_fastapi,
    instrument_httpx,
    instrument_redis,
    setup_observability,
)
from documind_core.rate_limiter import RateLimiter

from app.chunking import RecursiveChunker
from app.core.config import IngestionSettings
from app.embedding import OllamaEmbedder
from app.parsers import ParserRegistry
from app.repositories import ChunkRepo, DocumentRepo, Neo4jRepo, QdrantRepo, SagaRepo
from app.routers import documents_router, health_router
from app.saga import SagaRecoveryWorker
from app.services import BlobService, IngestionService

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Application factory. Called by uvicorn (``app.main:app``)."""
    settings = get_settings(IngestionSettings)
    setup_logging(
        service_name=settings.service_name,
        level=settings.log_level,
        json_format=settings.log_json,
    )
    setup_observability(
        service_name=settings.service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        prometheus_port=settings.prometheus_port,
        environment=settings.env,
    )

    # ----- Clients ---------------------------------------------------------
    db = DbClient(
        dsn=settings.postgres_dsn,
        min_size=settings.pg_min_conns,
        max_size=settings.pg_max_conns,
    )
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    embedder = OllamaEmbedder(
        base_url=settings.ollama_url,
        model=settings.ollama_embed_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    qdrant_repo = QdrantRepo(
        url=settings.qdrant_url,
        collection=settings.qdrant_collection,
        dimension=embedder.dimension,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
    )
    neo4j_repo = Neo4jRepo(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password.get_secret_value(),
    )
    blob_service = BlobService(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key.get_secret_value(),
        secret_key=settings.minio_secret_key.get_secret_value(),
        bucket=settings.minio_bucket,
        use_ssl=settings.minio_use_ssl,
    )

    # ----- Repos + service -------------------------------------------------
    document_repo = DocumentRepo(db)
    chunk_repo = ChunkRepo(db)
    saga_repo = SagaRepo(db)

    ingestion_service = IngestionService(
        settings=settings,
        parsers=ParserRegistry(),
        chunker=RecursiveChunker(
            target_tokens=settings.chunk_target_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        ),
        embedder=embedder,
        document_repo=document_repo,
        chunk_repo=chunk_repo,
        saga_repo=saga_repo,
        qdrant_repo=qdrant_repo,
        neo4j_repo=neo4j_repo,
        blob_service=blob_service,
    )

    # ----- Lifespan --------------------------------------------------------
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await db.connect()
        instrument_asyncpg()
        instrument_redis()
        instrument_httpx()
        await qdrant_repo.ensure_collection()
        await neo4j_repo.ensure_constraints()

        # Crash-recovery: compensate stale sagas from a previous run before
        # accepting any new traffic. Runs once at startup; non-fatal on error.
        try:
            recovery = SagaRecoveryWorker(db=db)
            n = await recovery.run_once()
            if n:
                log.warning("saga_recovery recovered=%d", n)
        except Exception:
            log.exception("saga_recovery_failed")

        app.state.ingestion_service = ingestion_service
        log.info("ingestion_service_ready model=%s dim=%d", embedder.model_name, embedder.dimension)
        try:
            yield
        finally:
            await db.close()
            await embedder.aclose()
            await qdrant_repo.aclose()
            await neo4j_repo.aclose()
            await redis_client.close()

    app = FastAPI(
        title="DocuMind — Ingestion Service",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ----- Middleware (LIFO — last added runs first) ----------------------
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Idempotency guard on write routes — duplicate X-Idempotency-Key
    # returns the cached response. No-op on GETs.
    app.add_middleware(
        IdempotencyMiddleware,
        store=IdempotencyStore(redis_client, ttl_seconds=86400),
    )

    # Body-size cap: 1MB default, 50MB on /upload.
    app.add_middleware(
        BodyLimitMiddleware,
        max_bytes=1 * 1024 * 1024,
        path_overrides={"/api/v1/documents/upload": settings.max_upload_mb * 1024 * 1024},
    )

    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(redis_client),
        default_limit_per_min=settings.rate_limit_api_per_min,
        admin_limit_per_min=settings.rate_limit_admin_per_min,
        upload_limit_per_min=settings.rate_limit_upload_per_min,
    )
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "X-RateLimit-Remaining"],
    )
    app.add_middleware(CorrelationIdMiddleware)

    register_exception_handlers(app)
    instrument_fastapi(app)

    # ----- Routers ---------------------------------------------------------
    app.include_router(health_router)
    app.include_router(documents_router)

    return app


app = create_app()
