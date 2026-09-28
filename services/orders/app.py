"""API base de pedidos. Responsable: Alumno 1."""

import os

from flask import Flask, jsonify, request

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
    # TODO(ALUMNO-1): devolver pedidos desde PostgreSQL.
    return jsonify([])


@app.get("/api/orders/<order_id>")
def get_order(order_id: str):
    # TODO(ALUMNO-1): devolver pedido e historial, o 404.
    return jsonify({"error": "NOT_IMPLEMENTED", "order_id": order_id}), 501


@app.post("/api/orders")
def create_order():
    payload = request.get_json(silent=True) or {}
    # TODO(ALUMNO-1): validar, persistir y publicar ORDER_CREATED.
    return jsonify({"error": "NOT_IMPLEMENTED", "received": payload}), 501


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")))

