"""Servicio de reparto. Responsable: Alumno 4.

REQUISITO DE INTEGRACION pendiente de acordar con alumnos 1 y 2 (no se crea DDL):
orders necesita driver_id y vehicle_id opcionales.
order_history necesita event_id UUID UNIQUE y event JSONB opcionales para reintentos.
processed_events usa la clave (event_id, service_name), como init.sql.
ORDER_READY solo necesita el sobre común.

Probar: python -m pytest -q tests/test_delivery.py
Integración: docker compose up -d --build delivery; docker compose logs -f delivery
Enviar ORDER_READY a warehouse para un pedido READY_FOR_DELIVERY y observar
order-status, deliveries, orders y order_history. Reenviar el evento: deben
permanecer cuatro etapas. Con dos réplicas, ninguna unidad debe tener dos
pedidos en DRIVER_ASSIGNED, IN_TRANSIT o NEAR_DESTINATION.

El historial conserva los eventos para recuperarlos tras fallos. Kafka recibe
al menos una vez: las repeticiones mantienen event_id para deduplicación.
Las pruebas unitarias no sustituyen la integración PostgreSQL/Kafka.
"""

import logging
import json
import os
import re
import threading
import time
from datetime import datetime
from uuid import UUID, NAMESPACE_URL, uuid5

from flask import Flask, jsonify
from common.database import get_connection
from common.events import build_event, validate_event
from common.kafka_client import create_consumer, create_producer

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s delivery %(message)s")
log = logging.getLogger(__name__)
STAGES = ("DRIVER_ASSIGNED", "IN_TRANSIT", "NEAR_DESTINATION", "DELIVERED")
EVENT_TYPES = ("DRIVER_ASSIGNED", "ORDER_IN_TRANSIT", "NEAR_DESTINATION", "ORDER_DELIVERED")
# Mantener idéntica flota en todas las réplicas.
FLEET = (("REP-001", "UNI-001"), ("REP-002", "UNI-002"), ("REP-003", "UNI-003"))


class RetryLater(RuntimeError):
    """Mensaje pendiente: no confirmar el offset."""


@app.get("/health")
def health():
    return jsonify({"service": "delivery", "status": "UP"})


def decode_event(raw):
    event = json.loads(raw)
    if not isinstance(event, dict):
        raise ValueError("El evento debe ser un objeto")
    validate_event(event)
    if set(event) != {"event_id", "event_type", "timestamp", "source", "order_id", "version", "payload"}:
        raise ValueError("Campos fuera del contrato")
    UUID(event["event_id"])
    if not isinstance(event["order_id"], str) or not re.fullmatch(r"PED-[0-9]{6}", event["order_id"]):
        raise ValueError("order_id inválido")
    for field, minimum in (("source", 2), ("event_type", 3)):
        if not isinstance(event[field], str) or len(event[field]) < minimum:
            raise ValueError(f"{field} inválido")
    if type(event["version"]) is not int or event["version"] != 1:
        raise ValueError("Versión inválida")
    if datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("timestamp necesita zona horaria")
    return event


def publish_confirmed(producer, topic, event):
    # El helper común no comprueba la entrega: esperamos confirmación aquí.
    results = []
    producer.produce(topic, key=event["order_id"].encode(),
                     value=json.dumps(event).encode(),
                     on_delivery=lambda error, message: results.append(error))
    remaining = producer.flush(10)
    if remaining or not results or results[0] is not None:
        raise RetryLater(f"Kafka no confirmó {topic}: {results}")
    log.info("Publicado %s pedido=%s event_id=%s topic=%s", event["event_type"],
             event["order_id"], event["event_id"], topic)


def publish_stage(producer, event):
    publish_confirmed(producer, "order-status", event)
    if event["event_type"] in ("ORDER_IN_TRANSIT", "ORDER_DELIVERED"):
        publish_confirmed(producer, "deliveries", event)


