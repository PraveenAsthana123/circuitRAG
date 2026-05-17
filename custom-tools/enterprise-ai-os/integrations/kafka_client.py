# ✅ P1 IMPROVED (Iter 36, 2026-05-17): producer + consumer configs
#     tightened for at-least-once delivery with idempotency, plus a
#     publish() helper that routes failed messages to a dead-letter
#     topic instead of silently dropping.
#
#     Pre-fix:
#       - Producer: no acks setting (default 1 — one broker ack), no
#         idempotence → duplicates on retry, possible silent loss.
#       - Consumer: enable_auto_commit=True → at-most-once. Crashes
#         between message receipt and processing meant the offset
#         was already committed, so the message was silently dropped
#         on restart.
#
#     Now:
#       - Producer: acks='all', enable_idempotence=True, retries=5.
#       - Consumer: enable_auto_commit=False. Caller is expected to
#         call commit() AFTER successful processing.
#       - New publish(producer, topic, value, dlq_topic) helper that
#         catches send failures and routes the failed message to
#         the DLQ. Returns True on success, False on DLQ.

import os
import json
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError


class KafkaClient:
    def __init__(self):
        self.bootstrap_servers = os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS",
            "localhost:9092",
        )

    def producer(self):
        return KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            # Iter 36 hardening:
            acks="all",                  # require ALL in-sync replicas
            enable_idempotence=True,     # de-dup on retry within a session
            retries=5,                   # retry transient errors
            max_in_flight_requests_per_connection=5,  # keep ordering w/ idempotence
        )

    def consumer(self, topic: str, group_id: str):
        return KafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=group_id,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            auto_offset_reset="earliest",
            # Iter 36: at-least-once. Caller must commit after success.
            enable_auto_commit=False,
        )

    def publish(self, producer, topic: str, value, dlq_topic: str | None = None) -> bool:
        """Send `value` to `topic`. On send failure (broker error), route
        to dlq_topic if provided and return False; otherwise re-raise.
        Returns True on success."""
        try:
            future = producer.send(topic, value=value)
            future.get(timeout=10)
            return True
        except KafkaError:
            if dlq_topic is None:
                raise
            try:
                # DLQ send must NOT itself loop on failure; on
                # double-failure we surface as RuntimeError so the
                # caller can persist-to-disk / alert.
                producer.send(dlq_topic, value={
                    "original_topic": topic,
                    "original_value": value,
                }).get(timeout=10)
                return False
            except KafkaError as dlq_err:
                raise RuntimeError(
                    f"Failed to publish to {topic} AND to DLQ {dlq_topic}: {dlq_err}"
                )
