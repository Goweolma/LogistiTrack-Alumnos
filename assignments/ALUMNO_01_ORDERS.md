# Alumno 1 — API de pedidos

Rama: `feat/orders-service`  
Ruta principal: `services/orders/`

## Debe demostrar

- `POST /api/orders` valida y registra.
- `GET /api/orders` lista pedidos.
- `GET /api/orders/{id}` incluye historial.
- Publica `ORDER_CREATED`.
- Devuelve errores 400 y 404 correctamente.
- `/health` responde.

## Mejora individual

Agregar cancelación de pedidos únicamente cuando todavía estén en `RECEIVED`.

