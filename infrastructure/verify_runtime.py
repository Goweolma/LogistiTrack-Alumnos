"""Prueba de infraestructura real ejecutada dentro del contenedor Orders.

Desde PowerShell: Get-Content -Raw infrastructure/verify_runtime.py |
    docker compose exec -T orders python -
Desde Linux: docker compose exec -T orders python - < infrastructure/verify_runtime.py

Lee PostgreSQL, resuelve nombres y publica un diagnóstico inválido mediante
el helper común. Solo añade un PROCESSING_FAILED a dead-letter, no pedidos.
"""

import json
import os
import socket
import time
from uuid import uuid4

from confluent_kafka import Consumer, TopicPartition

from common.database import get_connection
from common.events import build_event, validate_event
from common.kafka_client import create_producer, publish


def main():
    for hostname in ("postgres", "kafka", "orders", "inventory", "warehouse", "delivery"):
        socket.getaddrinfo(hostname, None)
        print(f"[OK] DNS interno: {hostname}", flush=True)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
    print("[OK] PostgreSQL accesible por DATABASE_URL", flush=True)

    consumer = Consumer({
        "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        "group.id": f"infrastructure-check-{uuid4()}",
        "enable.auto.commit": False,
    })
    try:
        metadata = consumer.list_topics(timeout=10)
        expected = {"orders", "inventory", "warehouse", "deliveries", "order-status", "dead-letter"}
        assert expected <= metadata.topics.keys(), "Faltan topics"
        partitions = []
        for topic in ("orders", "dead-letter"):
            assert metadata.topics[topic].error is None, f"Topic no disponible: {topic}"
            for partition in metadata.topics[topic].partitions:
                _, end = consumer.get_watermark_offsets(TopicPartition(topic, partition), timeout=10)
                partitions.append(TopicPartition(topic, partition, end))
        consumer.assign(partitions)
        invalid = build_event("INFRA_DIAGNOSTIC", "PED-000000", "infrastructure", {"probe": str(uuid4())})
        invalid["event_id"] = "invalid-" + str(uuid4())
        publish(create_producer(), "orders", invalid)
        found = False
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            message = consumer.poll(0.5)
            if message is None:
                continue
            if message.error():
                raise RuntimeError(str(message.error()))
            event = json.loads(message.value())
            assert event.get("event_id") != invalid["event_id"], "Evento inválido llegó al topic de negocio"
            if message.topic() == "dead-letter" and event.get("payload", {}).get("original_event") == invalid:
                validate_event(event)
                assert event["event_type"] == "PROCESSING_FAILED"
                assert event["payload"]["error"]
                found = True
                print(f"[OK] PROCESSING_FAILED recibido: event_id={event['event_id']}", flush=True)
        assert found, "No se recibió el diagnóstico en dead-letter dentro del plazo"
        print("[OK] Original y motivo conservados; inválido ausente en orders durante 15 s", flush=True)
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
