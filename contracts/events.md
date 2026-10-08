# Contrato de eventos

Todos los servicios deben respetar `event.schema.json`. Los nombres oficiales son:

| Topic | Evento | Productor | Consumidor |
|---|---|---|---|
| `orders` | `ORDER_CREATED` | orders | inventory |
| `inventory` | `INVENTORY_RESERVED`, `INVENTORY_REJECTED` | inventory | warehouse |
| `warehouse` | `ORDER_READY` | warehouse | delivery |
| `deliveries` | `ORDER_IN_TRANSIT`, `ORDER_DELIVERED` | delivery | extensiones |
| `order-status` | todos los cambios visibles | todos | dashboard/extensiones |
| `dead-letter` | `PROCESSING_FAILED` | todos | soporte |

Los cambios de contrato requieren Pull Request separado y aprobación del profesor.

## Sobre común (versión 1)

Esta sección documenta el código existente; no modifica el esquema ni los
nombres acordados. Fuente: `common/events.py` y los consumidores de `services/`.

| Campo | Restricción |
|---|---|
| `event_id` | Cadena UUID con guiones; identifica el evento para deduplicación. |
| `event_type` | Cadena de al menos tres caracteres. Los nombres oficiales siguen la tabla anterior. |
| `order_id` | `PED-` y seis dígitos. `PED-000000` se usa como diagnóstico cuando no hay ID válido. |
| `source` | Cadena de al menos dos caracteres. Identifica al emisor. |
| `timestamp` | Fecha ISO-8601 con zona horaria; el constructor genera UTC. |
| `version` | Entero `1` en el validador Python; rechaza booleanos. |
| `payload` | Objeto; sus campos de negocio los valida cada consumidor. |

Todos son obligatorios y no se admiten campos adicionales en el sobre. Ejemplo
ilustrativo (no es evidencia de un pedido creado por la API):

```json
{
  "event_id": "c087358e-176a-48c7-91b1-a4ace53287bd",
  "event_type": "ORDER_CREATED",
  "order_id": "PED-000001",
  "source": "orders",
  "timestamp": "2026-10-08T18:00:00+00:00",
  "version": 1,
  "payload": {"items": [{"product_id": "PROD-001", "quantity": 1}]}
}
```

## Payloads observados en el código

| Evento | Contenido de payload | Observaciones |
|---|---|---|
| `ORDER_CREATED` | `items`: lista de objetos con `product_id` cadena y `quantity` entero positivo. | Orders lo publica después de persistir; Inventory lo consume. |
| `INVENTORY_RESERVED` | `items`, `order_event_id`, `status`, `warehouse`. | `status=INVENTORY_RESERVED`; almacén `NORTE` o `SUR`. |
| `INVENTORY_REJECTED` | `items`, `order_event_id`, `status`, `reason`. | `reason=OUT_OF_STOCK`; Warehouse ignora el rechazo. |
| `PREPARING` | Copia del payload de reserva más `status`, `preparation_seconds`, `reservation_event_id`. | Se publica en `order-status`. |
| `READY_FOR_DELIVERY`, `ORDER_READY` | Copia del payload de reserva más `status=READY_FOR_DELIVERY`, `preparation_seconds`, `reservation_event_id`. | Dos sobres distintos: uno a `order-status`, otro a `warehouse`. |
| `DRIVER_ASSIGNED` | `status=DRIVER_ASSIGNED`, `driver_id`, `vehicle_id`. | `order-status`. |
| `ORDER_IN_TRANSIT` | `status=IN_TRANSIT`, `driver_id`, `vehicle_id`. | `order-status` y `deliveries`. |
| `NEAR_DESTINATION` | `status=NEAR_DESTINATION`, `driver_id`, `vehicle_id`. | `order-status`. |
| `ORDER_DELIVERED` | `status=DELIVERED`, `driver_id`, `vehicle_id`. | `order-status` y `deliveries`. |
| `PROCESSING_FAILED` por helper común | `error`, `original_event`. | Conserva el original; Inventory y Warehouse utilizan este helper. |
| `PROCESSING_FAILED` por Delivery | `reason`, `topic`, `partition`, `offset`. | Usa `PED-000000` y UUID determinista por posición; no conserva el original. |

Delivery solo necesita un sobre válido `ORDER_READY` para buscar el pedido
persistido; no usa las partidas del payload para asignar su flota.

## Consumo y garantías

| Grupo | Topic de entrada | Evento atendido |
|---|---|---|
| `inventory-service` | `orders` | `ORDER_CREATED` |
| `warehouse-service` | `inventory` | `INVENTORY_RESERVED` |
| `delivery-service` | `warehouse` | `ORDER_READY` |

Los consumidores confirman manualmente después de procesar y publicar.
Un fallo puede causar relectura: `processed_events` y los resultados
persistidos participan en la idempotencia. `earliest` se utiliza cuando el
grupo no tiene un offset válido, no reinicia el historial en cada arranque.

El frontend actual obtiene estados por REST; no existe una suscripción Kafka
del navegador a `order-status`. La columna dashboard/extensiones de la tabla
inicial expresa el destino previsto, no un consumidor ya implementado.

La publicación común comprueba callback y `flush`, pero no garantiza entrega
exactamente una vez ni orden global entre topics o particiones. Inventory
recupera el mismo evento de reserva; Delivery conserva UUID por pedido/etapa;
Warehouse conserva UUID por evento de reserva y tipo de salida al reintentar.

