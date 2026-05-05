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

from documind_core.breakers import RetrievalCircuitBreaker
from documind_core.cache import Cache
from documind_core.circuit_breaker import CircuitBreaker

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
        vector_breaker: CircuitBreaker | None = None,
        graph_breaker: CircuitBreaker | None = None,
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
        # Transport-level breakers — guard the actual HTTP/Bolt calls
        # to Qdrant and Neo4j. The quality breaker checks RESULT QUALITY
        # (top_score, n_results); these check RAW EXCEPTIONS (Connect
        # errors, timeouts, 5xx). Both layers matter:
        #   * Quality breaker catches "service is up but corpus is empty"
        #   * Transport breaker catches "service is unreachable" and
        #     fast-rejects after N failures so a 30-min Qdrant outage
        #     doesn't cost every retrieval ~5s of timeout each.
        # Failure during call_async is re-raised, which the
        # ``asyncio.gather(return_exceptions=True)`` in ``retrieve``
        # converts into the existing degraded path. No new error path
        # to wire — the breaker just changes the SHAPE of failure
        # (fast CircuitOpenError vs slow ConnectError/ReadTimeout).
        self._vector_breaker = vector_breaker or CircuitBreaker(
            "retrieval-vector-transport",
            failure_threshold=3,
            recovery_timeout=30.0,
        )
        self._graph_breaker = graph_breaker or CircuitBreaker(
            "retrieval-graph-transport",
            failure_threshold=3,
            recovery_timeout=30.0,
        )

    @staticmethod
    def _cache_key(tenant_id: str, req: RetrieveRequest) -> str:
        h = hashlib.sha256(f"{req.strategy}|{req.top_k}|{req.query}|{sorted(req.filters.items())}".encode()).hexdigest()
        return Cache.tenant_key(tenant_id, "retr", h)

    async def retrieve(self, *, tenant_id: str, request: RetrieveRequest) -> RetrieveResponse:
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

        fused = fused[: request.top_k]
        chunks = [RetrievedChunk(**h) for h in fused]

        # Per docs/architecture/rag-deep-test-2026-05-04.md — empirical
        # RAG test surfaced that retrieval returns top-K even with
        # zero-match corpus (Q1 "Half-Life 2" returned 5 unrelated
        # chunks). Hard floor on similarity score: chunks below
        # request.min_score are rejected. Default 0.0 preserves
        # legacy behavior; callers explicitly pass min_score>0 to
        # enforce quality.
        if request.min_score > 0.0:
            n_before = len(chunks)
            chunks = [c for c in chunks if c.score >= request.min_score]
            n_after = len(chunks)
            if n_after < n_before:
                log.info(
                    "min_score_filter dropped=%d kept=%d threshold=%.3f",
                    n_before - n_after, n_after, request.min_score,
                )

        # Stage-3 BGE rerank wiring (per CLAUDE.md §56 + §49):
        # When BGE_RERANKER_IN_HOT_PATH=1 AND BGE_RERANKER_ENABLED=1
        # AND NATIVE_COMPUTE_WRAPPER_ENABLED=1, fire the protected
        # cross-encoder reranker AFTER min_score floor. Default off:
        # legacy callers see no behavior change. The wrapper handles
        # timeout (1500ms) + circuit-breaker + RRF-order fallback.
        # Per docs/architecture/llvm-mlir-circuit-breaker-2026-05-04.md
        # — shield-around-blade composition.
        import os  # noqa: PLC0415
        if os.getenv("BGE_RERANKER_IN_HOT_PATH", "").strip() == "1":
            try:
                from app.services.bge_reranker_protected import (  # noqa: PLC0415
                    protected_rerank, is_available as _bge_avail,
                )
                if _bge_avail() and chunks:
                    chunks_dicts = [c.model_dump() for c in chunks]
                    reranked = protected_rerank(
                        request.query, chunks_dicts,
                        top_k=request.top_k,
                    )
                    # Keep only RetrievedChunk-compatible fields when
                    # rebuilding (drop the bge_score keyword which is
                    # additive; preserve via metadata if needed).
                    rebuilt = []
                    for d in reranked:
                        bge_score = d.pop("bge_score", None)
                        if bge_score is not None:
                            d.setdefault("metadata", {})["bge_score"] = bge_score
                        rebuilt.append(RetrievedChunk(**d))
                    log.info(
                        "bge_rerank_in_hot_path before=%d after=%d",
                        len(chunks), len(rebuilt),
                    )
                    chunks = rebuilt
            except Exception as exc:
                # Fail-safe: never break the request path on rerank
                # error — log + return original chunks. This is the
                # reliability shield around the optimization plane.
                log.warning("bge_rerank_in_hot_path skipped: %s", exc)

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

        # Cache — BUT ONLY on non-degraded results. If every backend failed
        # (len(ranked_lists) == 0) OR we got zero chunks back, skip the cache
        # so a transient dependency outage doesn't poison retrieval for
        # cache_ttl seconds. Found live via Phase-7 chaos drill on 2026-04-24.
        backend_failed = len(ranked_lists) < len(coros)
        if chunks and not backend_failed:
            await self._cache.set_json(
                key,
                {
                    "chunks": [c.model_dump(mode="json") for c in chunks],
                    "strategy": request.strategy,
                },
                ttl=self._cache_ttl,
            )
        else:
            log.info(
                "retrieval_skip_cache chunks=%d backends_ok=%d/%d reason=degraded",
                len(chunks),
                len(ranked_lists),
                len(coros),
            )

        log.info(
            "retrieval_complete tenant=%s strategy=%s n=%d latency_ms=%.1f top_score=%.3f breaker=%s degraded=%s",
            tenant_id,
            request.strategy,
            len(chunks),
            latency_ms,
            top_score,
            self._quality_breaker.state.value,
            backend_failed,
        )
        return RetrieveResponse(
            chunks=chunks,
            latency_ms=latency_ms,
            strategy=request.strategy,
            cached=False,
            # Surface the same signal the cache-skip uses internally —
            # callers need it for the same reason: "this result is
            # built from a subset of the requested backends." Without
            # this, the agent path silently downstreams partial RAG
            # context as if it were complete.
            degraded=backend_failed,
        )

    async def _do_vector(self, tenant_id: str, req: RetrieveRequest) -> list[dict]:
        # Embedding is intentionally OUTSIDE the vector breaker —
        # an Ollama outage is a separate failure mode (the embedder
        # has its own breaker). The vector breaker only protects
        # the Qdrant transport.
        qv = await self._embedder.embed_query(req.query)

        async def _call() -> list[dict]:
            return await self._vector.search(
                tenant_id=tenant_id,
                query_vector=qv,
                top_k=self._vector_top_k,
            )

        return await self._vector_breaker.call_async(_call)

    async def _do_graph(self, tenant_id: str, req: RetrieveRequest) -> list[dict]:
        async def _call() -> list[dict]:
            return await self._graph.search(
                tenant_id=tenant_id,
                query=req.query,
                top_k=self._graph_top_k,
            )

        return await self._graph_breaker.call_async(_call)
