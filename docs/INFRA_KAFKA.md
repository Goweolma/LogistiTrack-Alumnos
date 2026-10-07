# Kafka: inicialización y confirmación de entrega — Alumno 5

## Cambios

- `compose.yaml`: `kafka-init` ejecuta `set -e` antes del bucle. Antes, un
  fallo al crear un topic podía quedar oculto si la última creación funcionaba.
  Se conserva un único argumento de `bash -c`, la espera por Kafka saludable,
  `--if-not-exists` y los seis topics del contrato.
- La red tiene el nombre explícito `logistitrack`. Antes Docker añadía el
  prefijo del proyecto al nombre real. Los puertos y DNS internos se conservan.
- `common/kafka_client.py`: `publish()` y `publish_dead_letter()` esperan
  confirmación del broker. Un timeout, rechazo o callback ausente produce
  `PublishError` (subclase de `RuntimeError`). Antes se ignoraba el resultado
  de `flush(5)` y el consumidor podía confirmar un offset sin entrega efectiva.
- `tests/test_infrastructure_events.py`: cubre los tres fallos tanto en el
  topic solicitado como en dead-letter. Los dobles simulan callbacks de entrega;
  las dependencias Kafka reales siguen instaladas.

No se cambian contratos, topics, grupos ni configuración de consumidores:
`earliest` y `enable.auto.commit=False`. No se editan servicios ni frontend.

## Validador

`validate_event` exige `event_id` con el formato `8-4-4-4-12` de
`contracts/event.schema.json` (`format: uuid`). Antes, `UUID()` aceptaba
valores sin guiones, con llaves o `urn:uuid:`, y `publish` los enviaba al
topic de negocio. Esas formas quedan solo en `dead-letter`. Las mayúsculas
siguen siendo válidas, igual que en el esquema. No se modifica `contracts/`:
un cambio de contrato pide otro Pull Request y la aprobación del profesor.

`version` sigue siendo el entero `1`. El `const: 1` del esquema también acepta
`1.0` por comparación numérica; Python lo rechaza antes de publicar. No se
afirma que el validador y el esquema sean equivalentes.

## Prueba reproducible (PowerShell o terminal Linux)

Antes del primer arranque, copiar `.env.example` a `.env` (`Copy-Item` en
PowerShell o `cp` en Linux). No sobrescribir una configuración local existente.
`POSTGRES_PASSWORD` y `DATABASE_URL` son obligatorios: Compose rechaza valores
ausentes o vacíos en vez de usar una contraseña incluida en el YAML. Mantener
ambos sincronizados; `.env.example` conserva solo valores de demostración.
Las variantes locales `.env.*` también se ignoran, salvo `.env.example`.

```text
python -m pip install -r requirements-dev.txt
python -m pytest -q
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
docker compose run --rm --no-deps kafka-init
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --list
python scripts/health_platform.py
```

La segunda ejecución de `kafka-init` debe terminar en 0 sin borrar datos.
Se esperan `orders`, `inventory`, `warehouse`, `deliveries`, `order-status`
y `dead-letter` (Kafka también puede mostrar topics internos).
`localhost` en healthchecks dentro del propio contenedor es correcto; entre
contenedores se usan `kafka`, `postgres` y los nombres de servicios.

## Evidencia del 7 de octubre de 2026

- Rama individual: 86 pruebas aprobadas en Python 3.11.9, sin fallos ni saltos.
- Combinada localmente con el PR de salud: 117 pruebas aprobadas en Python 3.12
  dentro de Docker, usando las dependencias reales de `requirements-dev.txt`.
- Compose válido, siete servicios activos y `kafka-init` terminado en 0.
- Se ejecutó nuevamente `kafka-init`: código 0 con los topics existentes.
- Prueba de fallo temprano en Bash: simulando error 42 al crear el primer topic,
  el script anterior retornó 0 y el corregido retornó 42. No se modificó el broker
  para esta prueba; se verificó también el argumento único del comando renderizado.
- Broker real: publicación válida confirmada y evento inválido recibido en
  `dead-letter` como `PROCESSING_FAILED`, con original y motivo conservados.
  Se usaron mensajes de diagnóstico con `PED-000000`, sin crear pedidos.
- Los seis topics existen. `__consumer_offsets` es un topic interno adicional.

## Límites y dependencias externas

La confirmación no convierte la publicación en exactamente una vez: un timeout
puede dejar un mensaje en tránsito y el reintento producir duplicados. Los
consumidores deben mantener su idempotencia. No se confirma el offset ante el
error de publicación. El cambio de nombre de red requiere que Compose recree
contenedores; no requiere eliminar `postgres_data`.

**BLOQUEADO POR DEPENDENCIA EXTERNA** para la demostración de negocio completa:

| Archivo | Problema y efecto | Cambio del responsable |
|---|---|---|
| `services/orders/app.py` | `POST /api/orders` devuelve 501 para pedidos válidos; no inicia el flujo. | Alumno 1: persistir pedido/historial y publicar `ORDER_CREATED`. |
| `services/orders/app.py` | `/api/products` devuelve una lista vacía fija. | Alumnos 1/2: integrar el catálogo persistido. |
| `services/delivery/app.py` | Usa columnas `orders.driver_id`, `orders.vehicle_id`, `order_history.event_id` y `order_history.event` ausentes en el DDL compartido. | Alumno 4 con alumnos 1/2: acordar y entregar la migración compatible; el propio módulo declara pendiente ese acuerdo. |

Estos problemas no se solucionan alterando APIs desde infraestructura. Un
healthcheck HTTP exitoso no demuestra que el recorrido de pedidos esté completo.
