"""
Document metadata repository (Postgres, ingestion schema).

Implements the document state machine from spec Area 9:

    UPLOADED → PARSING → PARSED → CHUNKING → CHUNKED → EMBEDDING →
    EMBEDDED → INDEXING → INDEXED → ACTIVE

State transitions are validated against :attr:`ALLOWED_TRANSITIONS` — any
attempt to go from FAILED → ACTIVE without re-processing is rejected at
the repository layer.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from documind_core.db_client import DbClient, Repository
from documind_core.exceptions import NotFoundError, ValidationError

log = logging.getLogger(__name__)


# State machine (spec Area 9)
STATE_UPLOADED = "uploaded"
STATE_PARSING = "parsing"
STATE_PARSED = "parsed"
STATE_CHUNKING = "chunking"
STATE_CHUNKED = "chunked"
STATE_EMBEDDING = "embedding"
STATE_EMBEDDED = "embedded"
STATE_INDEXING = "indexing"
STATE_INDEXED = "indexed"
STATE_ACTIVE = "active"
STATE_FAILED = "failed"
STATE_ARCHIVED = "archived"

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    STATE_UPLOADED: {STATE_PARSING, STATE_FAILED},
    STATE_PARSING: {STATE_PARSED, STATE_FAILED},
    STATE_PARSED: {STATE_CHUNKING, STATE_FAILED},
    STATE_CHUNKING: {STATE_CHUNKED, STATE_FAILED},
    STATE_CHUNKED: {STATE_EMBEDDING, STATE_FAILED},
    STATE_EMBEDDING: {STATE_EMBEDDED, STATE_FAILED},
    STATE_EMBEDDED: {STATE_INDEXING, STATE_FAILED},
    STATE_INDEXING: {STATE_INDEXED, STATE_FAILED},
    STATE_INDEXED: {STATE_ACTIVE, STATE_FAILED},
    STATE_ACTIVE: {STATE_ARCHIVED, STATE_PARSING},  # re-process
    STATE_FAILED: {STATE_PARSING, STATE_ARCHIVED},  # manual retry
    STATE_ARCHIVED: set(),
}


class DocumentRepo(Repository):
    """Tenant-scoped CRUD on ``ingestion.documents``."""

    async def create(
        self,
        *,
        tenant_id: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        checksum_sha256: str,
        blob_uri: str,
        uploaded_by: UUID | None,
    ) -> dict[str, Any]:
        doc_id = uuid4()
        async with self._db.tenant_connection(tenant_id) as conn:
            record = await conn.fetchrow(
                """
                INSERT INTO ingestion.documents
                    (id, tenant_id, filename, mime_type, size_bytes,
                     checksum_sha256, blob_uri, state, uploaded_by, version)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, 1)
                RETURNING *
                """,
                doc_id, tenant_id, filename, mime_type, size_bytes,
                checksum_sha256, blob_uri, STATE_UPLOADED, uploaded_by,
            )
        log.info("document_created id=%s tenant=%s filename=%s", doc_id, tenant_id, filename)
        return dict(record)

    async def get(self, *, tenant_id: str, document_id: UUID) -> dict[str, Any]:
        async with self._db.tenant_connection(tenant_id) as conn:
            record = await conn.fetchrow(
                "SELECT * FROM ingestion.documents WHERE id = $1", document_id
            )
        if record is None:
            raise NotFoundError(f"Document {document_id} not found")
        return dict(record)

    async def list(
        self,
        *,
        tenant_id: str,
        offset: int = 0,
        limit: int = 50,
        state: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        where = "WHERE TRUE"
        params: list[Any] = []
        if state is not None:
            where += " AND state = $1"
            params.append(state)

        async with self._db.tenant_connection(tenant_id) as conn:
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM ingestion.documents {where}", *params
            )
            rows = await conn.fetch(
                f"""
                SELECT * FROM ingestion.documents {where}
                ORDER BY created_at DESC
                OFFSET ${len(params) + 1} LIMIT ${len(params) + 2}
                """,
                *params, offset, limit,
            )
        return [dict(r) for r in rows], int(total)

    async def transition_state(
        self,
        *,
        tenant_id: str,
        document_id: UUID,
        to_state: str,
        expected_from: str | None = None,
    ) -> dict[str, Any]:
        """Validated state transition with optimistic locking on ``version``."""
        async with self._db.tenant_connection(tenant_id) as conn:
            current = await conn.fetchrow(
                "SELECT state, version FROM ingestion.documents WHERE id = $1",
                document_id,
            )
            if current is None:
                raise NotFoundError(f"Document {document_id} not found")

            from_state = current["state"]
            if expected_from is not None and from_state != expected_from:
                raise ValidationError(
                    f"Expected state '{expected_from}', got '{from_state}'",
                    details={"document_id": str(document_id), "from": from_state},
                )
            allowed = ALLOWED_TRANSITIONS.get(from_state, set())
            if to_state not in allowed:
                raise ValidationError(
                    f"Invalid transition {from_state} → {to_state}",
                    details={"allowed": sorted(allowed)},
                )

            row = await conn.fetchrow(
                """
                UPDATE ingestion.documents
                SET state = $1, version = version + 1, updated_at = NOW()
                WHERE id = $2 AND version = $3
                RETURNING *
                """,
                to_state, document_id, current["version"],
            )
            if row is None:
                raise ValidationError(
                    "Concurrent modification — version mismatch",
                    details={"document_id": str(document_id)},
                )
        log.info(
            "document_state_change id=%s %s -> %s",
            document_id, from_state, to_state,
        )
        return dict(row)

    async def mark_failed(
        self,
        *,
        tenant_id: str,
        document_id: UUID,
        reason: str,
    ) -> None:
        async with self._db.tenant_connection(tenant_id) as conn:
            await conn.execute(
                """
                UPDATE ingestion.documents
                SET state = $1, error_reason = $2, updated_at = NOW()
                WHERE id = $3
                """,
                STATE_FAILED, reason, document_id,
            )
        log.warning("document_marked_failed id=%s reason=%s", document_id, reason)

    async def delete(self, *, tenant_id: str, document_id: UUID) -> None:
        async with self._db.tenant_connection(tenant_id) as conn:
            result = await conn.execute(
                "DELETE FROM ingestion.documents WHERE id = $1", document_id
            )
        if result == "DELETE 0":
            raise NotFoundError(f"Document {document_id} not found")
        log.info("document_deleted id=%s", document_id)

    async def touch(self, *, tenant_id: str, document_id: UUID, updates: dict[str, Any]) -> None:
        """Update non-state fields (page_count, chunk_count, etc.)."""
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
        params = [document_id, *updates.values()]
        async with self._db.tenant_connection(tenant_id) as conn:
            await conn.execute(
                f"UPDATE ingestion.documents SET {set_clause}, updated_at = NOW() WHERE id = $1",
                *params,
            )
