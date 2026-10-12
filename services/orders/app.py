"""API base de pedidos. Responsable: Alumno 1."""

import logging
import os


from flask import Flask, jsonify, request
from common.database import get_connection
from common.events import build_event
from common.kafka_client import create_producer, publish


app = Flask(__name__)

SERVICE_NAME = "orders"
ORDERS_TOPIC = "orders"

@app.get("/health")
def health():
    return jsonify({"service": "orders", "status": "UP"})


@app.get("/api/health")
def platform_health():
    """Respuesta inicial para que el frontend pueda comprobar la API."""
    return jsonify(
        {
            "status": "BASE_READY",
            "message": "La infraestructura funciona; el flujo aún debe implementarse.",
        }
    )


@app.get("/api/products")
def list_products():
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT product_id, name, product_description, price
                    FROM products
                    ORDER BY product_id
                    """
                )
                rows = cursor.fetchall()

    except Exception:
        logging.exception("Error al consultar el catálogo de productos")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503

    products = [
        {
            "product_id": product_id,
            "name": name,
            "description": description,
            "price": float(price),
        }
        for product_id, name, description, price in rows
    ]

    return jsonify(products)


@app.get("/api/orders")
def list_orders():
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT order_id, total, created_at, delivery_address, status
                    FROM orders
                    ORDER BY created_at DESC
                    """
                )
                rows = cursor.fetchall()

    except Exception:
        logging.exception("Error al consultar la lista de pedidos")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503

    orders = [
        {
            "order_id": order_id,
            "total": float(total),
            "created_at": created_at.isoformat(),
            "delivery_address": delivery_address,
            "status": status,
        }
        for order_id, total, created_at, delivery_address, status in rows
    ]

    return jsonify(orders)
    


@app.get("/api/orders/<order_id>")
def get_order(order_id: str):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT order_id, total, created_at, delivery_address, status
                    FROM orders
                    WHERE order_id = %s
                    """,
                    (order_id,),
                )

                order = cursor.fetchone()

                if order is None:
                    return jsonify(
                        {
                            "error": "ORDER_NOT_FOUND",
                            "order_id": order_id,
                        }
                    ), 404

                cursor.execute(
                    """
                    SELECT status, created_at
                    FROM order_history
                    WHERE order_id = %s
                    ORDER BY history_id
                    """,
                    (order_id,),
                )

                history_rows = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT product_id, quantity
                    FROM order_items
                    WHERE order_id = %s
                    ORDER BY product_id
                    """,
                    (order_id,),
                )

                item_rows = cursor.fetchall()

    except Exception:
        logging.exception("Error al consultar el detalle del pedido")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503

    return jsonify(
        {
            "order_id": order[0],
            "total": float(order[1]),
            "created_at": order[2].isoformat(),
            "delivery_address": order[3],
            "status": order[4],
            "history": [
                {
                    "status": status,
                    "created_at": created_at.isoformat(),
                }
                for status, created_at in history_rows
            ],
            "items": [
                {
                    "product_id": product_id,
                    "quantity": quantity,
                }
                for product_id, quantity in item_rows
            ],
        }
    )

@app.patch("/api/orders/<order_id>/cancel")
def cancel_order(order_id: str):
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT status
                    FROM orders
                    WHERE order_id = %s
                    FOR UPDATE
                    """,
                    (order_id,),
                )

                order = cursor.fetchone()

                if order is None:
                    return jsonify(
                        {
                            "error": "ORDER_NOT_FOUND",
                            "order_id": order_id,
                        }
                    ), 404

                current_status = order[0]

                if current_status != "RECEIVED":
                    return jsonify(
                        {
                            "error": "ORDER_CANNOT_BE_CANCELLED",
                            "order_id": order_id,
                            "status": current_status,
                        }
                    ), 409

                cursor.execute(
                    """
                    UPDATE orders
                    SET status = 'CANCELLED'
                    WHERE order_id = %s
                    """,
                    (order_id,),
                )

                cursor.execute(
                    """
                    INSERT INTO order_history (order_id, status)
                    VALUES (%s, %s)
                    """,
                    (order_id, "CANCELLED"),
                )

    except Exception:
        logging.exception("Error al cancelar el pedido")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503

    return jsonify(
        {
            "order_id": order_id,
            "status": "CANCELLED",
        }
    ), 200
def validate_order_payload(payload):
    if not isinstance(payload, dict):
        return "INVALID_JSON"

    delivery_address = payload.get("delivery_address")
    items = payload.get("items")

    if (
        not isinstance(delivery_address, str)
        or not delivery_address.strip()
        or len(delivery_address.strip()) > 200
    ):
        return "INVALID_DELIVERY_ADDRESS"

    if not isinstance(items, list) or not items:
        return "INVALID_ITEMS"

    product_ids = set()

    for item in items:
        if not isinstance(item, dict):
            return "INVALID_ITEM"

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        if not isinstance(product_id, str) or not product_id.strip():
            return "INVALID_PRODUCT_ID"

        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
        ):
            return "INVALID_QUANTITY"

        normalized_product_id = product_id.strip()
        if normalized_product_id in product_ids:
            return "DUPLICATE_PRODUCT"

        product_ids.add(normalized_product_id)

    return None


@app.post("/api/orders")
def create_order():
    payload = request.get_json(silent=True)
    validation_error = validate_order_payload(payload)

    if validation_error:
        return jsonify(
            {
                "error": "INVALID_ORDER",
                "detail": validation_error,
            }
        ), 400

    delivery_address = payload["delivery_address"].strip()
    items = [
        {
            "product_id": item["product_id"].strip(),
            "quantity": item["quantity"],
        }
        for item in payload["items"]
    ]


    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                total = 0

                for item in items:
                    cursor.execute(
                        "SELECT price FROM products WHERE product_id = %s",
                        (item["product_id"],),
                    )
                    product = cursor.fetchone()

                    if product is None:
                        return jsonify(
                            {
                                "error": "INVALID_ORDER",
                                "detail": "PRODUCT_NOT_FOUND",
                                "product_id": item["product_id"],
                            }
                        ), 400

                    total += product[0] * item["quantity"]

                cursor.execute(
                    """
                    INSERT INTO orders (total, delivery_address, status)
                    VALUES (%s, %s, 'RECEIVED')
                    RETURNING order_id
                    """,
                    (total, delivery_address),
                )

                order_id = cursor.fetchone()[0]

                for item in items:
                    cursor.execute(
                        """
                        INSERT INTO order_items (
                            order_id, product_id, quantity
                        )
                        VALUES (%s, %s, %s)
                        """,
                        (
                            order_id,
                            item["product_id"],
                            item["quantity"],
                        ),
                    )

                cursor.execute(
                    """
                    INSERT INTO order_history (order_id, status)
                    VALUES (%s, %s)
                    """,
                    (order_id, "RECEIVED"),
                )

    except Exception:
        logging.exception("Error al crear el pedido")
        return jsonify({"error": "DATABASE_UNAVAILABLE"}), 503
    try:
        event = build_event(
                "ORDER_CREATED",
                order_id,
                SERVICE_NAME,
                {"items": items},
        )

        producer = create_producer()
        publish(producer, ORDERS_TOPIC, event)

    except Exception:
        logging.exception("Error al publicar ORDER_CREATED")
        return jsonify(
            {
                "error": "KAFKA_UNAVAILABLE",
                "order_id": order_id,
            }
        ), 503

    return jsonify(
        {
            "order_id": order_id,
            "status": "RECEIVED",
            "total": float(total),
            "items": items,
        }
    ), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")))

