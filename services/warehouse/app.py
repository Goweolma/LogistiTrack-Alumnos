"""Servicio base de almacén. Responsable: Alumno 3."""

import json
import logging
import os
import threading
import time
from typing import Any

from flask import Flask, jsonify

from common.database import get_connection
from common.events import build_event, validate_event
from common.kafka_client import (
    create_consumer,
    create_producer,
    publish,
    publish_dead_letter,
)

SERVICE_NAME = "warehouse"

INVENTORY_TOPIC = "inventory"
WAREHOUSE_TOPIC = "warehouse"
STATUS_TOPIC = "order-status"

CONSUMER_GROUP = "warehouse-service"


app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s warehouse %(message)s")

def initialize_storage() -> None:
    """Crea la tabla usada para recordar eventos ya procesados."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_events (
                    event_id VARCHAR(64) NOT NULL,
                    consumer VARCHAR(40) NOT NULL,
                    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (event_id, consumer)
                )
                """
            )

state_lock = threading.RLock()

service_state = {
    "kafka_connected": False,
    "processed_events": 0,
    "ignored_events": 0,
    "last_error": None,
}

def event_was_processed(event_id: str) -> bool:
    """Comprueba si la reserva ya fue atendida."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM processed_events
                WHERE event_id = %s AND consumer = %s
                """,
                (event_id, SERVICE_NAME),
            )
            return cursor.fetchone() is not None


def mark_event_processed(event_id: str) -> None:
    """Registra que Warehouse procesó el evento."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO processed_events (event_id, consumer)
                VALUES (%s, %s)
                ON CONFLICT (event_id, consumer) DO NOTHING
                """,
                (event_id, SERVICE_NAME),
            )
            
def calculate_preparation_seconds(payload: dict[str, Any]) -> float:
    """Calcula el tiempo de preparación según cantidad y tipo de producto."""
    try:
        base_seconds = max(
            0.0,
            float(os.getenv("PREPARATION_DELAY_SECONDS", "3")),
        )   
        
    except ValueError:
        base_seconds = 3.0

    items = payload.get("items", payload.get("products", []))

    # También acepta un pedido que traiga un solo producto directamente.
    if not isinstance(items, list) or not items:
        items = [payload]

    total_effort = 0.0

    for item in items:
        if not isinstance(item, dict):
            continue

        try:
            quantity = max(1, int(item.get("quantity", 1)))
        except (TypeError, ValueError):
            quantity = 1

        product_type = str(
            item.get(
                "product_type",
                item.get("type", item.get("name", "normal")),
            )
        ).lower()

        multiplier = 1.0

        if any(word in product_type for word in ("pesado", "voluminoso", "heavy", "bulky")):
            multiplier = 2.0
        elif any(word in product_type for word in ("frágil", "fragil", "vidrio", "fragile")):
            multiplier = 1.5
        elif any(word in product_type for word in ("refrigerado", "perecedero", "cold")):
            multiplier = 1.3

        total_effort += quantity * multiplier

    estimated_seconds = base_seconds * max(1.0, total_effort)

    # Evita que una cantidad muy grande congele la demostración.
    return round(min(estimated_seconds, 30.0), 2)

