"""Servicio base de almacén. Responsable: Alumno 3."""

import logging
import os
import threading
import time

from flask import Flask, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s warehouse %(message)s")


@app.get("/health")
def health():
    return jsonify({"service": "warehouse", "status": "UP"})


def consume_reservations() -> None:
    """TODO(ALUMNO-3): consumir INVENTORY_RESERVED y publicar estados."""
    while True:
        time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=consume_reservations, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5003")))

