"""Retrieval service FastAPI application."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from documind_core.cache import Cache
from documind_core.config import get_settings
from documind_core.logging_config import setup_logging
from documind_core.middleware import (
    CorrelationIdMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    TenantContextMiddleware,
    register_exception_handlers,
)
from documind_core.observability import (
    instrument_fastapi,
    instrument_httpx,
    instrument_redis,
    setup_observability,
)
from documind_core.rate_limiter import RateLimiter
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import RetrievalSettings
from app.routers import router
from app.services import (
    GraphSearcher,
    HybridRetriever,
    OllamaEmbedderClient,
    ReciprocalRankFusion,
    VectorSearcher,
)

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings(RetrievalSettings)
    setup_logging(service_name=settings.service_name, level=settings.log_level, json_format=settings.log_json)
    setup_observability(
        service_name=settings.service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        prometheus_port=settings.prometheus_port,
        environment=settings.env,
    )

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    embedder = OllamaEmbedderClient(
        base_url=settings.ollama_url, model=settings.ollama_embed_model
    )
    vector = VectorSearcher(
        url=settings.qdrant_url,
        collection=settings.qdrant_collection,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
    )
    graph = GraphSearcher(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password.get_secret_value(),
    )
    reranker = ReciprocalRankFusion(k=60)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        instrument_redis()
        instrument_httpx()
        app.state.retriever = HybridRetriever(
            embedder=embedder,
            vector=vector,
            graph=graph,
            reranker=reranker,
            cache=Cache(redis_client, default_ttl=settings.query_cache_ttl),
            vector_top_k=settings.vector_top_k,
            graph_top_k=settings.graph_top_k,
            cache_ttl=settings.query_cache_ttl,
        )
        log.info("retrieval_service_ready")
        try:
            yield
        finally:
            await embedder.aclose()
            await vector.aclose()
            await graph.aclose()
            await redis_client.close()

    app = FastAPI(title="DocuMind — Retrieval Service", version="0.1.0", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(redis_client),
        default_limit_per_min=settings.rate_limit_api_per_min,
    )
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    instrument_fastapi(app)
    app.include_router(router)
    return app


app = create_app()