def process_inventory_event(event: dict[str, Any], producer) -> str:
    """Procesa únicamente eventos INVENTORY_RESERVED."""
    validate_event(event)

    # Almacén no debe procesar rechazos ni otros eventos.
    if event["event_type"] != "INVENTORY_RESERVED":
        logging.info(
            "Evento ignorado type=%s order_id=%s",
            event["event_type"],
            event["order_id"],
        )
        return "ignored"

    # Kafka puede entregar nuevamente un evento.
    if event_was_processed(event["event_id"]):
        logging.info(
            "Evento duplicado ignorado event_id=%s order_id=%s",
            event["event_id"],
            event["order_id"],
        )
        return "duplicate"

    order_id = event["order_id"]
    payload = dict(event["payload"])
    preparation_seconds = calculate_preparation_seconds(payload)

    # Primer cambio de estado.
    preparing_payload = dict(payload)
    preparing_payload.update(
        {
            "status": "PREPARING",
            "preparation_seconds": preparation_seconds,
            "reservation_event_id": event["event_id"],
        }
    )

    preparing_event = build_event(
        "PREPARING",
        order_id,
        SERVICE_NAME,
        preparing_payload,
    )

    publish(producer, STATUS_TOPIC, preparing_event)

    logging.info(
        "Preparando pedido order_id=%s tiempo=%.2f segundos",
        order_id,
        preparation_seconds,
    )

    # Simula el trabajo físico dentro del almacén.
    time.sleep(preparation_seconds)

    # Segundo cambio de estado.
    ready_payload = dict(payload)
    ready_payload.update(
        {
            "status": "READY_FOR_DELIVERY",
            "preparation_seconds": preparation_seconds,
            "reservation_event_id": event["event_id"],
        }
    )

    ready_status_event = build_event(
        "READY_FOR_DELIVERY",
        order_id,
        SERVICE_NAME,
        ready_payload,
    )

    publish(producer, STATUS_TOPIC, ready_status_event)

    # Este es el evento que posteriormente consumirá Delivery.
    order_ready_event = build_event(
        "ORDER_READY",
        order_id,
        SERVICE_NAME,
        ready_payload,
    )

    publish(producer, WAREHOUSE_TOPIC, order_ready_event)

    # Se registra hasta que todas las publicaciones terminaron.
    mark_event_processed(event["event_id"])
    
    logging.info(
        "Pedido listo order_id=%s event_id=%s",
        order_id,
        event["event_id"],
    )

    return "processed"

@app.get("/health")
def health():
    with state_lock:
        state = dict(service_state)

    status = "UP" if state["kafka_connected"] else "DEGRADED"

    response = {
        "service": SERVICE_NAME,
        "status": status,
        **state,
    }

    return jsonify(response), 200 if status == "UP" else 503


def consume_reservations() -> None:
    """Consume reservas aprobadas desde Kafka."""
    while True:
        consumer = None

        try:
            initialize_storage()

            producer = create_producer()
            consumer = create_consumer(
                CONSUMER_GROUP,
                [INVENTORY_TOPIC],
            )

            with state_lock:
                service_state["kafka_connected"] = True
                service_state["last_error"] = None

            logging.info(
                "Consumidor conectado topic=%s group=%s",
                INVENTORY_TOPIC,
                CONSUMER_GROUP,
            )

            while True:
                message = consumer.poll(1.0)

                if message is None:
                    continue

                if message.error():
                    raise RuntimeError(str(message.error()))

                try:
                    event = json.loads(
                        message.value().decode("utf-8")
                    )

                    result = process_inventory_event(
                        event,
                        producer,
                    )

                    logging.info(
                        "Resultado=%s offset=%s",
                        result,
                        message.offset(),
                    )

                    with state_lock:
                        if result == "processed":
                            service_state["processed_events"] += 1
                        else:
                            service_state["ignored_events"] += 1

                except (
                    json.JSONDecodeError,
                    UnicodeDecodeError,
                    TypeError,
                    ValueError,
                ) as error:
                    raw_message = message.value().decode(
                        "utf-8",
                        errors="replace",
                    )

                    try:
                        invalid_event = json.loads(raw_message)
                    except json.JSONDecodeError:
                        invalid_event = {"raw_message": raw_message}

                    publish_dead_letter(
                        producer,
                        invalid_event,
                        str(error),
                        source=SERVICE_NAME,
                    )

                    logging.exception(
                        "Evento inválido enviado a dead-letter"
                    )

                # El offset se confirma solamente después de atender el mensaje.
                consumer.commit(
                    message=message,
                    asynchronous=False,
                )

        except Exception as error:
            with state_lock:
                service_state["kafka_connected"] = False
                service_state["last_error"] = str(error)
            logging.exception(
                "Warehouse perdió conexión. Reintentando en 5 segundos"
            )
            time.sleep(5)

        finally:
            if consumer is not None:
                consumer.close()


if __name__ == "__main__":
    threading.Thread(target=consume_reservations, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5003")))

