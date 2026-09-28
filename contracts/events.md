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

