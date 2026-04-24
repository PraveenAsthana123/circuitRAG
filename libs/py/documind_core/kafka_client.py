"""
Kafka client (Design Areas 17 — Event-Driven, 19 — Compensation,
20 — Idempotency, 31 — Event Contract, 44 — Queue Strategy).

Provides:

* :class:`EventProducer` — publishes CloudEvents-compliant JSON envelopes.
* :class:`IdempotentConsumer` — base class that dedupes events by ``id``
  via a ``processed_events`` table (see spec §Area 20).

Event envelope matches ``schemas/events/*.json``. Producers are responsible
for validating against the schema BEFORE sending; this catches contract
violations at the source instead of downstream.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .exceptions import ExternalServiceError

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Producer
# ---------------------------------------------------------------------------
class EventProducer:
    """
    CloudEvents-compatible JSON producer.

    Each ``publish`` call attaches standard fields:
    ``id`` (UUID), ``source``, ``type``, ``specversion=1.0``, ``time``,
    ``tenantid``, ``correlationid``. The caller only provides ``data`` plus
    ``type`` + optional ``subject``.

    Delivery guarantees
    -------------------
    * ``acks=all`` — wait for all in-sync replicas.
    * ``enable_idempotence=True`` — no duplicate writes on producer retry.
    * Failed sends raise :class:`ExternalServiceError` after the internal
      retry budget is exhausted. Callers must NOT swallow this — if an
      event fails to publish, the corresponding state change should either
      be rolled back (saga compensation) or queued for later replay
      (outbox pattern). Silent drops cause auditing gaps.
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        client_id: str,
        source: str,
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._client_id = client_id
        self._source = source
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            client_id=self._client_id,
            acks="all",
            enable_idempotence=True,
            compression_type="gzip",
        )
        await self._producer.start()
        log.info("kafka_producer_started bootstrap=%s source=%s", self._bootstrap, self._source)

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(
        self,
        *,
        topic: str,
        type: str,
        data: dict[str, Any],
        tenant_id: str,
        correlation_id: str = "",
        subject: str | None = None,
        key: str | None = None,
    ) -> None:
        """
        Send a single event. Key controls the partition (use ``tenant_id``
        for per-tenant ordering, ``document_id`` for per-document ordering).
        """
        if self._producer is None:
            raise ExternalServiceError("EventProducer.start() has not been called")

        envelope: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "source": self._source,
            "type": type,
            "specversion": "1.0",
            "time": datetime.now(UTC).isoformat(),
            "datacontenttype": "application/json",
            "tenantid": tenant_id,
            "correlationid": correlation_id,
            "data": data,
        }
        if subject is not None:
            envelope["subject"] = subject

        payload = json.dumps(envelope, separators=(",", ":"), default=str).encode()
        try:
            await self._producer.send_and_wait(
                topic=topic,
                value=payload,
                key=(key or tenant_id).encode(),
                headers=[
                    ("id", envelope["id"].encode()),
                    ("type", type.encode()),
                    ("tenantid", tenant_id.encode()),
                    ("correlationid", correlation_id.encode()),
                ],
            )
        except Exception as exc:
            log.error("kafka_publish_failed topic=%s type=%s err=%s", topic, type, exc)
            raise ExternalServiceError(
                f"Failed to publish to Kafka topic '{topic}'",
                details={"topic": topic, "type": type},
            ) from exc


# ---------------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------------
EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class IdempotentConsumer:
    """
    Subscribes to one topic and dispatches to a handler.

    Idempotency: before processing an event, we check a Redis set
    ``processed_events:{service}:{event_id}``. If already seen, skip. After
    successful processing, add to the set with a 7-day TTL.

    **Why Redis and not Postgres?** Postgres gives stronger durability but
    requires a schema + migration + repo. Redis is acceptable here because:
    1. Events are retried indefinitely if Kafka doesn't see an ACK.
    2. Our processing handlers are already idempotent at the DB level
       (ON CONFLICT, etc.) — the Redis check is an optimization to skip
       redundant work, not a correctness guarantee. If Redis loses the
       set, handlers still run correctly.
    For stronger guarantees (financial events, legal audit), inject a
    Postgres-backed deduper instead.
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str],
        dedup_check: Callable[[str], Awaitable[bool]],
        dedup_mark: Callable[[str], Awaitable[None]],
        handler: EventHandler,
        max_poll_records: int = 10,
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._group_id = group_id
        self._topics = topics
        self._dedup_check = dedup_check
        self._dedup_mark = dedup_mark
        self._handler = handler
        self._max_poll_records = max_poll_records
        self._consumer: AIOKafkaConsumer | None = None
        self._stopping = False

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap,
            group_id=self._group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            max_poll_records=self._max_poll_records,
        )
        await self._consumer.start()
        log.info(
            "kafka_consumer_started group=%s topics=%s",
            self._group_id, ",".join(self._topics),
        )

    async def stop(self) -> None:
        self._stopping = True
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    async def run_forever(self) -> None:
        """Poll + dispatch loop. Designed to be awaited from a background task."""
        if self._consumer is None:
            raise ExternalServiceError("IdempotentConsumer.start() not called")
        try:
            async for msg in self._consumer:
                if self._stopping:
                    break
                await self._handle_one(msg)
                await self._consumer.commit()
        except asyncio.CancelledError:
            log.info("kafka_consumer_cancelled group=%s", self._group_id)
            raise

    async def _handle_one(self, msg: Any) -> None:
        try:
            envelope = json.loads(msg.value)
        except json.JSONDecodeError:
            log.error("kafka_bad_json topic=%s offset=%d", msg.topic, msg.offset)
            return

        event_id = envelope.get("id")
        if not event_id:
            log.error("kafka_missing_id topic=%s offset=%d", msg.topic, msg.offset)
            return

        if await self._dedup_check(event_id):
            log.debug("kafka_dup_skip id=%s", event_id)
            return

        try:
            await self._handler(envelope)
            await self._dedup_mark(event_id)
        except Exception:
            # Don't mark as processed — Kafka will redeliver on next commit.
            log.exception("kafka_handler_error id=%s topic=%s", event_id, msg.topic)
            raise
