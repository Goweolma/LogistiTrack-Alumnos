"""Ayudantes mínimos de Kafka que el alumno de infraestructura ampliará."""

import json
import os
import re

from confluent_kafka import Consumer, Producer

from common.events import build_event, validate_event


DEAD_LETTER_TOPIC = "dead-letter"


def create_producer() -> Producer:
    return Producer({"bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")})


def publish(producer: Producer, topic: str, event: dict) -> None:
    try:
        validate_event(event)
    except (TypeError, ValueError) as exc:
        publish_dead_letter(producer, event, str(exc))
        return

    producer.produce(topic, json.dumps(event).encode("utf-8"))
    producer.flush(5)


def publish_dead_letter(
    producer: Producer,
    event: dict,
    reason: str,
    source: str = "infrastructure",
) -> None:
    """Publica un evento inválido sin volver a intentar el topic original."""
    order_id = event.get("order_id") if isinstance(event, dict) else None
    if not isinstance(order_id, str) or not re.fullmatch(r"PED-[0-9]{6}", order_id):
        order_id = "PED-000000"

    original_event = json.loads(json.dumps(event, default=str))
    dead_letter_event = build_event(
        "PROCESSING_FAILED",
        order_id,
        source,
        {"error": reason, "original_event": original_event},
    )
    producer.produce(DEAD_LETTER_TOPIC, json.dumps(dead_letter_event).encode("utf-8"))
    producer.flush(5)


def create_consumer(group_id: str, topics: list[str]) -> Consumer:
    consumer = Consumer(
        {
            "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(topics)
    return consumer
