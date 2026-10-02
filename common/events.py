"""Contrato mínimo para eventos. Completar sin romper el esquema JSON."""

from datetime import datetime, timezone
import re
from typing import Any
from uuid import UUID, uuid4


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
    """Valida un evento contra el contrato compartido del sistema."""
    if not isinstance(event, dict):
        raise ValueError("El evento debe ser un objeto JSON")

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

    extra = set(event).difference(required)
    if extra:
        raise ValueError(f"El evento contiene campos no permitidos: {sorted(extra)}")

    if not isinstance(event["event_id"], str):
        raise ValueError("event_id debe ser una cadena UUID")
    try:
        UUID(event["event_id"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("event_id debe ser una cadena UUID válida") from exc

    if not isinstance(event["event_type"], str) or len(event["event_type"]) < 3:
        raise ValueError("event_type debe ser una cadena de al menos 3 caracteres")

    if not isinstance(event["order_id"], str) or not re.fullmatch(r"PED-[0-9]{6}", event["order_id"]):
        raise ValueError("order_id debe tener el formato PED-000000")

    if not isinstance(event["source"], str) or len(event["source"]) < 2:
        raise ValueError("source debe ser una cadena de al menos 2 caracteres")

    if not isinstance(event["timestamp"], str):
        raise ValueError("timestamp debe ser una fecha ISO-8601")
    try:
        timestamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp debe ser una fecha ISO-8601 válida") from exc
    if timestamp.tzinfo is None:
        raise ValueError("timestamp debe incluir zona horaria")

    if type(event["version"]) is not int or event["version"] != 1:
        raise ValueError("Versión de evento no soportada")

    if not isinstance(event["payload"], dict):
        raise ValueError("payload debe ser un objeto JSON")
