"""PostgresIdempotencyStore — multi-pod-safe IdempotencyStore.

Closes P0 #34 from idempotency.md per-tool review:

    Pre-fix: InMemoryIdempotencyStore loses data on restart; multi-pod
    unsafe (different pods see different idempotency state).
    Fix: Postgres-backed implementation backed by migration 014's
    orchestration.idempotency_keys table. Composite PK (tenant_id, key)
    + RLS policy already drilled by C2 + C3.

Wire from service.py with a DbClient:

    store = PostgresIdempotencyStore(db_client)
    record = await lookup_or_reserve(store=store, ...)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .idempotency import IdempotencyRecord

if TYPE_CHECKING:
    from documind_core.db_client import DbClient

log = logging.getLogger("orchestrator.idempotency_postgres")


class PostgresIdempotencyStore:
    """Postgres-backed IdempotencyStore. Implements the IdempotencyStore
    Protocol from app/idempotency.py. Reads/writes orchestration.idempotency_keys
    via DbClient.tenant_connection (RLS-enforced)."""

    def __init__(self, db: DbClient) -> None:
        self._db = db

    async def get(self, tenant_id: str, key: str) -> IdempotencyRecord | None:
        async with self._db.tenant_connection(tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT tenant_id, key, task_id, body_hash
                FROM orchestration.idempotency_keys
                WHERE tenant_id = $1 AND key = $2
                """,
                tenant_id, key,
            )
        if row is None:
            return None
        return IdempotencyRecord(
            tenant_id=row["tenant_id"],
            key=row["key"],
            task_id=row["task_id"],
            body_hash=row["body_hash"],
        )

    async def save(self, record: IdempotencyRecord) -> None:
        # ON CONFLICT DO NOTHING: the lookup_or_reserve helper guarantees
        # we only call save() AFTER a successful lookup miss + task creation.
        # Concurrent inserts of the same (tenant_id, key) are NOT a bug —
        # the second writer's body_hash will already match (idempotency
        # contract); the conflict resolution is "first writer wins."
        async with self._db.tenant_connection(record.tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO orchestration.idempotency_keys
                    (tenant_id, key, task_id, body_hash)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (tenant_id, key) DO NOTHING
                """,
                record.tenant_id, record.key, record.task_id, record.body_hash,
            )
