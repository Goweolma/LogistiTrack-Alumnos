"""Servicio base de inventario. Responsable: Alumno 2."""

import logging
import os
import threading
import time

from flask import Flask, jsonify
from common.database import get_connection

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s inventory %(message)s")


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


def consume_orders() -> None:
    """TODO(ALUMNO-2): consumir ORDER_CREATED y reservar con transacción."""
    while True:
        time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=consume_orders, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5002")))

