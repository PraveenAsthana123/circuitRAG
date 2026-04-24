"""
Transactional outbox (Design Area 17).

Saga steps call `OutboxRepo.enqueue` inside the same asyncpg transaction as
their domain write. A separate `OutboxDrainWorker` reads unpublished rows
and publishes them to Kafka via `EventProducer`. Published rows are marked;
a retention cron deletes old rows after 7 days.

Guarantees:
* **Atomic with domain write** — if the saga transaction commits, the
  outbox row is there. If it rolls back, the event is gone. No more
  "wrote to DB, crashed, never published".
* **At-least-once publish** — the drain worker retries on Kafka failure;
  Kafka consumers must be idempotent (we already are via dedup).
* **Ordered per subject** — drain pulls oldest-first and respects the
  `subject` field; Kafka partitioning key preserves per-document order.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid as uuidlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
from documind_core.kafka_client import EventProducer

log = logging.getLogger(__name__)


class OutboxRepo:
    """
    Enqueue into the outbox.

    **Atomicity contract.** ``enqueue`` accepts a caller-supplied
    ``asyncpg.Connection`` that the caller ALREADY has under a
    transaction. The INSERT runs on that connection, so it commits with
    the caller's own commit — the outbox row and the domain row live or
    die together. Nothing in this module opens its own connection.

    If the caller hasn't started a transaction yet, they should call this
    from inside ``conn.transaction():`` or (easier) from inside
    ``DbClient.tenant_connection``'s implicit txn.
    """

    @staticmethod
    async def enqueue(
        conn: asyncpg.Connection,
        *,
        tenant_id: str,
        topic: str,
        event_type: str,
        subject: str | None,
        correlation_id: str,
        payload: dict[str, Any],
    ) -> UUID:
        event_id = uuidlib.uuid4()
        await conn.execute(
            """
            INSERT INTO ingestion.outbox
                (tenant_id, topic, event_id, event_type, subject,
                 correlation_id, payload)
            VALUES ($1::uuid, $2, $3, $4, $5, NULLIF($6, '')::uuid, $7::jsonb)
            """,
            tenant_id, topic, event_id, event_type, subject,
            correlation_id, json.dumps(payload, default=str),
        )
        return event_id


class OutboxDrainWorker:
    """
    Background worker that reads unpublished outbox rows and publishes to
    Kafka. Runs as an asyncio task started in the ingestion-svc lifespan.

    Graceful shutdown: `stop()` sets the flag; the loop exits on the next
    iteration without losing rows (drain-on-shutdown would be nicer but
    Kafka retries cover this — drained rows are just "delayed, not lost").
    """

    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        producer: EventProducer,
        poll_interval_s: float = 1.0,
        batch_size: int = 100,
    ) -> None:
        self._pool = pool
        self._producer = producer
        self._poll = poll_interval_s
        self._batch = batch_size
        self._stopping = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._loop())
        log.info("outbox_drain_started interval_s=%.1f batch=%d", self._poll, self._batch)

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        log.info("outbox_drain_stopped")

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                n = await self._drain_once()
                if n == 0:
                    await asyncio.sleep(self._poll)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("outbox_drain_loop_error")
                await asyncio.sleep(self._poll * 5)

    async def _drain_once(self) -> int:
        async with self._pool.acquire() as conn:
            # SELECT FOR UPDATE SKIP LOCKED so multiple pods don't double-
            # publish. Each worker takes its own chunk.
            rows = await conn.fetch(
                """
                SELECT id, tenant_id, topic, event_id, event_type, subject,
                       correlation_id, payload, attempts
                FROM ingestion.outbox
                WHERE published_at IS NULL
                ORDER BY created_at ASC
                LIMIT $1
                FOR UPDATE SKIP LOCKED
                """,
                self._batch,
            )
            if not rows:
                return 0

            for row in rows:
                try:
                    await self._producer.publish(
                        topic=row["topic"],
                        type=row["event_type"],
                        data=json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"],
                        tenant_id=str(row["tenant_id"]),
                        correlation_id=str(row["correlation_id"] or ""),
                        subject=row["subject"] or None,
                        key=row["subject"] or str(row["tenant_id"]),
                    )
                    await conn.execute(
                        "UPDATE ingestion.outbox "
                        "SET published_at = $1, attempts = attempts + 1 "
                        "WHERE id = $2",
                        datetime.now(UTC), row["id"],
                    )
                except Exception as exc:  # noqa: BLE001
                    await conn.execute(
                        "UPDATE ingestion.outbox "
                        "SET attempts = attempts + 1, last_error = $1 "
                        "WHERE id = $2",
                        f"{type(exc).__name__}: {exc}"[:500], row["id"],
                    )
                    log.warning(
                        "outbox_publish_failed id=%s attempts=%d err=%s",
                        row["id"], row["attempts"] + 1, exc,
                    )
            return len(rows)
