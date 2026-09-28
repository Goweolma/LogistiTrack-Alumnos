"""Servicio base de reparto. Responsable: Alumno 4."""

import logging
import os
import threading
import time

from flask import Flask, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s delivery %(message)s")


@app.get("/health")
def health():
    return jsonify({"service": "delivery", "status": "UP"})


def consume_ready_orders() -> None:
    """TODO(ALUMNO-4): consumir ORDER_READY y simular recorrido."""
    while True:
        time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=consume_ready_orders, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5004")))

