"""Prueba de aceptación contra el frontend ya levantado.

Sale con 0 cuando el proxy y las lecturas responden y el alta queda creada
o bloqueada en 501. Sale con 1 si un chequeo obligatorio falla. Un 501 no
escribe pedidos.

Ejemplo:
    python scripts/acceptance_flow.py
    $env:ACCEPTANCE_BASE_URL = "http://localhost:8080"
"""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def classify_create(status: int, body: object) -> str:
    """Clasifica POST /api/orders sin tratar un 501 como pedido creado."""
    if status == 501 and isinstance(body, dict) and body.get("error") == "NOT_IMPLEMENTED":
        return "blocked"
    if status in (200, 201) and isinstance(body, dict) and isinstance(body.get("order_id"), str):
        return "created"
    return "failed"


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
        print("[BLOQUEADO] alta: POST /api/orders sigue en 501 NOT_IMPLEMENTED")
    elif outcome == "created":
        order_id = body["order_id"]
        print(f"[OK] alta: pedido {order_id}")
        status, detail_body = request_json("GET", f"{base}/api/orders/{order_id}")
        history = detail_body.get("history") if isinstance(detail_body, dict) else None
        check(
            "seguimiento",
            status == 200 and isinstance(history, list) and any(step.get("status") == "RECEIVED" for step in history if isinstance(step, dict)),
            f"HTTP {status}",
        )
    else:
        check("alta", False, f"HTTP {status} cuerpo={body}")

    if failures:
        print("Aceptacion incompleta: " + ", ".join(failures))
        return 1
    print("Aceptacion terminada. El alta bloqueada no cuenta como flujo de negocio cerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
