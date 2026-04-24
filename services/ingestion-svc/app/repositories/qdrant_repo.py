"""
Qdrant repository (Design Area 47 — Vector DB Strategy).

Responsibilities:

* Ensure the collection exists with the right dimensionality and HNSW config.
* Upsert vectors with tenant_id + document_id in the payload (for filtering).
* Delete by document_id (saga compensation).

Schema choice: ONE collection shared across tenants, tenant_id as a payload
filter. This scales better than one-collection-per-tenant at high tenant
counts (Qdrant has a per-collection overhead). For very large tenants,
we'd shard them into dedicated collections — that decision lives in
governance, not code.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    HnswConfigDiff,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    VectorParams,
)

log = logging.getLogger(__name__)


class QdrantRepo:
    """Tenant-aware vector index over a single shared collection."""

    def __init__(
        self,
        *,
        url: str,
        collection: str,
        dimension: int,
        api_key: str | None = None,
    ) -> None:
        self._client = AsyncQdrantClient(url=url, api_key=api_key)
        self._collection = collection
        self._dimension = dimension

    @property
    def collection(self) -> str:
        return self._collection

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------
    async def ensure_collection(self) -> None:
        """Idempotent — creates the collection if missing with production-
        grade settings (HNSW + scalar quantization + payload indexes)."""
        existing = await self._client.get_collections()
        if any(c.name == self._collection for c in existing.collections):
            log.info("qdrant_collection_exists name=%s", self._collection)
            return

        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=self._dimension, distance=Distance.COSINE),
            hnsw_config=HnswConfigDiff(m=16, ef_construct=128),
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8, quantile=0.99, always_ram=True
                )
            ),
        )
        # Payload indexes — critical for tenant filter performance
        for field in ("tenant_id", "document_id"):
            await self._client.create_payload_index(
                collection_name=self._collection,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        await self._client.create_payload_index(
            collection_name=self._collection,
            field_name="created_at",
            field_schema=PayloadSchemaType.INTEGER,
        )
        log.info("qdrant_collection_created name=%s dim=%d", self._collection, self._dimension)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    async def upsert_chunks(
        self,
        *,
        tenant_id: str,
        document_id: UUID,
        chunk_ids: list[UUID],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> int:
        if not chunk_ids:
            return 0
        if not (len(chunk_ids) == len(vectors) == len(payloads)):
            raise ValueError("chunk_ids, vectors, payloads must be the same length")

        points = [
            PointStruct(
                id=str(cid),
                vector=vec,
                payload={
                    **payload,
                    "tenant_id": tenant_id,
                    "document_id": str(document_id),
                    "chunk_id": str(cid),
                },
            )
            for cid, vec, payload in zip(chunk_ids, vectors, payloads, strict=True)
        ]
        await self._client.upsert(collection_name=self._collection, points=points)
        log.info("qdrant_upsert document=%s n=%d", document_id, len(points))
        return len(points)

    # ------------------------------------------------------------------
    # Deletes (saga compensation)
    # ------------------------------------------------------------------
    async def delete_document(self, *, tenant_id: str, document_id: UUID) -> int:
        """Delete all vectors belonging to a document. Idempotent."""
        flt = Filter(
            must=[
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                FieldCondition(key="document_id", match=MatchValue(value=str(document_id))),
            ]
        )
        result = await self._client.delete(collection_name=self._collection, points_selector=flt)
        count = result.operation_id if hasattr(result, "operation_id") else 0
        log.info("qdrant_delete document=%s", document_id)
        return count

    async def aclose(self) -> None:
        await self._client.close()
