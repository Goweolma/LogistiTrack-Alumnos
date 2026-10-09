# Kafka: inicialización y confirmación de entrega — Alumno 5

## Cambios

- `compose.yaml`: `kafka-init` ejecuta `set -e` antes del bucle. Antes, un
  fallo al crear un topic podía quedar oculto si la última creación funcionaba.
  Se conserva un único argumento de `bash -c`, la espera por Kafka saludable,
  `--if-not-exists` y los seis topics del contrato.
- La red tiene el nombre explícito `logistitrack`. Antes Docker añadía el
  prefijo del proyecto al nombre real. Los puertos y DNS internos se conservan.
- `common/kafka_client.py`: `publish_confirmed()` es el helper común.
  `publish()` y `publish_dead_letter()` lo usan. Un timeout, rechazo o
  callback ausente produce `PublishError` (subclase de `RuntimeError`).
  Inventario y reparto no se editan. El reemplazo queda comentado en
  `common/kafka_client.py` para que cada alumno lo aplique en su servicio
  y conserve `PublishError` o `RetryLater`.
- `.github/workflows/tests.yml`: además de pytest, el job `compose` copia
  `.env.example` a `.env`, valida la configuración y arranca la plataforma.
  No se sube `.env`.
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

## Versiones

Los pines compartidos de `requirements-dev.txt`, pedidos, almacén y reparto
son `Flask==3.1.0`, `psycopg[binary]==3.2.3` y `confluent-kafka==2.6.1`.
Inventario declara `Flask==3.1.3`, `psycopg[binary]==3.3.6` y
`confluent-kafka==2.15.1`. No se modifica
`services/inventory/requirements.txt`: lo alinea el alumno de inventario
cuando le corresponda. No se sube al resto a `2.15.1`.

Postgres, Kafka, `kafka-init`, las cuatro APIs y el frontend tienen healthcheck.
Las APIs consultan su propio `localhost`. `kafka-init` consulta `kafka:9092`
mientras crea los topics; su éxito de arranque sigue siendo terminar con código 0.
Entre contenedores se usan `kafka`, `postgres`, `inventory`, `warehouse` y `delivery`.

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

- Rehecho sobre `develop` en `895d17b` (incluye el PR #42 de reparto).
  `python -m pytest -q`: 146 aprobadas y 1 omitida. `docker compose config --quiet` válido.
  No se modifican `services/` ni `frontend/`.
- Rama individual anterior: 86 pruebas aprobadas en Python 3.11.9, sin fallos ni saltos.
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
| `services/orders/app.py` | `POST /api/orders` persiste y publica desde `7501596`. Responde 201, o 503 si falla la base o Kafka. | Resuelto por el alumno 1. Infraestructura no modifica esa API. |
| `services/orders/app.py` | `GET /api/products` lee `products` desde `4e707b9`. No incluye existencias. | Resuelto por el PR #48. Infraestructura no modifica esa API. |
| `services/inventory/app.py` y `services/delivery/app.py` | Cada uno repite `produce` y `flush`. El helper común ya confirma, también en dead-letter. | Alumno de inventario y alumno de reparto: aplicar el comentario de `common/kafka_client.py`. Conservar `PublishError`, `RetryLater`, la clave `order_id` y el timeout de 10 s. |
| `services/inventory/requirements.txt` | Pines distintos al resto: Flask 3.1.3, psycopg 3.3.6, confluent-kafka 2.15.1. | Alumno de inventario: igualar a Flask 3.1.0, psycopg 3.2.3 y confluent-kafka 2.6.1. |

Estos problemas no se solucionan alterando APIs desde infraestructura. Un
healthcheck HTTP exitoso no demuestra que el recorrido de pedidos esté completo.
