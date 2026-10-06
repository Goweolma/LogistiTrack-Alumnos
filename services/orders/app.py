"""API base de pedidos. Responsable: Alumno 1."""

import logging
import os

from flask import Flask, jsonify, request
from common.database import get_connection

app = Flask(__name__)


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
    # TODO(ALUMNO-1/2): consultar PostgreSQL; no dejar datos fijos en el código.
    return jsonify([])


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


@app.post("/api/orders")
def create_order():
    payload = request.get_json(silent=True) or {}
    # TODO(ALUMNO-1): validar, persistir y publicar ORDER_CREATED.
    return jsonify({"error": "NOT_IMPLEMENTED", "received": payload}), 501


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")))

