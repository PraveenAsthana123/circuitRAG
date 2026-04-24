"""
Saga persistence (Design Area 18 — Workflow Orchestration).

Stores the progress of a multi-step ingestion pipeline so that if the
service crashes mid-flight, we can resume from the last completed step or
run compensations in reverse.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID, uuid4

from documind_core.db_client import Repository
from documind_core.exceptions import NotFoundError

log = logging.getLogger(__name__)


class SagaRepo(Repository):
    async def create(
        self,
        *,
        tenant_id: str,
        saga_type: str,
        subject_id: UUID,
        total_steps: int,
    ) -> dict[str, Any]:
        saga_id = uuid4()
        async with self._db.tenant_connection(tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO ingestion.sagas
                    (id, tenant_id, saga_type, subject_id, total_steps,
                     completed_steps, state, state_data)
                VALUES ($1, $2::uuid, $3, $4, $5, 0, 'running', '{}'::jsonb)
                RETURNING *
                """,
                saga_id, tenant_id, saga_type, subject_id, total_steps,
            )
        log.info("saga_created id=%s type=%s subject=%s", saga_id, saga_type, subject_id)
        return dict(row)

    async def record_step(
        self,
        *,
        tenant_id: str,
        saga_id: UUID,
        step_name: str,
        result: dict[str, Any],
    ) -> None:
        async with self._db.tenant_connection(tenant_id) as conn:
            await conn.execute(
                """
                UPDATE ingestion.sagas
                SET completed_steps = completed_steps + 1,
                    state_data = state_data || jsonb_build_object($1::text, $2::jsonb),
                    updated_at = NOW()
                WHERE id = $3
                """,
                step_name, json.dumps(result), saga_id,
            )

    async def mark_complete(self, *, tenant_id: str, saga_id: UUID) -> None:
        async with self._db.tenant_connection(tenant_id) as conn:
            await conn.execute(
                "UPDATE ingestion.sagas SET state = 'completed', updated_at = NOW() WHERE id = $1",
                saga_id,
            )

    async def mark_failed(
        self,
        *,
        tenant_id: str,
        saga_id: UUID,
        failing_step: str,
        error: str,
    ) -> None:
        async with self._db.tenant_connection(tenant_id) as conn:
            await conn.execute(
                """
                UPDATE ingestion.sagas
                SET state = 'failed', failing_step = $1, error = $2, updated_at = NOW()
                WHERE id = $3
                """,
                failing_step, error, saga_id,
            )

    async def mark_compensated(self, *, tenant_id: str, saga_id: UUID) -> None:
        async with self._db.tenant_connection(tenant_id) as conn:
            await conn.execute(
                "UPDATE ingestion.sagas SET state = 'compensated', updated_at = NOW() WHERE id = $1",
                saga_id,
            )

    async def get(self, *, tenant_id: str, saga_id: UUID) -> dict[str, Any]:
        async with self._db.tenant_connection(tenant_id) as conn:
            row = await conn.fetchrow("SELECT * FROM ingestion.sagas WHERE id = $1", saga_id)
        if row is None:
            raise NotFoundError(f"Saga {saga_id} not found")
        return dict(row)
