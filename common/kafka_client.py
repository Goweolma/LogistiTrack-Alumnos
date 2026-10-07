"""Ayudantes mínimos de Kafka que el alumno de infraestructura ampliará."""

import json
import os
import re

from confluent_kafka import Consumer, Producer

from common.events import build_event, validate_event


DEAD_LETTER_TOPIC = "dead-letter"


class PublishError(RuntimeError):
    """Kafka no confirmó la entrega; el consumidor no debe confirmar el offset."""


def publish_confirmed(
    producer: Producer,
    topic: str,
    event: dict,
    *,
    key: bytes | None = None,
    timeout: float = 5,
) -> None:
    """Publica y espera la confirmación del broker. Lo usan negocio y dead-letter."""
    results = []
    payload = json.dumps(event).encode("utf-8")
    callback = lambda error, message: results.append(error)
    if key is None:
        producer.produce(topic, payload, on_delivery=callback)
    else:
        producer.produce(topic, payload, key=key, on_delivery=callback)
    remaining = producer.flush(timeout)
    if remaining or not results or results[0] is not None:
        raise PublishError(f"Kafka no confirmó la publicación en {topic}: {results or 'sin respuesta'}")


def create_producer() -> Producer:
    return Producer({"bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")})


def publish(producer: Producer, topic: str, event: dict) -> None:
    try:
        validate_event(event)
    except (TypeError, ValueError) as exc:
        publish_dead_letter(producer, event, str(exc))
        return

    publish_confirmed(producer, topic, event)


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
    validate_event(dead_letter_event)
    publish_confirmed(producer, DEAD_LETTER_TOPIC, dead_letter_event)


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
