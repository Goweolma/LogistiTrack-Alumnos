# Diagnóstico de plataforma — Alumno 5

`python scripts/health_platform.py` verifica los ocho servicios, PostgreSQL,
Kafka y Orders saludables, `kafka-init` terminado con código 0, el volumen real,
cinco endpoints HTTP y los seis topics del contrato. Devuelve **0** si todo
pasa y **1** ante cualquier fallo. No crea pedidos ni modifica las APIs.

## Correcciones

| Archivo | Problema | Cambio y justificación |
|---|---|---|
| `scripts/health_platform.py` | Cualquier texto en `Mounts` se aceptaba como persistencia, incluso el bind de `init.sql`. | Inspecciona tipo `volume`, destino `/var/lib/postgresql/data`, escritura y etiqueta Compose `postgres_data`. |
| `scripts/health_platform.py` | Solo aceptaba JSON por línea y dependía del directorio actual. | También admite arrays JSON y ejecuta Docker desde la raíz calculada a partir de `__file__`. |
| `scripts/health_platform.py` | Docker ausente causaba traceback; un comando podía bloquear indefinidamente. | Diagnóstico explícito y límite de 45 segundos por comando. Los fallos siguen produciendo código 1. |
| `scripts/health_platform.py` | Servicios ausentes impedían revisar el resto; no distinguía responsabilidades. | Continúa las comprobaciones y separa infraestructura de servicios externos. |
| `tests/test_infrastructure_health.py` | No había regresiones del script. | Prueba formatos Compose, volumen incorrecto, healthchecks, código de kafka-init, Docker ausente, timeout, HTTP, topics y código de salida. |

## Ejecutar

```text
python -m pip install -r requirements-dev.txt
python -m pytest -q
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
python scripts/health_platform.py
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --list
```

En Linux también puede usarse `python3`. Puede ejecutarse el script por ruta
absoluta desde otra carpeta. No necesita librerías Python adicionales.

Los endpoints predeterminados usan `localhost` porque el script se ejecuta en
el host, fuera de Docker. Se pueden sustituir por variables **del proceso**:
`PLATFORM_FRONTEND_HEALTH_URL`, `PLATFORM_ORDERS_HEALTH_URL`,
`PLATFORM_INVENTORY_HEALTH_URL`, `PLATFORM_WAREHOUSE_HEALTH_URL` y
`PLATFORM_DELIVERY_HEALTH_URL`. El script no carga `.env`.

```powershell
$env:PLATFORM_ORDERS_HEALTH_URL = 'http://localhost:5001/health'
python scripts/health_platform.py
$LASTEXITCODE
```

## Interpretar resultados

- `[ERROR] INFRAESTRUCTURA`: revisar Docker, PostgreSQL, Kafka, inicialización,
  topics o volumen. Docker debe estar instalado y el motor iniciado.
- `[ERROR] BLOQUEADO POR DEPENDENCIA EXTERNA`: un servicio de otro alumno está
  ausente, detenido o falla por HTTP/healthcheck. Revisar primero si hay un
  fallo de infraestructura que explique el síntoma y después sus logs. La
  categoría identifica el módulo afectado, no prueba la causa del error.
- `[OK]`: la comprobación puntual pasó. Salud HTTP no demuestra que productores,
  consumidores o el flujo completo de negocio estén implementados.

No se elimina ningún volumen. Para una red desactualizada al aplicar cambios
de Compose, `docker compose up -d --force-recreate` recrea contenedores y conserva
`postgres_data`. No ejecutar `docker compose down -v` para esta comprobación.

La prueba de negocio permanece **BLOQUEADA POR DEPENDENCIA EXTERNA**: Orders debe
persistir/publicar pedidos (actualmente devuelve 501) y Delivery debe acordar
con los responsables de pedidos las columnas adicionales descritas al comienzo
de `services/delivery/app.py`. Este PR no modifica esos archivos ni el DDL.
