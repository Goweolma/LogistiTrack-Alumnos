"""Clientes Kafka, publicación confirmada y derivación de eventos inválidos.

La configuración usa KAFKA_BOOTSTRAP_SERVERS o kafka:9092. Los consumidores
administran sus offsets y cierre; este módulo no garantiza entrega única.
"""

import json
import os
import re

from confluent_kafka import Consumer, Producer

from common.events import build_event, validate_event


DEAD_LETTER_TOPIC = "dead-letter"


class PublishError(RuntimeError):
    """Kafka no confirmó la entrega; el consumidor no debe confirmar el offset."""


# Inventario y reparto todavía confirman con su propio produce/flush.
# Esos archivos son de otros alumnos: no se modifican en este cambio.
# Pueden delegar en este helper y conservar su excepción y sus pruebas.
#
# Inventario, services/inventory/app.py. Ya importa publish_dead_letter.
# Añadir PublishError as BrokerPublishError y publish_confirmed as confirm_publish.
# Sustituir solo el cuerpo de su publish_confirmed, con timeout=10:
#
#     def publish_confirmed(producer, topic: str, event: dict[str, Any]) -> None:
#         validate_event(event)
#         try:
#             confirm_publish(producer, topic, event, timeout=10)
#         except BrokerPublishError as exc:
#             raise PublishError(str(exc)) from exc
#
# Reparto, services/delivery/app.py. Importar PublishError y
# publish_confirmed as confirm_publish. Conservar la clave, RetryLater y el log:
#
#     def publish_confirmed(producer, topic, event):
#         try:
#             confirm_publish(
#                 producer,
#                 topic,
#                 event,
#                 key=event["order_id"].encode(),
#                 timeout=10,
#             )
#         except PublishError as exc:
#             raise RetryLater(str(exc)) from exc
#         log.info(
#             "Publicado %s pedido=%s event_id=%s topic=%s",
#             event["event_type"],
#             event["order_id"],
#             event["event_id"],
#             topic,
#         )
def publish_confirmed(
    producer: Producer,
    topic: str,
    event: dict,
    *,
    key: bytes | None = None,
    timeout: float = 5,
) -> None:
    """Serializa a JSON UTF-8 y espera callback y flush, hasta timeout segundos.

    key se pasa al productor cuando está presente. No valida el sobre ni hace
    reintentos. Lanza PublishError si quedan mensajes, falta confirmación o el
    callback informa un error; propaga errores de serialización y del cliente.
    Ante un fallo, el consumidor no debe confirmar el offset de entrada.
    """
    results = []
    payload = json.dumps(event).encode("utf-8")
    callback = lambda error, message: results.append(error)
    if key is None:
        producer.produce(topic, payload, on_delivery=callback)
    else:
        producer.produce(topic, payload, key=key, on_delivery=callback)
    remaining = producer.flush(timeout)
    if remaining or not results or results[0] is not None:
        raise PublishError(f"Kafka no confirmó la publicación en {topic}: {results or 'sin respuesta'}")


def create_producer() -> Producer:
    """Crea un productor; su construcción no demuestra conexión con el broker."""
    return Producer({"bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")})


def publish(producer: Producer, topic: str, event: dict) -> None:
    """Valida y publica, o desvía a dead-letter si falla la validación.

    Devuelve None también al desviar el mensaje: no implica publicación en el
    topic solicitado. Propaga fallos de entrega, incluso los de dead-letter.
    """
    try:
        validate_event(event)
    except (TypeError, ValueError) as exc:
        publish_dead_letter(producer, event, str(exc))
        return

    publish_confirmed(producer, topic, event)


def publish_dead_letter(
    producer: Producer,
    event: dict,
    reason: str,
    source: str = "infrastructure",
) -> None:
    """Envía PROCESSING_FAILED con payload.error y payload.original_event.

    Conserva order_id válido o usa PED-000000 como identificador de diagnóstico.
    Copia el original mediante JSON (objetos no serializables pasan a texto),
    valida el nuevo sobre y espera confirmación. No reintenta el topic original.
    """
    order_id = event.get("order_id") if isinstance(event, dict) else None
    if not isinstance(order_id, str) or not re.fullmatch(r"PED-[0-9]{6}", order_id):
        order_id = "PED-000000"

    original_event = json.loads(json.dumps(event, default=str))
    dead_letter_event = build_event(
        "PROCESSING_FAILED",
        order_id,
        source,
        {"error": reason, "original_event": original_event},
    )
    validate_event(dead_letter_event)
    publish_confirmed(producer, DEAD_LETTER_TOPIC, dead_letter_event)


def create_consumer(group_id: str, topics: list[str]) -> Consumer:
    """Crea y suscribe un consumidor del grupo con commit automático desactivado.

    earliest aplica cuando no hay offset utilizable para el grupo; no reinicia
    offsets existentes. El llamador hace poll, commit tras procesar y close.
    """
    consumer = Consumer(
        {
            "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(topics)
    return consumer
