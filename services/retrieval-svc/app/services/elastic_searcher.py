"""
Vectorless retrieval over Elasticsearch (BM25 keyword search).

PLANNED feature surface — Phase 1 retrieves only via Qdrant (vector)
and Neo4j (graph). This module exists as the wrapper contract for
when the operator wires ES indexing of documents. Until that lands,
search() will return [] against any query because no documents are
indexed.

Tenant isolation: every query includes a `term` filter on
`tenant_id` so cross-tenant hits are impossible even if calling
code forgets to filter. Defense in depth, mirrors VectorSearcher.

Locked by mcp/tests/drill_elastic_searcher_skeleton.py.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class ElasticSearcher:
    """BM25 keyword search wrapper. Returns empty list until an
    indexing pipeline populates the configured index.

    Usage:
        es = ElasticSearcher(url="http://elasticsearch:9200",
                             index="documind_documents")
        hits = await es.search(tenant_id="acme",
                               query="how does the auth flow work?",
                               top_k=10)
    """

    def __init__(
        self,
        *,
        url: str,
        index: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._url = url
        self._index = index
        self._username = username
        self._password = password
        self._client = None  # lazy-instantiate; ES dep is optional

    async def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            # Lazy import — elasticsearch client is optional in tests
            # and Phase-1 dev where ES is log-aggregation only.
            from elasticsearch import AsyncElasticsearch  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            log.warning(
                "elasticsearch client not installed; vectorless retrieval disabled. "
                "Install via `pip install elasticsearch>=8.15,<9` if needed.",
            )
            raise RuntimeError("elasticsearch client unavailable") from exc
        kwargs: dict[str, Any] = {"hosts": [self._url]}
        if self._username and self._password:
            kwargs["basic_auth"] = (self._username, self._password)
        self._client = AsyncElasticsearch(**kwargs)
        return self._client

    async def search(
        self,
        *,
        tenant_id: str,
        query: str,
        top_k: int,
        extra_filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """BM25 search. Returns list of hit dicts with chunk_id, score,
        content, source. Empty list when no index / no documents.

        Tenant isolation: enforced via term filter on tenant_id —
        cross-tenant rows are impossible even if extra_filters
        contains a wider tenant_id.
        """
        try:
            client = await self._ensure_client()
        except RuntimeError:
            # ES client not installed — degrade gracefully to empty.
            return []

        bool_query: dict[str, Any] = {
            "must": [{"match": {"content": query}}],
            "filter": [{"term": {"tenant_id": tenant_id}}],
        }
        if extra_filters:
            for key, val in extra_filters.items():
                bool_query["filter"].append({"term": {key: val}})

        try:
            resp = await client.search(
                index=self._index,
                query={"bool": bool_query},
                size=top_k,
            )
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            log.warning(
                "elastic_search_failed index=%s tenant=%s err=%s",
                self._index, tenant_id, exc,
            )
            return []

        hits = []
        for h in resp.get("hits", {}).get("hits", []):
            src = h.get("_source", {})
            hits.append(
                {
                    "chunk_id": h.get("_id") or src.get("chunk_id"),
                    "score": h.get("_score", 0.0),
                    "content": src.get("content", ""),
                    "source": src.get("source"),
                    "tenant_id": src.get("tenant_id", tenant_id),
                }
            )
        return hits

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
