"""Prueba de aceptación contra el frontend ya levantado.

Sale con 0 solo si las lecturas responden, el alta devuelve un pedido y el
historial recorre hasta DELIVERED. Un 501 o un recorrido a medias sale con 1.

Ejemplo:
    python scripts/acceptance_flow.py
    $env:ACCEPTANCE_BASE_URL = "http://localhost:8080"
    $env:ACCEPTANCE_FLOW_TIMEOUT_SECONDS = "45"
"""

from __future__ import annotations

import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


EXPECTED_FLOW = (
    "RECEIVED",
    "INVENTORY_RESERVED",
    "PREPARING",
    "READY_FOR_DELIVERY",
    "DRIVER_ASSIGNED",
    "IN_TRANSIT",
    "NEAR_DESTINATION",
    "DELIVERED",
)


def classify_create(status: int, body: object) -> str:
    """Clasifica POST /api/orders sin tratar un 501 como pedido creado."""
    if status == 501 and isinstance(body, dict) and body.get("error") == "NOT_IMPLEMENTED":
        return "blocked"
    if status in (200, 201) and isinstance(body, dict) and isinstance(body.get("order_id"), str):
        return "created"
    return "failed"


def flow_statuses(history: object) -> list[str] | None:
    """Extrae los estados del historial. None si el cuerpo no tiene esa forma."""
    if not isinstance(history, list):
        return None
    statuses = []
    for step in history:
        if not isinstance(step, dict) or not isinstance(step.get("status"), str) or not step["status"]:
            return None
        statuses.append(step["status"])
    return statuses


def classify_flow(statuses: list[str] | None) -> str:
    """Compara el historial con el recorrido oficial, sin saltos ni rechazos."""
    if statuses is None:
        return "invalid"
    expected = list(EXPECTED_FLOW)
    if statuses == expected:
        return "complete"
    if statuses == expected[: len(statuses)]:
        return "in_progress"
    if "INVENTORY_REJECTED" in statuses:
        return "rejected"
    return "diverged"


def _decode(raw: str) -> object:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def request_json(method: str, url: str, payload: dict | None = None, timeout: float = 5):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, _decode(response.read().decode())
    except HTTPError as exc:
        return exc.code, _decode(exc.read().decode())
    except (URLError, TimeoutError) as exc:
        return 0, {"error": str(exc)}


def main() -> int:
    base = os.environ.get("ACCEPTANCE_BASE_URL", "http://localhost:8080").rstrip("/")
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str) -> None:
        print(f"[{'OK' if ok else 'ERROR'}] {name}: {detail}")
        if not ok:
            failures.append(name)

    status, body = request_json("GET", f"{base}/frontend-health")
    check("frontend", status == 200, f"HTTP {status}")

    for service in ("orders", "inventory", "warehouse", "delivery"):
        status, body = request_json("GET", f"{base}/api/services/{service}/health")
        reported = body.get("status") if isinstance(body, dict) else None
        check(
            f"salud {service}",
            status == 200 and reported in {"UP", "BASE_READY"},
            f"HTTP {status} status={reported}",
        )

    status, body = request_json("GET", f"{base}/api/orders")
    check("lista de pedidos", status == 200 and isinstance(body, list), f"HTTP {status}")

    status, body = request_json("GET", f"{base}/api/inventory")
    check("inventario", status == 200 and isinstance(body, list), f"HTTP {status}")

    status, body = request_json("GET", f"{base}/api/products")
    if status == 200 and body == []:
        print("[PENDIENTE] catalogo: GET /api/products devuelve una lista vacia")
    else:
        check("catalogo", status == 200 and isinstance(body, list), f"HTTP {status}")

    status, body = request_json(
        "POST",
        f"{base}/api/orders",
        {"delivery_address": "", "items": []},
    )
    detail = body.get("detail") if isinstance(body, dict) else None
    check("alta invalida", status == 400 and detail == "INVALID_DELIVERY_ADDRESS", f"HTTP {status} detail={detail}")

    payload = {
        "delivery_address": "Avenida Universidad 100",
        "items": [{"product_id": "PROD-001", "quantity": 1}],
    }
    status, body = request_json("POST", f"{base}/api/orders", payload)
    outcome = classify_create(status, body)
    if outcome == "blocked":
        check("alta", False, "HTTP 501 NOT_IMPLEMENTED")
    elif outcome != "created":
        check("alta", False, f"HTTP {status} cuerpo={body}")
    else:
        order_id = body["order_id"]
        print(f"[OK] alta: pedido {order_id}")
        timeout = float(os.environ.get("ACCEPTANCE_FLOW_TIMEOUT_SECONDS", "45"))
        deadline = time.monotonic() + timeout
        while True:
            status, detail_body = request_json("GET", f"{base}/api/orders/{order_id}")
            history = detail_body.get("history") if isinstance(detail_body, dict) else None
            statuses = flow_statuses(history)
            progress = classify_flow(statuses) if status == 200 else "invalid"
            seen = ",".join(statuses or [])
            if progress == "complete":
                check("seguimiento", True, order_id)
                break
            if progress != "in_progress" or time.monotonic() >= deadline:
                check("seguimiento", False, f"HTTP {status} historial={seen or progress}")
                break
            time.sleep(2)

    if failures:
        print("Aceptacion incompleta: " + ", ".join(failures))
        return 1
    print("Aceptacion terminada: el pedido llego a DELIVERED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
