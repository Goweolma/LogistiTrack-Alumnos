# Resultados de QA y pendientes de entrega

Fecha: 8 de octubre de 2026. Base: `origin/develop` en `4e707b9` (merge del
PR #48, catálogo leído de `products`). Esta entrega solo incluye archivos de
los alumnos 5 y 7. No modifica `frontend/` ni las APIs de otros módulos. El
pull 47 se devolvió por cambios de CSS; esas pantallas quedan comentadas en
`docs/NOTAS_PARA_FRONTEND.md`.

## Evidencia ejecutada

| Comprobación | Resultado observado | Interpretación |
|---|---|---|
| `python --version` | Python 3.11.9. | Entorno local Windows/PowerShell. |
| `python -m pytest -q` sobre `4e707b9` y estos cambios | `184 passed, 1 skipped`. | Suite local aprobada. No acredita sola el recorrido entregado. |
| `python scripts/health_platform.py` | Salida 0, repetida en esta rama. Ocho servicios correctos, volumen `logistitrack-alumnos_postgres_data`, cinco HTTP 200 y seis topics. | Salud de plataforma demostrada con Docker 29.7.2. |
| `infrastructure/verify_runtime.py` dentro de Orders | Salida 0. DNS interno, PostgreSQL y `PROCESSING_FAILED` `ac9545ba-cb40-449c-8028-a0f8fa6c1bb9` en `dead-letter`. | Evento inválido desviado sin crear pedidos. |
| `GET http://localhost:5001/api/products` en el contenedor ya en marcha | HTTP 200 y `[]`. | La imagen de Orders es anterior al PR #48. El código de `4e707b9` lee `products`. No se reconstruyó ese servicio. |
| `python scripts/acceptance_flow.py` por puertos publicados | Salida 1 en el alta: HTTP 503 `DATABASE_UNAVAILABLE`. El catálogo vacío quedó como pendiente. La alta inválida respondió 400. | El volumen vivo no tiene `DEFAULT` en `orders.order_id` ni la secuencia `order_number_seq`. No se borró ni se alteró. |
| Capturas en `docs/evidencias/` | Existen `interfaz-sin-api-escritorio.png` e `interfaz-sin-api-celular.png`. | Archivos previos, ignorados por Git. No muestran un pedido entregado. |

La prueba omitida es
`DeliveryPostgresTests.test_existing_schema_recovery_and_fleet_capacity`.
Requiere `DELIVERY_TEST_DATABASE_URL`: usa un esquema temporal y revierte sus
cambios, con Kafka simulado. No se configuró una base para ejecutarla aquí.

## Matriz de pruebas y cobertura

| Área | Archivos / procedimiento | Qué cubre | Qué queda fuera |
|---|---|---|---|
| Sobre y publicación | `test_events.py`, `test_infrastructure_events.py` | Campos, UUID, versión, rechazo, dead-letter y confirmación. | Entrega contra broker real. |
| Compose | `test_infrastructure_compose.py` | Credenciales por entorno, topics, red, healthchecks y CI. | Arranque real de imágenes. |
| Diagnóstico | `test_infrastructure_health.py` | JSON, contenedores ausentes, volumen, `healthy` de los siete servicios de larga duración, tareas one-off, errores HTTP y topics con dobles. | Estado real de Docker en esta sesión. |
| Orders | `test_orders.py` | Lista, detalle, historial, alta 201, persistencia, publicación, rollback y errores con dobles. | Persistencia y publicación contra PostgreSQL/Kafka reales. |
| Inventory | `test_inventory_schema.py`, `test_inventory_consumer.py` | Esquema, selección de almacén, reserva, rechazo, rollback, duplicados y fallos de publicación. | Reserva concurrente integral con servicios reales. |
| Warehouse | `test_warehouse.py` | Tiempo de preparación, transiciones, rechazo ignorado, duplicados y UUID estables al reintentar. | Recuperación integral tras caída real. |
| Delivery | `test_delivery.py` | Validación, etapas, recuperación, asignaciones y fallos con dobles. | La prueba PostgreSQL opcional quedó omitida; integración Kafka pendiente. |
| Frontend | `docs/NOTAS_PARA_FRONTEND.md` | Instrucciones comentadas: una página por función, componentes, enrutamiento y proxy. | Implementación. No entra en este pull. |
| Aceptación | `test_acceptance.py`, `scripts/acceptance_flow.py` | Un 501 no es un pedido creado. Solo el historial ordenado hasta `DELIVERED` cierra la prueba. | Ejecución HTTP contra Compose en esta sesión. |

Todos los archivos de prueba anteriores están en `tests/`. Sus resultados
automatizados corresponden a la suite indicada, no a una ejecución manual de
cada escenario con contenedores reales.

## Hallazgos listos para registrar como Issues

Estos identificadores son locales; no son números de Issues de GitHub.

| ID | Hallazgo y reproducción | Esperado / observado en código | Responsable y cierre |
|---|---|---|---|
| QA-01 | Enviar `POST /api/orders` con dirección y una partida válida. | El bloqueo 501 está corregido en `7501596`: persiste y publica; devuelve 201 o 503 si falla la infraestructura. | Corregido en código por Alumno 1; pendiente evidencia con servicios reales. |
| QA-02 | Consultar `GET /api/products` con la semilla de `products`. | En `4e707b9` la ruta lee PostgreSQL y devuelve `product_id`, `name`, `description` y `price`. No incluye existencias. Esta rama no cambia esa API. | Cerrado en código por el PR #48. Una imagen local anterior a ese merge puede seguir devolviendo `[]`. |
| QA-03 | `python scripts/acceptance_flow.py` con Compose en marcha. | Esperado: historial hasta `DELIVERED`. Observado: 503 porque `orders.order_id` del volumen vivo no tiene valor por defecto y no existe `order_number_seq`. | Infraestructura del volumen anterior a `init.sql`. Hace falta una base creada con el script actual. No ejecutar `down -v` sin aceptar la pérdida de datos. |
| QA-04 | Revisar evidencia de las cinco zonas del tablero con APIs activas. | Esperado: capturas reales de salud, alta, tablero, seguimiento e inventario. Actual: solo archivos previos descritos como interfaz sin API. | Alumno 7; adjuntar capturas y resultado del pedido real. |

Ejemplo del cuerpo para QA-01 (dato de demostración):

```json
{
  "delivery_address": "Avenida Universidad 100",
  "items": [{"product_id": "PROD-001", "quantity": 1}]
}
```

## Procedimiento de evidencia final

1. Iniciar el motor Docker y seguir la instalación del [manual](MANUAL.md).
2. Ejecutar `docker compose ps -a`, `python scripts/health_platform.py` y
   `python -m pytest -q`; registrar fecha, revisión Git, comandos y salida.
3. Ejecutar `python scripts/acceptance_flow.py`. La salida 0 exige el
   historial hasta `DELIVERED`. Guardar el ID impreso y la lista de estados.
4. Consultar el inventario del producto usado y comprobar que la reserva lo
   descontó. Un pedido sin existencia debe quedar en `INVENTORY_REJECTED` y
   no descontar.
5. Capturar salud, formulario/confirmación, tablero, seguimiento e inventario
   en escritorio y móvil. Anotar pedido y resultado junto a cada captura.
6. Registrar los defectos pendientes como Issues, adjuntar evidencia real y
   completar la portada y tabla de aportaciones con datos del equipo.

`docs/evidencias/` está ignorado por Git. Las imágenes pueden adjuntarse a la
entrega o PR; su existencia local no significa que estén en el repositorio.
No se modifica `.gitignore` ni se fuerzan archivos ignorados en esta revisión.
