"""Inference service FastAPI application."""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
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

from app.core.config import InferenceSettings
from app.routers import router
from app.services import (
    GuardrailChecker,
    OllamaClient,
    PromptBuilder,
    RagInferenceService,
    RetrievalClient,
)

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings(InferenceSettings)
    setup_logging(service_name=settings.service_name, level=settings.log_level, json_format=settings.log_json)
    setup_observability(
        service_name=settings.service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        prometheus_port=settings.prometheus_port,
        environment=settings.env,
    )

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    retrieval = RetrievalClient(base_url=settings.retrieval_svc_url)
    ollama = OllamaClient(
        base_url=settings.ollama_url,
        model=settings.ollama_llm_model,
        timeout=settings.ollama_timeout_seconds,
    )
    prompts = PromptBuilder()
    guardrails = GuardrailChecker()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        instrument_redis()
        instrument_httpx()
        app.state.rag_service = RagInferenceService(
            retrieval=retrieval,
            ollama=ollama,
            prompts=prompts,
            guardrails=guardrails,
            default_prompt=settings.prompt_version,
            max_new_tokens=settings.max_new_tokens,
            temperature=settings.temperature,
        )
        # Agent service (RAG + MCP). Configured to skip MCP wiring if the
        # URL is not set — services can run in "answer-only" mode without MCP.
        from app.services.agent import AgentService
        from mcp import MCPClient

        mcp_url = os.getenv("DOCUMIND_MCP_HR_URL", "")
        if mcp_url:
            mcp_client = MCPClient(base_url=mcp_url)
            app.state.mcp_client = mcp_client
            app.state.agent_service = AgentService(
                rag=app.state.rag_service, mcp=mcp_client,
            )
            log.info("agent_service_ready mcp_url=%s", mcp_url)
        else:
            app.state.mcp_client = None
            app.state.agent_service = None
            log.info("agent_service_disabled reason=no_mcp_url")

        log.info("inference_service_ready model=%s", ollama.model)
        try:
            yield
        finally:
            await retrieval.aclose()
            await ollama.aclose()
            if app.state.mcp_client is not None:
                await app.state.mcp_client.close()
            await redis_client.close()

    app = FastAPI(title="DocuMind — Inference Service", version="0.1.0", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(redis_client),
        default_limit_per_min=settings.rate_limit_inference_per_min,
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
