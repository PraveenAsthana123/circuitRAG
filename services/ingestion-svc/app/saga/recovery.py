"""
Saga crash recovery (Design Areas 18, 19).

When the ingestion service crashes mid-saga, rows in `ingestion.sagas`
are left in state='running'. A plain process restart would do nothing
about them — the orphan vectors / chunks / graph nodes written by earlier
steps would persist forever.

This module scans for stale sagas on startup and:

1. If age < max_run_age → leave alone (still in-flight in another pod).
2. If age >= max_run_age → mark 'failed' and run compensations in reverse.

Wired as a startup task in :mod:`app.main` lifespan.

Important: this runs CONCURRENTLY with live traffic. It must not compensate
a saga that's genuinely still in-flight elsewhere. We pessimistic-lock the
candidate row with a PostgreSQL advisory lock per saga_id — only one pod
will run compensations; others skip.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from documind_core.db_client import DbClient

log = logging.getLogger(__name__)


class SagaRecoveryWorker:
    def __init__(
        self,
        *,
        db: DbClient,
        max_run_age: timedelta = timedelta(minutes=15),
        chunk_repo: Any = None,
        qdrant_repo: Any = None,
        neo4j_repo: Any = None,
        blob_service: Any = None,
    ) -> None:
        self._db = db
        self._max_age = max_run_age
        # When provided, recovery runs REAL per-step compensations. When
        # None (e.g. in unit tests or migration contexts), we fall back
        # to the minimal "mark failed" path. Production wiring passes all.
        self._chunk_repo = chunk_repo
        self._qdrant_repo = qdrant_repo
        self._neo4j_repo = neo4j_repo
        self._blob_service = blob_service

    async def run_once(self) -> int:
        """Find + compensate all stale running sagas. Returns count compensated."""
        cutoff = datetime.now(timezone.utc) - self._max_age
        recovered = 0
        async with self._db.admin_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, tenant_id, saga_type, subject_id, state_data, completed_steps
                FROM ingestion.sagas
                WHERE state = 'running' AND updated_at < $1
                ORDER BY updated_at ASC
                LIMIT 100
                """,
                cutoff,
            )
            for row in rows:
                # Advisory lock on the saga id — if another pod has it, skip.
                locked = await conn.fetchval(
                    "SELECT pg_try_advisory_lock(hashtext($1))", str(row["id"])
                )
                if not locked:
                    log.debug("saga_recovery_skip_locked id=%s", row["id"])
                    continue
                try:
                    await self._compensate(conn, row)
                    recovered += 1
                finally:
                    await conn.execute(
                        "SELECT pg_advisory_unlock(hashtext($1))", str(row["id"])
                    )
        log.info("saga_recovery_complete recovered=%d age_threshold=%s", recovered, self._max_age)
        return recovered

    async def _compensate(self, conn, row) -> None:  # noqa: ANN001
        """Real per-step compensations in reverse order of completion.

        Step numbering matches DocumentIngestionSaga:
          5 = INDEX, 4 = GRAPH, 3 = EMBED, 2 = CHUNK, 1 = PARSE.

        We run compensations for steps <= completed_steps in REVERSE order.
        Any single compensation error is logged but does NOT block the
        rest — the goal is to drain the recovery queue as fully as
        possible; fully-stuck sagas stay in 'failed' with a composite
        error message for operators.
        """
        saga_id = row["id"]
        tenant_id = str(row["tenant_id"])
        document_id: UUID = row["subject_id"]
        completed: int = row["completed_steps"]
        errors: list[str] = []

        log.warning(
            "saga_recovery_compensating id=%s subject=%s completed=%d",
            saga_id, document_id, completed,
        )

        if completed >= 5 and self._qdrant_repo is not None:
            try:
                await self._qdrant_repo.delete_document(
                    tenant_id=tenant_id, document_id=document_id,
                )
            except Exception as e:  # noqa: BLE001
                errors.append(f"qdrant:{type(e).__name__}")

        if completed >= 4 and self._neo4j_repo is not None:
            try:
                await self._neo4j_repo.delete_document(
                    tenant_id=tenant_id, document_id=document_id,
                )
            except Exception as e:  # noqa: BLE001
                errors.append(f"neo4j:{type(e).__name__}")

        if completed >= 2 and self._chunk_repo is not None:
            try:
                await self._chunk_repo.delete_by_document(
                    tenant_id=tenant_id, document_id=document_id,
                )
            except Exception as e:  # noqa: BLE001
                errors.append(f"chunks:{type(e).__name__}")

        if completed >= 1 and self._blob_service is not None:
            try:
                doc = await conn.fetchrow(
                    "SELECT blob_uri FROM ingestion.documents WHERE id = $1",
                    document_id,
                )
                if doc and doc["blob_uri"]:
                    self._blob_service.delete(uri=doc["blob_uri"])
            except Exception as e:  # noqa: BLE001
                errors.append(f"blob:{type(e).__name__}")

        err_msg = (
            "recovered_by_startup_worker"
            + (f"; compensation_errors={'|'.join(errors)}" if errors else "")
        )[:2000]

        await conn.execute(
            """
            UPDATE ingestion.sagas
            SET state = 'failed', error = $1, updated_at = NOW()
            WHERE id = $2 AND state = 'running'
            """,
            err_msg, saga_id,
        )
        await conn.execute(
            """
            UPDATE ingestion.documents
            SET state = 'failed',
                error_reason = 'saga_recovery: service crash mid-flight',
                updated_at = NOW()
            WHERE id = $1 AND state NOT IN ('active', 'archived')
            """,
            document_id,
        )
