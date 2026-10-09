"""Construcción y validación del sobre de contracts/event.schema.json."""

from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4


def build_event(event_type: str, order_id: str, source: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Devuelve un sobre versión 1 con UUID nuevo y fecha UTC con zona horaria.

    No valida los argumentos ni copia payload: conserva el diccionario recibido.
    El emisor debe validar el resultado antes de publicarlo.
    """
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
    """Comprueba campos y tipos del sobre; retorna None o lanza ValueError.

    Rechaza campos adicionales, UUID sin guiones, fechas sin zona y versiones
    distintas del entero 1 (incluido True). Solo comprueba que payload sea un
    diccionario: cada servicio valida su contenido de negocio. No comprueba
    existencia del pedido, nombres oficiales de eventos ni serialización JSON.
    """
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

    # El esquema exige format: uuid (8-4-4-4-12). UUID() también acepta formas
    # sin guiones, con llaves o urn:uuid, y esas no deben publicarse.
    if not isinstance(event["event_id"], str) or re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        event["event_id"],
    ) is None:
        raise ValueError("event_id debe ser un UUID con guiones, como exige el esquema")

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
