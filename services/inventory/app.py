"""Servicio base de inventario. Responsable: Alumno 2."""

import json
import logging
import os
import threading
import time
from typing import Any

from flask import Flask, jsonify
from common.database import get_connection
from common.events import build_event, validate_event
from common.kafka_client import create_consumer, create_producer, publish_dead_letter

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s inventory %(message)s")


SERVICE_NAME = "inventory"
ORDERS_TOPIC = "orders"
INVENTORY_TOPIC = "inventory"
STATUS_TOPIC = "order-status"
CONSUMER_GROUP = "inventory-service"

WAREHOUSES = ("NORTE", "SUR")

INVENTORY_QUERY = """
    SELECT p.product_id, p.name, p.product_description, p.price, i.warehouse, i.quantity
    FROM products p
    LEFT JOIN inventory i ON i.product_id = p.product_id
    {where}
    ORDER BY p.product_id, i.warehouse
"""


def fetch_inventory(product_id: str | None = None) -> list[dict]:
    where = "WHERE p.product_id = %s" if product_id else ""
    params = (product_id,) if product_id else ()

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(INVENTORY_QUERY.format(where=where), params)
            rows = cursor.fetchall()

    products: dict[str, dict] = {}
    for pid, name, description, price, warehouse, quantity in rows:
        product = products.setdefault(
            pid,
            {
                "product_id": pid,
                "name": name,
                "description": description,
                "price": float(price),
                "stock": {w: 0 for w in WAREHOUSES},
                "total": 0,
            },
        )
        if warehouse is not None:
            product["stock"][warehouse] = quantity
            product["total"] += quantity
    return list(products.values())


@app.get("/health")
def health():
    return jsonify({"service": "inventory", "status": "UP"})


@app.get("/api/inventory")
def list_inventory():
    try:
        return jsonify(fetch_inventory())
    except Exception:
        logging.exception("No se pudo consultar el inventario")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503


@app.get("/api/inventory/<product_id>")
def get_inventory(product_id: str):
    try:
        products = fetch_inventory(product_id)
    except Exception:
        logging.exception("No se pudo consultar el producto %s", product_id)
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503
    if not products:
        return jsonify({"error": "PRODUCT_NOT_FOUND", "product_id": product_id}), 404
    return jsonify(products[0])


def requested_quantities(payload: dict[str, Any]) -> dict[str, int]:
    """Suma las cantidades pedidas por producto. Espera payload.items = [{product_id, quantity}]."""
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("payload.items debe ser una lista no vacía")

    quantities: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("product_id"), str):
            raise ValueError("Cada item debe incluir product_id")
        quantity = item.get("quantity")
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("quantity debe ser un entero positivo")
        quantities[item["product_id"]] = quantities.get(item["product_id"], 0) + quantity
    return quantities


def choose_warehouse(stock: dict[tuple[str, str], int], quantities: dict[str, int]) -> str | None:
    """Primer almacén, en orden NORTE y SUR, que puede surtir el pedido completo."""
    for warehouse in WAREHOUSES:
        if all(stock.get((pid, warehouse), 0) >= quantity for pid, quantity in quantities.items()):
            return warehouse
    return None


