"""Servicio base de inventario. Responsable: Alumno 2."""

import logging
import os
import threading
import time

from flask import Flask, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s inventory %(message)s")


@app.get("/health")
def health():
    return jsonify({"service": "inventory", "status": "UP"})


def consume_orders() -> None:
    """TODO(ALUMNO-2): consumir ORDER_CREATED y reservar con transacción."""
    while True:
        time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=consume_orders, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5002")))

