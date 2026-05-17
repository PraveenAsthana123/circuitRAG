# Negative drills for Iter 36 (2026-05-17): Kafka client hardening.

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_BACKDOOR_CHECK_producer_config_has_idempotence_and_acks(monkeypatch):
    """Pre-fix the producer had no acks/idempotence override — default
    acks=1 → silent loss on broker failover."""
    import integrations.kafka_client as mod
    captured_kwargs = {}
    def fake_producer(**kwargs):
        captured_kwargs.update(kwargs)
        return MagicMock()
    monkeypatch.setattr(mod, "KafkaProducer", fake_producer)
    mod.KafkaClient().producer()
    assert captured_kwargs["acks"] == "all"
    assert captured_kwargs["enable_idempotence"] is True
    assert captured_kwargs["retries"] >= 1


def test_BACKDOOR_CHECK_consumer_config_disables_auto_commit(monkeypatch):
    """Pre-fix enable_auto_commit=True → at-most-once delivery."""
    import integrations.kafka_client as mod
    captured_kwargs = {}
    def fake_consumer(topic, **kwargs):
        captured_kwargs.update(kwargs)
        return MagicMock()
    monkeypatch.setattr(mod, "KafkaConsumer", fake_consumer)
    mod.KafkaClient().consumer(topic="t", group_id="g")
    assert captured_kwargs["enable_auto_commit"] is False


def test_publish_success_path():
    import integrations.kafka_client as mod
    producer = MagicMock()
    producer.send.return_value.get.return_value = None
    client = mod.KafkaClient()
    assert client.publish(producer, "topic-x", {"k": 1}) is True
    producer.send.assert_called_once_with("topic-x", value={"k": 1})


def test_publish_routes_to_dlq_on_failure():
    import integrations.kafka_client as mod
    from kafka.errors import KafkaError

    sends = []
    producer = MagicMock()
    def send(topic, value=None):
        sends.append((topic, value))
        fut = MagicMock()
        if topic == "main-topic":
            fut.get.side_effect = KafkaError("broker down")
        else:
            fut.get.return_value = None
        return fut
    producer.send.side_effect = send

    client = mod.KafkaClient()
    result = client.publish(
        producer, "main-topic", {"k": 1}, dlq_topic="dlq",
    )
    assert result is False
    # First call to main-topic, then to dlq.
    assert sends[0][0] == "main-topic"
    assert sends[1][0] == "dlq"
    assert sends[1][1]["original_topic"] == "main-topic"
    assert sends[1][1]["original_value"] == {"k": 1}


def test_publish_raises_when_no_dlq_provided_and_send_fails():
    import integrations.kafka_client as mod
    from kafka.errors import KafkaError

    producer = MagicMock()
    producer.send.return_value.get.side_effect = KafkaError("boom")

    client = mod.KafkaClient()
    with pytest.raises(KafkaError):
        client.publish(producer, "main-topic", {"k": 1})


def test_publish_raises_runtime_error_on_double_failure():
    import integrations.kafka_client as mod
    from kafka.errors import KafkaError

    producer = MagicMock()
    producer.send.return_value.get.side_effect = KafkaError("everything dead")

    client = mod.KafkaClient()
    with pytest.raises(RuntimeError, match="AND to DLQ"):
        client.publish(producer, "main-topic", {"k": 1}, dlq_topic="dlq")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
