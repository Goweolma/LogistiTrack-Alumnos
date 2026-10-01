import json
import sys
from types import ModuleType

import pytest

from common.events import build_event, validate_event

try:
    import confluent_kafka  # noqa: F401
except ModuleNotFoundError:
    kafka_stub = ModuleType("confluent_kafka")

    class Consumer:  # pragma: no cover - solo permite probar sin Kafka local
        pass

    class Producer:  # pragma: no cover - solo permite probar sin Kafka local
        pass

    kafka_stub.Consumer = Consumer
    kafka_stub.Producer = Producer
    sys.modules["confluent_kafka"] = kafka_stub

from common.kafka_client import create_consumer, publish


class RecordingProducer:
    def __init__(self):
        self.messages = []
        self.flush_calls = []

    def produce(self, topic, value):
        self.messages.append((topic, json.loads(value)))

    def flush(self, timeout):
        self.flush_calls.append(timeout)


def test_validate_event_accepts_contract_event():
    validate_event(build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_id", "not-a-uuid"),
        ("order_id", "ORDER-1"),
        ("timestamp", "2026-09-29T18:00:00"),
        ("version", 2),
        ("payload", []),
    ],
)
def test_validate_event_rejects_invalid_field(field, value):
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    event[field] = value

    with pytest.raises(ValueError):
        validate_event(event)


def test_validate_event_rejects_unknown_fields():
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    event["unexpected"] = True

    with pytest.raises(ValueError):
        validate_event(event)


def test_publish_sends_valid_event_to_requested_topic():
    producer = RecordingProducer()
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})

    publish(producer, "orders", event)

    assert producer.messages == [("orders", event)]
    assert producer.flush_calls == [5]


def test_publish_sends_invalid_event_only_to_dead_letter():
    producer = RecordingProducer()
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    event["order_id"] = "ORDER-1"

    publish(producer, "orders", event)

    assert len(producer.messages) == 1
    topic, dead_letter_event = producer.messages[0]
    assert topic == "dead-letter"
    validate_event(dead_letter_event)
    assert dead_letter_event["event_type"] == "PROCESSING_FAILED"
    assert dead_letter_event["payload"]["original_event"] == event
    assert "order_id" in dead_letter_event["payload"]["error"]


def test_create_consumer_starts_from_earliest_without_auto_commit(monkeypatch):
    captured = {}

    class FakeConsumer:
        def __init__(self, config):
            captured["config"] = config

        def subscribe(self, topics):
            captured["topics"] = topics

    monkeypatch.setattr("common.kafka_client.Consumer", FakeConsumer)

    create_consumer("inventory", ["orders"])

    assert captured["config"]["group.id"] == "inventory"
    assert captured["config"]["auto.offset.reset"] == "earliest"
    assert captured["config"]["enable.auto.commit"] is False
    assert captured["topics"] == ["orders"]
