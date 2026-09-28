"""Contrato mínimo para eventos. Completar sin romper el esquema JSON."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def build_event(event_type: str, order_id: str, source: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Crea el sobre estándar que compartirán todos los servicios."""
    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "order_id": order_id,
        "version": 1,
        "payload": payload,
    }


def validate_event(event: dict[str, Any]) -> None:
    """TODO(ALUMNO-5): validar campos obligatorios y tipos."""
    required = {
        "event_id",
        "event_type",
        "timestamp",
        "source",
        "order_id",
        "version",
        "payload",
    }
    missing = required.difference(event)
    if missing:
        raise ValueError(f"Evento incompleto. Faltan: {sorted(missing)}")
    if event["version"] != 1:
        raise ValueError("Versión de evento no soportada")
    if not isinstance(event["payload"], dict):
        raise ValueError("payload debe ser un objeto JSON")
