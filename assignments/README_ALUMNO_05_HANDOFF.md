# Entrega y handoff — Alumno 5

Este documento resume el trabajo de infraestructura e integración de LogistiTrack para que otro integrante pueda continuar sin repetir cambios ni mezclar ramas viejas.

## Estado actual

La responsabilidad de Alumno 5 quedó integrada en `develop`.

El último cambio fue el PR [#25](https://github.com/Goweolma/LogistiTrack-Alumnos/pull/25), ya fusionado:

- Rama: `feat/infrastructure-ci-updated`
- Destino: `develop`
- Commit de la corrección CI: `ba8b6ee`
- Resultado de pruebas: `21 passed`

Las ramas anteriores de infraestructura ya no deben usarse para trabajo nuevo:

- PR #2: corrigió `kafka-init`.
- PR #3: agregó validación de eventos y salud de plataforma.
- PR #7: integró las pruebas/revisiones de infraestructura a `develop`.
- PR #24: quedó cerrado por conflictos históricos y fue reemplazado por el PR #25.

## Qué se implementó

### Compose, Kafka y PostgreSQL

En `compose.yaml`:

- Kafka corre como broker y controller KRaft.
- PostgreSQL usa el volumen persistente `postgres_data`.
- Todos los contenedores comparten la red Docker `logistitrack`.
- Los servicios se encuentran por nombre (`kafka`, `postgres`, `orders`, etc.).
- Kafka tiene healthcheck y PostgreSQL tiene healthcheck.
- `kafka-init` espera a Kafka saludable y crea los seis topics.
- `kafka-init` debe terminar con `Exited (0)`.
- El comando de `kafka-init` se conserva como un único argumento para `bash -c`; no separar `--create` de `--if-not-exists` en líneas distintas.

Topics esperados:

```text
orders
inventory
warehouse
deliveries
order-status
dead-letter
```

### Variables de entorno

La configuración usa `.env.example` y variables de Compose:

- `DATABASE_URL`
- `KAFKA_BOOTSTRAP_SERVERS`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `PREPARATION_DELAY_SECONDS`
- `DELIVERY_STEP_DELAY_SECONDS`

No subir `.env`, contraseñas reales ni tokens. `.env.example` solo contiene valores de demostración.

### Contratos y eventos

En `common/events.py`, `validate_event` comprueba:

- campos obligatorios;
- ausencia de campos desconocidos;
- `event_id` como UUID;
- `event_type` con longitud válida;
- `order_id` con formato `PED-000000`;
- `source` válido;
- `timestamp` ISO-8601 con zona horaria;
- `version == 1`;
- `payload` como objeto JSON.

En `common/kafka_client.py`:

- `publish` valida antes de publicar;
- un evento inválido no se publica en su topic original;
- se genera `PROCESSING_FAILED` y se publica en `dead-letter`;
- los consumidores comienzan desde `earliest` y no hacen commit automático;
- `publish_dead_letter` conserva el evento original y la razón del error.

Los nombres de topics y eventos están documentados en `contracts/events.md`, y el esquema está en `contracts/event.schema.json`.

### Script de salud

`python3 scripts/health_platform.py` comprueba automáticamente:

- que existan los ocho servicios de Compose;
- que los servicios estén `running`;
- que PostgreSQL, Kafka y Orders estén `healthy`;
- que `kafka-init` termine con código 0;
- que el volumen de PostgreSQL esté montado;
- que los endpoints HTTP respondan;
- que existan los seis topics de Kafka.

### CI y pytest

`.github/workflows/tests.yml` se ejecuta en pushes y Pull Requests hacia `develop`.

El workflow:

1. usa Python 3.12;
2. instala `requirements-dev.txt`;
3. ejecuta `python -m pytest -q`.

`requirements-dev.txt` incluye todas las dependencias necesarias para recolectar las pruebas actuales:

- `pytest`
- `jsonschema`
- `requests`
- `Flask`
- `psycopg[binary]`
- `confluent-kafka`

No se usan stubs artificiales para ocultar dependencias faltantes.

## Cómo continuar desde una copia actualizada

Siempre partir de `develop`:

```bash
git fetch origin
git switch develop
git pull --ff-only origin develop
```

Para trabajo nuevo, crear una rama con base en ese `develop`:

```bash
git switch -c feat/infrastructure-nombre
```

Los Pull Requests nuevos deben apuntar a `develop`, no a `main` ni a ramas antiguas de infraestructura.

## Pruebas locales

Instalar dependencias y correr pytest:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Resultado esperado actual:

```text
21 passed
```

Levantar la plataforma:

```bash
docker compose up -d --build
docker compose ps -a
python3 scripts/health_platform.py
```

Resultado esperado:

- PostgreSQL: `running`, health `healthy`.
- Kafka: `running`, health `healthy`.
- `kafka-init`: `exited`, exit code `0`.
- Orders, Inventory, Warehouse, Delivery y Frontend: `running`.
- Los endpoints responden HTTP 200.
- Los seis topics existen.

Para una prueba completamente limpia se puede usar:

```bash
docker compose down -v
docker compose up -d --build
```

`down -v` elimina el volumen local `postgres_data` y borra los datos locales de PostgreSQL; usarlo solo cuando se quiera reiniciar la base desde cero.

## Límites de alcance

No modificar sin autorización:

- `services/orders/`;
- `services/inventory/`;
- `services/warehouse/`;
- `services/delivery/`;
- `frontend/`;
- archivos de otros alumnos.

La infraestructura debe integrarse mediante `compose.yaml`, `common/`, `contracts/`, `infrastructure/`, los scripts propios y las pruebas de CI.

El archivo `LogistiTrack_Arquitectura_Visual (1).drawio.pdf` es material de referencia local y no debe agregarse al commit si aparece como archivo no rastreado.

## Checklist de mantenimiento

- [ ] Partir de `develop` actualizado.
- [ ] No incluir `.env`, contraseñas ni tokens.
- [ ] Ejecutar `python -m pytest -q`.
- [ ] Ejecutar `python3 scripts/health_platform.py` si Docker está disponible.
- [ ] Confirmar que `kafka-init` termine en 0.
- [ ] Confirmar que los seis topics sigan existiendo.
- [ ] Crear el PR con base `develop`.
