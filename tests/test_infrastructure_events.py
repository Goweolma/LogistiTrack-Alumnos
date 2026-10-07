import json
from pathlib import Path

import jsonschema
import pytest

from common.events import build_event, validate_event

from common.kafka_client import PublishError, create_consumer, publish, publish_confirmed


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts" / "event.schema.json").read_text(encoding="utf-8"))
FORMAT_CHECKER = jsonschema.FormatChecker()


class RecordingProducer:
    def __init__(self):
        self.messages = []
        self.flush_calls = []

    def produce(self, topic, value, on_delivery):
        self.messages.append((topic, json.loads(value)))
        self.on_delivery = on_delivery

    def flush(self, timeout):
        self.flush_calls.append(timeout)
        self.on_delivery(None, None)
        return 0


def test_validate_event_accepts_contract_event():
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})

    validate_event(event)


def test_validate_event_rejects_invalid_event():
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    event["order_id"] = "ORDER-1"

    with pytest.raises(ValueError):
        validate_event(event)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_id", "not-a-uuid"),
        ("event_id", "123e4567e89b12d3a456426614174000"),
        ("event_id", "{123e4567-e89b-12d3-a456-426614174000}"),
        ("event_id", "urn:uuid:123e4567-e89b-12d3-a456-426614174000"),
        ("timestamp", "2026-09-29T18:00:00"),
        ("version", 2),
        ("version", 1.0),
        ("version", True),
        ("version", "1"),
        ("payload", []),
    ],
)
def test_validate_event_rejects_invalid_field(field, value):
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    event[field] = value

    with pytest.raises(ValueError):
        validate_event(event)


def test_validate_event_accepts_uppercase_uuid_from_schema():
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    event["event_id"] = event["event_id"].upper()

    validate_event(event)
    jsonschema.validate(event, SCHEMA, format_checker=FORMAT_CHECKER)


def test_validator_matches_schema_uuid_and_keeps_integer_version():
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    jsonschema.validate(event, SCHEMA, format_checker=FORMAT_CHECKER)

    event["event_id"] = event["event_id"].replace("-", "")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(event, SCHEMA, format_checker=FORMAT_CHECKER)
    with pytest.raises(ValueError):
        validate_event(event)

    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    event["version"] = 1.0
    jsonschema.validate(event, SCHEMA, format_checker=FORMAT_CHECKER)
    with pytest.raises(ValueError):
        validate_event(event)


def test_validate_event_rejects_unknown_fields():
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    event["unexpected"] = True

    with pytest.raises(ValueError):
        validate_event(event)


def test_publish_confirmed_is_shared_and_keeps_the_message_key():
    class KeyProducer(RecordingProducer):
        def produce(self, topic, value, on_delivery, key=None):
            self.key = key
            super().produce(topic, value, on_delivery)

    producer = KeyProducer()
    event = build_event("ORDER_IN_TRANSIT", "PED-000001", "delivery", {"status": "IN_TRANSIT"})

    publish_confirmed(producer, "deliveries", event, key=b"PED-000001", timeout=10)

    assert producer.key == b"PED-000001"
    assert producer.messages == [("deliveries", event)]
    assert producer.flush_calls == [10]


def test_publish_sends_valid_event_to_requested_topic():
    producer = RecordingProducer()
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})

    publish(producer, "orders", event)

    assert producer.messages == [("orders", event)]
    assert producer.flush_calls == [5]


def test_publish_sends_noncanonical_uuid_only_to_dead_letter():
    producer = RecordingProducer()
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {"quantity": 1})
    event["event_id"] = event["event_id"].replace("-", "")

    publish(producer, "orders", event)

    assert [topic for topic, _ in producer.messages] == ["dead-letter"]
    validate_event(producer.messages[0][1])


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


@pytest.mark.parametrize("invalid", [False, True])
@pytest.mark.parametrize("failure", ["timeout", "broker", "no-callback"])
def test_publish_does_not_report_success_without_broker_confirmation(invalid, failure):
    class UnconfirmedProducer(RecordingProducer):
        def flush(self, timeout):
            if failure == "broker":
                self.on_delivery("broker rejected message", None)
            return 1 if failure == "timeout" else 0

    producer = UnconfirmedProducer()
    event = build_event("ORDER_CREATED", "PED-000001", "orders", {})
    if invalid:
        event["order_id"] = "invalid"

    with pytest.raises(PublishError):
        publish(producer, "orders", event)

    assert [topic for topic, _ in producer.messages] == ["dead-letter" if invalid else "orders"]
