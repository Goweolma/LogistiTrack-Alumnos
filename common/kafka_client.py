"""Ayudantes mínimos de Kafka que el alumno de infraestructura ampliará."""

import json
import os

from confluent_kafka import Consumer, Producer


def create_producer() -> Producer:
    return Producer({"bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")})


def publish(producer: Producer, topic: str, event: dict) -> None:
    producer.produce(topic, json.dumps(event).encode("utf-8"))
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