class DeliveryStore:
    def __init__(self, connection):
        self.connection = connection

    def processed(self, event_id):
        with self.connection.transaction():
            return self.connection.execute(
                "SELECT 1 FROM processed_events WHERE event_id=%s AND service_name=%s",
                (event_id, "delivery")).fetchone() is not None

    def history(self, order_id):
        with self.connection.transaction():
            rows = self.connection.execute(
                "SELECT status, event FROM order_history WHERE order_id=%s "
                "AND event->>'source'=%s", (order_id, "delivery")).fetchall()
        events = {status: event for status, event in rows}
        return [events[status] for status in STAGES if status in events]

    def advance(self, order_id):
        with self.connection.transaction():
            # Serializa reserva/liberación entre todas las réplicas.
            self.connection.execute("SELECT pg_advisory_xact_lock(42004, 1)")
            row = self.connection.execute(
                "SELECT status, driver_id, vehicle_id FROM orders WHERE order_id=%s FOR UPDATE",
                (order_id,)).fetchone()
            if row is None:
                raise RetryLater("Pedido todavía no disponible")
            status, driver, vehicle = row
            if status == "DELIVERED":
                return None
            if status == "READY_FOR_DELIVERY":
                busy = self.connection.execute(
                    "SELECT driver_id, vehicle_id FROM orders WHERE status IN (%s,%s,%s)",
                    STAGES[:3]).fetchall()
                unit = next(((d, v) for d, v in FLEET
                             if all(d != bd and v != bv for bd, bv in busy)), None)
                if unit is None:
                    raise RetryLater("Todas las unidades están ocupadas")
                driver, vehicle = unit
                index = 0
            elif status in STAGES[:3]:
                if (driver, vehicle) not in FLEET:
                    raise RetryLater("Asignación persistida no pertenece a la flota")
                index = STAGES.index(status) + 1
            else:
                raise RetryLater(f"Pedido no preparado para reparto: {status}")
            status = STAGES[index]
            event = build_event(EVENT_TYPES[index], order_id, "delivery",
                                {"status": status, "driver_id": driver, "vehicle_id": vehicle})
            event["event_id"] = str(uuid5(NAMESPACE_URL, f"logistitrack/delivery/{order_id}/{status}"))
            self.connection.execute(
                "UPDATE orders SET status=%s, driver_id=%s, vehicle_id=%s WHERE order_id=%s",
                (status, driver, vehicle, order_id))
            self.connection.execute(
                "INSERT INTO order_history (order_id,status,event_id,event) VALUES (%s,%s,%s,%s::jsonb)",
                (order_id, status, event["event_id"], json.dumps(event)))
            return event

    def finish(self, event_id):
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO processed_events (event_id,service_name) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (event_id, "delivery"))


def run_delivery(store, producer, incoming, delay):
    if store.processed(incoming["event_id"]):
        return
    for saved in store.history(incoming["order_id"]):
        publish_stage(producer, saved)
    while True:
        event = store.advance(incoming["order_id"])
        if event is None:
            break
        publish_stage(producer, event)
        if event["payload"]["status"] != "DELIVERED":
            time.sleep(delay)
    store.finish(incoming["event_id"])


def process_message(producer, message, delay):
    try:
        incoming = decode_event(message.value())
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        failure = build_event("PROCESSING_FAILED", "PED-000000", "delivery",
                              {"reason": str(exc), "topic": message.topic(),
                               "partition": message.partition(), "offset": message.offset()})
        failure["event_id"] = str(uuid5(NAMESPACE_URL,
            f"delivery/dead-letter/{message.topic()}/{message.partition()}/{message.offset()}"))
        publish_confirmed(producer, "dead-letter", failure)
        return
    if incoming["event_type"] != "ORDER_READY":
        return
    with get_connection() as connection:
        connection.autocommit = True
        # Bloqueo de sesión: un mismo pedido no recorre etapas en dos réplicas.
        key = int(incoming["order_id"][4:])
        if not connection.execute("SELECT pg_try_advisory_lock(42005, %s)", (key,)).fetchone()[0]:
            raise RetryLater("Otro consumidor procesa este pedido")
        try:
            run_delivery(DeliveryStore(connection), producer, incoming, delay)
        finally:
            connection.execute("SELECT pg_advisory_unlock(42005, %s)", (key,))


def consume_ready_orders():
    delay = float(os.getenv("DELIVERY_STEP_DELAY_SECONDS", "2"))
    if not 0 <= delay <= 30:
        raise ValueError("DELIVERY_STEP_DELAY_SECONDS debe estar entre 0 y 30")
    while True:
        consumer = None
        try:
            producer = create_producer()
            consumer = create_consumer("delivery-service", ["warehouse"])
            while True:
                message = consumer.poll(1)
                if message is None:
                    continue
                if message.error():
                    raise RetryLater(str(message.error()))
                process_message(producer, message, delay)
                consumer.commit(message=message, asynchronous=False)
        except Exception:
            log.exception("Reparto pendiente; se reintentará sin confirmar el mensaje")
        finally:
            if consumer is not None:
                consumer.close()
        time.sleep(3)
if __name__ == "__main__":
    threading.Thread(target=consume_ready_orders, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5004")))

