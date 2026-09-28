# Alumno 2 — Inventario y PostgreSQL

Rama: `feat/inventory-service`  
Rutas: `services/inventory/` e `infrastructure/postgres/`

## Debe demostrar

- Reserva en Norte o Sur.
- No permite inventario negativo.
- Rechaza cuando no hay existencia.
- Usa transacción y bloqueo.
- Ignora un `event_id` repetido.
- Publica resultado e historial.

## Mejora individual

Implementar regla para escoger el almacén con mayor disponibilidad.

