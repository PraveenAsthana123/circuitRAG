"""Chunk metadata repository (Postgres, ingestion schema)."""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from documind_core.db_client import Repository

from app.chunking import Chunk

log = logging.getLogger(__name__)


class ChunkRepo(Repository):
    async def bulk_insert(
        self,
        *,
        tenant_id: str,
        document_id: UUID,
        chunks: list[Chunk],
    ) -> list[dict[str, Any]]:
        if not chunks:
            return []

        records = [
            (
                tenant_id,
                str(document_id),
                c.index,
                c.content_hash,
                c.text,
                c.token_count,
                c.page_number,
                json.dumps(c.metadata),
            )
            for c in chunks
        ]
        async with self._db.tenant_connection(tenant_id) as conn:
            # COPY would be faster but we want RETURNING for the IDs.
            rows = await conn.fetch(
                """
                INSERT INTO ingestion.chunks
                    (tenant_id, document_id, index, content_hash, text,
                     token_count, page_number, metadata)
                SELECT
                    (r->>0)::uuid, (r->>1)::uuid, (r->>2)::int, r->>3,
                    r->>4, (r->>5)::int, (r->>6)::int, (r->>7)::jsonb
                FROM jsonb_array_elements($1::jsonb) AS r
                ON CONFLICT (document_id, index) DO UPDATE
                    SET content_hash = EXCLUDED.content_hash,
                        text = EXCLUDED.text,
                        token_count = EXCLUDED.token_count,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                RETURNING *
                """,
                json.dumps(records),
            )
        log.info("chunks_inserted document=%s n=%d", document_id, len(rows))
        return [dict(r) for r in rows]

    async def list_by_document(
        self, *, tenant_id: str, document_id: UUID
    ) -> list[dict[str, Any]]:
        async with self._db.tenant_connection(tenant_id) as conn:
            rows = await conn.fetch(
                "SELECT * FROM ingestion.chunks WHERE document_id = $1 ORDER BY index",
                document_id,
            )
        return [dict(r) for r in rows]

    async def delete_by_document(
        self, *, tenant_id: str, document_id: UUID
    ) -> int:
        async with self._db.tenant_connection(tenant_id) as conn:
            result = await conn.execute(
                "DELETE FROM ingestion.chunks WHERE document_id = $1", document_id
            )
        # asyncpg returns "DELETE N"
        count = int(result.rsplit(" ", 1)[-1]) if result else 0
        log.info("chunks_deleted document=%s n=%d", document_id, count)
        return count

    async def stamp_embedding_model(
        self,
        *,
        tenant_id: str,
        chunk_ids: list[UUID],
        model: str,
    ) -> None:
        """Mark the given chunks as embedded under ``model``. Called from
        the saga's embed step so the re-embed worker's predicate
        ``metadata->>'embedding_model' <> $current`` correctly skips
        just-embedded chunks. Without this stamp, the re-embed worker
        would re-pick the same chunks on its next poll (Bug #3)."""
        if not chunk_ids:
            return
        async with self._db.tenant_connection(tenant_id) as conn:
            await conn.execute(
                """
                UPDATE ingestion.chunks
                SET metadata = COALESCE(metadata, '{}'::jsonb)
                               || jsonb_build_object(
                                    'embedding_model', $1::text,
                                    'embedding_stamped_at', NOW()::text
                                  ),
                    updated_at = NOW()
                WHERE id = ANY($2::uuid[])
                """,
                model, chunk_ids,
            )
        log.info("chunks_embedding_stamped count=%d model=%s", len(chunk_ids), model)
