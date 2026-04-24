"""
Hybrid retriever (Design Areas 24 — Retrieval, 40 — Cache, 13 — Read Path).

Orchestrates the read-path CQRS:

1. Check Redis cache (namespaced by tenant + query hash).
2. On miss: parallel vector + graph search.
3. Fuse with RRF.
4. Cache the result + return.

Parallel fetch — ``asyncio.gather`` runs the two backends concurrently, so
latency is max(vector, graph), not vector+graph.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time

from documind_core.cache import Cache
from documind_core.breakers import RetrievalCircuitBreaker

from app.schemas import RetrievedChunk, RetrieveRequest, RetrieveResponse

from .embedder_client import OllamaEmbedderClient
from .graph_searcher import GraphSearcher
from .reranker import ReciprocalRankFusion
from .vector_searcher import VectorSearcher

log = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(
        self,
        *,
        embedder: OllamaEmbedderClient,
        vector: VectorSearcher,
        graph: GraphSearcher,
        reranker: ReciprocalRankFusion,
        cache: Cache,
        vector_top_k: int = 20,
        graph_top_k: int = 10,
        cache_ttl: int = 300,
        quality_breaker: RetrievalCircuitBreaker | None = None,
    ) -> None:
        self._embedder = embedder
        self._vector = vector
        self._graph = graph
        self._reranker = reranker
        self._cache = cache
        self._vector_top_k = vector_top_k
        self._graph_top_k = graph_top_k
        self._cache_ttl = cache_ttl
        # Quality-aware breaker: opens when rolling top-score falls below
        # threshold even though the HTTP calls succeeded. Without this, a
        # corpus that has nothing relevant would feed garbage into the LLM.
        self._quality_breaker = quality_breaker or RetrievalCircuitBreaker(
            "retrieval-quality",
            failure_threshold=5,
            recovery_timeout=60.0,
            min_quality=0.35,
            quality_window=20,
        )

    @staticmethod
    def _cache_key(tenant_id: str, req: RetrieveRequest) -> str:
        h = hashlib.sha256(
            f"{req.strategy}|{req.top_k}|{req.query}|{sorted(req.filters.items())}".encode()
        ).hexdigest()
        return Cache.tenant_key(tenant_id, "retr", h)

    async def retrieve(
        self, *, tenant_id: str, request: RetrieveRequest
    ) -> RetrieveResponse:
        start = time.monotonic()
        key = self._cache_key(tenant_id, request)

        cached = await self._cache.get_json(key)
        if cached is not None:
            log.info("retrieval_cache_hit tenant=%s", tenant_id)
            return RetrieveResponse(
                chunks=[RetrievedChunk(**c) for c in cached["chunks"]],
                latency_ms=(time.monotonic() - start) * 1000,
                strategy=cached["strategy"],
                cached=True,
            )

        # Parallel fetch
        coros = []
        if "vector" in request.include_sources:
            coros.append(self._do_vector(tenant_id, request))
        if "graph" in request.include_sources and request.strategy != "vector":
            coros.append(self._do_graph(tenant_id, request))
        results = await asyncio.gather(*coros, return_exceptions=True)

        ranked_lists = []
        for r in results:
            if isinstance(r, Exception):
                log.warning("retrieval_backend_failed err=%s", r)
                continue
            ranked_lists.append(r)

        if request.strategy == "vector" or len(ranked_lists) == 1:
            fused = ranked_lists[0] if ranked_lists else []
        else:
            fused = self._reranker.fuse(*ranked_lists, top_k=request.top_k)

        fused = fused[:request.top_k]
        chunks = [RetrievedChunk(**h) for h in fused]

        latency_ms = (time.monotonic() - start) * 1000

        # Record a quality sample so the breaker can notice a corpus trend.
        # We DO NOT block on the current query — one bad query is fine. The
        # breaker opens only when quality degrades across a rolling window.
        top_score = float(chunks[0].score) if chunks else 0.0
        self._quality_breaker.record_quality(
            top_score=top_score,
            n_results=len(chunks),
            latency_ms=latency_ms,
        )

        # Cache
        await self._cache.set_json(
            key,
            {
                "chunks": [c.model_dump(mode="json") for c in chunks],
                "strategy": request.strategy,
            },
            ttl=self._cache_ttl,
        )

        log.info(
            "retrieval_complete tenant=%s strategy=%s n=%d latency_ms=%.1f top_score=%.3f breaker=%s",
            tenant_id, request.strategy, len(chunks), latency_ms,
            top_score, self._quality_breaker.state.value,
        )
        return RetrieveResponse(
            chunks=chunks,
            latency_ms=latency_ms,
            strategy=request.strategy,
            cached=False,
        )

    async def _do_vector(self, tenant_id: str, req: RetrieveRequest) -> list[dict]:
        qv = await self._embedder.embed_query(req.query)
        return await self._vector.search(
            tenant_id=tenant_id, query_vector=qv, top_k=self._vector_top_k
        )

    async def _do_graph(self, tenant_id: str, req: RetrieveRequest) -> list[dict]:
        return await self._graph.search(
            tenant_id=tenant_id, query=req.query, top_k=self._graph_top_k
        )
