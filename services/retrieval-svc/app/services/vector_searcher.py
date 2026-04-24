"""
Vector search over Qdrant (Design Area 47).

Tenant isolation: every query includes ``must_filter`` on ``tenant_id`` — the
vector DB will NOT return cross-tenant hits even if a bug in calling code
forgets to filter. This is defense-in-depth.
"""
from __future__ import annotations

import logging
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

log = logging.getLogger(__name__)


class VectorSearcher:
    def __init__(self, *, url: str, collection: str, api_key: str | None = None) -> None:
        self._client = AsyncQdrantClient(url=url, api_key=api_key)
        self._collection = collection

    async def search(
        self,
        *,
        tenant_id: str,
        query_vector: list[float],
        top_k: int,
        extra_filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        conditions = [FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        for k, v in (extra_filters or {}).items():
            conditions.append(FieldCondition(key=k, match=MatchValue(value=v)))

        # Qdrant client ≥ 1.12 removed `.search()` in favor of `.query_points()`.
        # `response.points` contains the hits (same shape as the old ScoredPoint list).
        response = await self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            query_filter=Filter(must=conditions),
            limit=top_k,
            with_payload=True,
        )
        hits: list[dict[str, Any]] = []
        for r in response.points:
            payload = r.payload or {}
            hits.append({
                "chunk_id": payload.get("chunk_id"),
                "document_id": payload.get("document_id"),
                "text": payload.get("text", ""),
                "page_number": payload.get("page", 0),
                "score": float(r.score),
                "source": "vector",
            })
        log.info("vector_search tenant=%s top_k=%d hits=%d", tenant_id, top_k, len(hits))
        return hits

    async def aclose(self) -> None:
        await self._client.close()
