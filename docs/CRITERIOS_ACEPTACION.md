# Criterios de aceptación

## Pedidos

- Crear, listar y consultar pedidos.
- Rechazar datos inválidos con HTTP 400.
- Devolver HTTP 404 para pedidos inexistentes.
- Guardar historial y publicar `ORDER_CREATED`.

## Inventario

- Seleccionar un almacén con disponibilidad.
- Evitar inventario negativo mediante transacción.
- Publicar reserva o rechazo.
- Ignorar un `event_id` procesado previamente.

## Almacén

- Procesar únicamente reservas aprobadas.
- Publicar `PREPARING` y `READY_FOR_DELIVERY`.
- Evitar procesamiento duplicado.

## Entrega

- Asignar conductor y vehículo.
- Publicar las etapas del recorrido.
- Terminar en `DELIVERED`.

## Infraestructura

- Levantar todo con un comando.
- Crear seis topics.
- Usar volumen persistente y variables de entorno.
- Proporcionar health checks y dead-letter topic.

## Frontend

- Crear pedidos y mostrar confirmación.
- Consultar historial mediante ID.
- Mostrar inventario, pedidos y salud de servicios.
- Funcionar en escritorio y celular.

## QA y documentación

- Manual técnico y de usuario unificado.
- Matriz de pruebas y evidencias reales.
- Instalación Windows/Linux y solución de problemas.
- Issues de defectos y prueba de aceptación final.