def reserve_inventory(event: dict[str, Any], quantities: dict[str, int]) -> tuple[str, dict | None]:
    """Reserva en una sola transacción y devuelve (resultado, evento a publicar)."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            # La llave primaria bloquea a un duplicado concurrente hasta que esta transacción termine.
            cursor.execute(
                """
                INSERT INTO processed_events (event_id, service_name)
                VALUES (%s, %s)
                ON CONFLICT (event_id, service_name) DO NOTHING
                """,
                (event["event_id"], SERVICE_NAME),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    "SELECT result_event FROM inventory_reservations WHERE event_id = %s",
                    (event["event_id"],),
                )
                row = cursor.fetchone()
                return "duplicate", row[0] if row else None

            # Orders guarda el pedido antes de publicar ORDER_CREATED; si no existe, todo se revierte.
            cursor.execute(
                "SELECT status FROM orders WHERE order_id = %s FOR UPDATE",
                (event["order_id"],),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"ORDER_NOT_FOUND: {event['order_id']} no existe en orders")

            # Otro ORDER_CREATED (distinto event_id) no debe reservar de nuevo ni regresar el estado del pedido.
            current_status = row[0]
            if current_status != "RECEIVED":
                raise ValueError(f"INVALID_ORDER_STATE: se esperaba RECEIVED, pero está en {current_status}")

            # FOR UPDATE evita que dos pedidos reserven la misma existencia al mismo tiempo.
            cursor.execute(
                """
                SELECT product_id, warehouse, quantity
                FROM inventory
                WHERE product_id = ANY(%s)
                ORDER BY product_id, warehouse
                FOR UPDATE
                """,
                (list(quantities),),
            )
            stock = {(pid, warehouse): quantity for pid, warehouse, quantity in cursor.fetchall()}
            warehouse = choose_warehouse(stock, quantities)

            payload = {"items": event["payload"]["items"], "order_event_id": event["event_id"]}
            if warehouse is None:
                event_type = "INVENTORY_REJECTED"
                payload.update({"status": event_type, "reason": "OUT_OF_STOCK"})
            else:
                event_type = "INVENTORY_RESERVED"
                payload.update({"status": event_type, "warehouse": warehouse})
                for pid, quantity in quantities.items():
                    cursor.execute(
                        """
                        UPDATE inventory
                        SET quantity = quantity - %s
                        WHERE product_id = %s AND warehouse = %s
                        """,
                        (quantity, pid, warehouse),
                    )

            cursor.execute(
                "UPDATE orders SET status = %s WHERE order_id = %s",
                (event_type, event["order_id"]),
            )
            cursor.execute(
                "INSERT INTO order_history (order_id, status) VALUES (%s, %s)",
                (event["order_id"], event_type),
            )

            result_event = build_event(event_type, event["order_id"], SERVICE_NAME, payload)
            cursor.execute(
                """
                INSERT INTO inventory_reservations (event_id, order_id, status, warehouse, result_event)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                """,
                (event["event_id"], event["order_id"], event_type, warehouse, json.dumps(result_event)),
            )
    return ("reserved" if warehouse else "rejected"), result_event


class PublishError(RuntimeError):
    """Kafka no confirmó la entrega; el offset de ORDER_CREATED no debe confirmarse."""


def publish_confirmed(producer, topic: str, event: dict[str, Any]) -> None:
    """Publica y espera la confirmación del broker; el helper común no revisa el resultado de flush."""
    validate_event(event)
    results = []
    producer.produce(
        topic,
        json.dumps(event).encode("utf-8"),
        on_delivery=lambda error, message: results.append(error),
    )
    remaining = producer.flush(10)
    if remaining or not results or results[0] is not None:
        raise PublishError(f"Kafka no confirmó {event['event_type']} en {topic}: {results or 'sin respuesta'}")


def process_order_event(event: dict[str, Any], producer) -> str:
    """Atiende un ORDER_CREATED y publica la reserva o el rechazo."""
    validate_event(event)
    if event["event_type"] != "ORDER_CREATED":
        logging.info("Evento ignorado type=%s order_id=%s", event["event_type"], event["order_id"])
        return "ignored"

    quantities = requested_quantities(event["payload"])
    result, outgoing = reserve_inventory(event, quantities)

    # Un duplicado reenvía el mismo evento (mismo event_id) por si la publicación anterior se perdió.
    # Si Kafka no confirma, PublishError evita el commit del offset y el reintento llega como duplicado.
    if outgoing is not None:
        publish_confirmed(producer, INVENTORY_TOPIC, outgoing)
        publish_confirmed(producer, STATUS_TOPIC, outgoing)

    logging.info(
        "Resultado=%s order_id=%s event_id=%s publicado=%s",
        result,
        event["order_id"],
        event["event_id"],
        outgoing["event_type"] if outgoing else None,
    )
    return result


def consume_orders() -> None:
    """Consume ORDER_CREATED desde Kafka y confirma el offset después de atenderlo."""
    while True:
        consumer = None
        try:
            producer = create_producer()
            consumer = create_consumer(CONSUMER_GROUP, [ORDERS_TOPIC])
            logging.info("Consumidor conectado topic=%s group=%s", ORDERS_TOPIC, CONSUMER_GROUP)

            while True:
                message = consumer.poll(1.0)
                if message is None:
                    continue
                if message.error():
                    raise RuntimeError(str(message.error()))

                raw_message = message.value().decode("utf-8", errors="replace")
                try:
                    process_order_event(json.loads(raw_message), producer)
                except (json.JSONDecodeError, TypeError, ValueError) as error:
                    try:
                        invalid_event = json.loads(raw_message)
                    except json.JSONDecodeError:
                        invalid_event = {"raw_message": raw_message}
                    publish_dead_letter(producer, invalid_event, str(error), source=SERVICE_NAME)
                    logging.exception("Evento inválido enviado a dead-letter")

                consumer.commit(message=message, asynchronous=False)

        except Exception:
            # Sin commit del offset: el mensaje se vuelve a leer al reconectar.
            logging.exception("Inventory perdió conexión. Reintentando en 5 segundos")
            time.sleep(5)
        finally:
            if consumer is not None:
                consumer.close()


if __name__ == "__main__":
    threading.Thread(target=consume_orders, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5002")))

