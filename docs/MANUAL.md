# Manual técnico y de usuario — LogistiTrack

Documento único de operación, APIs, eventos y pruebas. La plantilla vacía
sigue en `docs/PLANTILLA_MANUAL.md`. Este manual describe el estado real del
código en `develop` `4e707b9`: el alta persiste pedidos y publica
`ORDER_CREATED`, y `GET /api/products` lee la tabla `products`. El navegador
en el puerto 8080 solo comprueba `GET /api/health`. El recorrido integrado
aún requiere evidencia con Docker.

Fecha de esta revisión: 8 de octubre de 2026.

Anexos: [guía del código](CODIGO_TECNICO.md), [contrato y payloads](../contracts/events.md)
y [resultados de QA](QA_RESULTADOS.md). Las rutas de los demás alumnos se
consultan para documentar su comportamiento, sin modificarlas.

## 1. Portada

Pendiente de la entrega del equipo: institución, materia, grupo, nombres de
los integrantes y profesor. No se inventan esos datos aquí.

Sistema: LogistiTrack, práctica de Sistemas Distribuidos. Repositorio
`Goweolma/LogistiTrack-Alumnos`, integración en `develop`.

## 2. Propósito del sistema

LogistiTrack registra un pedido, reserva inventario en el almacén Norte o
Sur, prepara la mercancía y publica las etapas del reparto hasta
`DELIVERED`. Quien opera el tablero crea el pedido y consulta su estado.
Los servicios se hablan por Kafka y guardan el estado en PostgreSQL.

## 3. Arquitectura

```text
Navegador :8080
    │
    ▼
Nginx (frontend), como está hoy en develop
    ├── /api/                 → orders:5001
    ├── /                     → index.html
    └── /frontend-health      → 200 ok
            │
            ├── PostgreSQL
            └── Kafka: orders, inventory, warehouse, deliveries,
                       order-status, dead-letter

Puertos publicados, usados por la aceptación mientras el alumno 6
no agrega prefijos:
    orders:5001  inventory:5002  warehouse:5003  delivery:5004
```

Los contenedores se encuentran por nombre en la red `logistitrack`. Hoy
Nginx reenvía todo `/api/` a pedidos, así que el navegador no llega a
inventario, almacén ni reparto. Esas consultas se hacen en los puertos
5002, 5003 y 5004. La página por función, los componentes y el proxy
quedan comentados en
[NOTAS_PARA_FRONTEND.md](NOTAS_PARA_FRONTEND.md).

Recorrido previsto:

```text
RECEIVED → INVENTORY_RESERVED → PREPARING → READY_FOR_DELIVERY
→ DRIVER_ASSIGNED → IN_TRANSIT → NEAR_DESTINATION → DELIVERED
```

`INVENTORY_REJECTED` termina el intento cuando no hay existencia. Un evento
inválido no se publica en su topic de negocio: se convierte en
`PROCESSING_FAILED` y va a `dead-letter`.

## 4. Requisitos

- Git.
- Docker Desktop en Windows, o Docker Engine y el complemento Compose en Linux.
- Unos 6 GB de memoria libre para la primera construcción.
- Python 3.12 en CI. En local también sirve 3.11 para pytest.
- No hace falta Node para ejecutar la plataforma. El tablero es HTML, CSS y
  JavaScript servido por Nginx.

## 5. Instalación en Windows

En PowerShell, desde una carpeta de trabajo:

```powershell
git clone https://github.com/Goweolma/LogistiTrack-Alumnos.git
cd LogistiTrack-Alumnos
git switch develop
git pull origin develop
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps -a
```

Abrir <http://localhost:8080>.

Comprobaciones:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts\health_platform.py
python scripts\acceptance_flow.py
```

Docker Desktop tiene que mostrar el motor en marcha. Si el tubo
`dockerDesktopLinuxEngine` no existe, Compose no puede arrancar: no es un
fallo del archivo `compose.yaml`.

## 6. Instalación en Linux

```bash
git clone https://github.com/Goweolma/LogistiTrack-Alumnos.git
cd LogistiTrack-Alumnos
git switch develop
git pull origin develop
cp .env.example .env
docker compose up -d --build
docker compose ps -a
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
python3 scripts/health_platform.py
python3 scripts/acceptance_flow.py
```

Abrir <http://localhost:8080>. El usuario debe poder hablar con el socket de
Docker.

## 7. Configuración

`.env.example` trae valores de demostración. Compose exige `POSTGRES_PASSWORD`
y `DATABASE_URL`. No se sube `.env`.

| Variable | Uso |
|---|---|
| `POSTGRES_DB` | Base. Demostración: `logistitrack`. |
| `POSTGRES_USER` | Usuario. Demostración: `logisti`. |
| `POSTGRES_PASSWORD` | Obligatoria. Tiene que coincidir con `DATABASE_URL`. |
| `DATABASE_URL` | Conexión interna, host `postgres` y puerto `5432`. |
| `KAFKA_BOOTSTRAP_SERVERS` | Por defecto `kafka:9092`. |
| `PREPARATION_DELAY_SECONDS` | Espera de preparación. Por defecto 3. |
| `DELIVERY_STEP_DELAY_SECONDS` | Espera entre etapas de reparto, entre 0 y 30 segundos. Por defecto 2. |

| Servicio | Puerto publicado | Dentro de la red |
|---|---:|---|
| Frontend | 8080 | 80 |
| Orders | 5001 | 5001 |
| Inventory | 5002 | 5002 |
| Warehouse | 5003 | 5003 |
| Delivery | 5004 | 5004 |
| PostgreSQL | 5433 | 5432 |
| Kafka | 9092 | 9092 |

`scripts/acceptance_flow.py` usa puertos publicados y no depende de rutas
nuevas de Nginx. `ACCEPTANCE_BASE_URL` apunta al frontend
(`http://localhost:8080`). `ACCEPTANCE_ORDERS_URL`,
`ACCEPTANCE_INVENTORY_URL`, `ACCEPTANCE_WAREHOUSE_URL` y
`ACCEPTANCE_DELIVERY_URL` apuntan a `5001`, `5002`, `5003` y `5004`. No van
en `.env`.

## 8. Manual de usuario

Hoy http://localhost:8080 muestra el estado de la plataforma con
`GET /api/health`. No hay páginas separadas de pedido, tablero, seguimiento
ni inventario: eso le corresponde al alumno 6. Los comentarios para
implementarlo, sin que esta rama toque CSS ni JavaScript, están en
[NOTAS_PARA_FRONTEND.md](NOTAS_PARA_FRONTEND.md).

Cuando esas páginas existan, el alta debe enviar:

   ```json
   {
     "delivery_address": "Avenida Universidad 100",
     "items": [{ "product_id": "PROD-001", "quantity": 1 }]
   }
   ```

El alta exitosa devuelve 201 y el identificador del pedido. Si responde 503
`KAFKA_UNAVAILABLE`, el pedido ya quedó guardado: consultar ese identificador
antes de repetir el alta. Una versión anterior respondía 501 `NOT_IMPLEMENTED`.
El seguimiento usa `GET /api/orders/{id}` y el identificador tiene la forma
`PED-000001`. El inventario público está en el puerto 5002,
`GET /api/inventory`. Nginx todavía no reenvía esa ruta.

## 9. API REST

Las rutas de negocio se consultan en el puerto de cada servicio. En el
navegador, Nginx solo reenvía `/api/` a pedidos. Las rutas
`/api/services/<servicio>/health` todavía no existen; el alumno 6 debe
agregarlas. La aceptación no las usa: llama a `/health` en los puertos
5001–5004.

### Pedidos (`orders`)

| Método y ruta | Respuesta actual |
|---|---|
| `GET /api/services/orders/health` | 200 `{"service":"orders","status":"UP"}`. Directamente en puerto 5001: `/health`. |
| `GET /api/health` | 200 `{"status":"BASE_READY","message":"..."}`. |
| `GET /api/products` | 200 y lista de `product_id`, `name`, `description` y `price`, leída de `products` desde `4e707b9`. 503 `DATABASE_UNAVAILABLE`. El stock Norte/Sur no viene aquí. |
| `GET /api/orders` | 200 y lista de `order_id`, `total`, `created_at`, `delivery_address`, `status`. 503 `DATABASE_UNAVAILABLE` si la base falla. |
| `GET /api/orders/{id}` | 200 con `history` (`status`, `created_at`) e `items` (`product_id`, `quantity`). 404 `ORDER_NOT_FOUND`. 503 si la base falla. |
| `POST /api/orders` | 201 con `order_id`, `status=RECEIVED`, `total` e `items` tras persistir y publicar `ORDER_CREATED`. 400 `INVALID_ORDER` si la entrada o el producto no sirven; 503 `DATABASE_UNAVAILABLE` si falla la persistencia o `KAFKA_UNAVAILABLE` con `order_id` si falla la publicación posterior. |

Detalles de validación del alta: `INVALID_JSON`, `INVALID_DELIVERY_ADDRESS`,
`INVALID_ITEMS`, `INVALID_ITEM`, `INVALID_PRODUCT_ID`, `INVALID_QUANTITY`,
`DUPLICATE_PRODUCT`, `PRODUCT_NOT_FOUND`.

### Inventario

| Método y ruta | Respuesta actual |
|---|---|
| `GET /api/services/inventory/health` | 200 `{"service":"inventory","status":"UP"}`. Directamente en puerto 5002: `/health`. |
| `GET /api/inventory` | 200 y lista con `product_id`, `name`, `description`, `price`, `stock` (`NORTE`, `SUR`) y `total`. 503 `DATABASE_UNAVAILABLE`. |
| `GET /api/inventory/{product_id}` | 200 con el mismo objeto, o 404 `PRODUCT_NOT_FOUND`. |

### Almacén y reparto

| Método y ruta | Respuesta actual |
|---|---|
| `GET /api/services/warehouse/health` | 200 si `status` es `UP`. Puede responder 503 con `DEGRADED` cuando Kafka no está conectado. |
| `GET /api/services/delivery/health` | 200 `{"service":"delivery","status":"UP"}`. |
| `GET /api/warehouse` y `GET /api/delivery` | Esos servicios no publican un listado. El proxy que las expondría está comentado para el alumno 6. |

### Salud del tablero

`GET /api/services/orders/health` y `GET /api/services/inventory/health`
equivalen a `GET /health` de cada servicio, no a `GET /api/health`.

## 10. Catálogo de eventos

El sobre es el de `contracts/event.schema.json`: `event_id`, `event_type`,
`timestamp` con zona horaria, `source`, `order_id` con forma `PED-000000`,
`version` entera `1` y `payload` objeto. `validate_event` rechaza el evento
antes de publicarlo en el topic de negocio.

| Topic | Evento | Productor | Consumidor |
|---|---|---|---|
| `orders` | `ORDER_CREATED` | orders | inventory |
| `inventory` | `INVENTORY_RESERVED`, `INVENTORY_REJECTED` | inventory | warehouse |
| `warehouse` | `ORDER_READY` | warehouse | delivery |
| `deliveries` | `ORDER_IN_TRANSIT`, `ORDER_DELIVERED` | delivery | extensiones |
| `order-status` | cambios visibles, incluido `READY_FOR_DELIVERY` y las etapas de reparto | servicios de negocio | extensiones; el tablero actual consulta REST, no Kafka |
| `dead-letter` | `PROCESSING_FAILED` | todos | soporte |

Inventario espera `payload.items` como lista de `product_id` y `quantity`.
El detalle de cada payload está en [el catálogo](../contracts/events.md),
contrastado con el servicio que lo publica. Cambiar nombres de eventos pide
otro Pull Request y la aprobación del profesor. Esta revisión documenta el
contrato existente sin cambiar nombres ni esquema.

## 11. Base de datos

`infrastructure/postgres/init.sql` crea, si el volumen está vacío:

- `products`, `inventory` (Norte y Sur), `processed_events`.
- `inventory_reservations` para repetir el resultado de una reserva.
- `order_number_seq`, limitada a `PED-000001` … `PED-999999`.
- `orders` (incluye `driver_id` y `vehicle_id` opcionales; Delivery no escribe
  esas columnas en su implementación actual).
- `order_history` (incluye `event_id` y `event` opcionales).
- `order_items`.

Delivery crea al iniciar `delivery_assignments` para conductor y vehículo,
y `delivery_events` para recuperar eventos persistidos. El historial visible
usa `order_history`; la recuperación del reparto usa `delivery_events`.

Datos de ejemplo: `PROD-001` Laptop empresarial, `PROD-002` Monitor 24
pulgadas, `PROD-003` Teclado mecánico, con existencias en Norte y Sur.

El script solo corre al crear el volumen `postgres_data`. Un volumen anterior
no recibe columnas nuevas. No usar `docker compose down -v` para “arreglarlo”:
borra los datos locales.

## 12. Pruebas

| Caso | Cómo se comprueba | Resultado esperado hoy |
|---|---|---|
| Compose, topics, salud y volumen | `python -m pytest -q` y `python scripts/health_platform.py` | Pytest en verde. El script de salud sale 0 con el motor de Docker en marcha. |
| Contrato de eventos inválido | `tests/test_events.py` y `tests/test_infrastructure_events.py` | `order_id` mal formado y el resto de campos inválidos no pasan `validate_event`. El inválido va a `dead-letter`. |
| Alta rechazada | `tests/test_orders.py` y el paso “alta invalida” de la aceptación | HTTP 400 e `INVALID_DELIVERY_ADDRESS` u otro `detail`. |
| Alta válida | `tests/test_orders.py` y `python scripts/acceptance_flow.py` | HTTP 201, persistencia y publicación. La aceptación sigue el historial. |
| Lista y detalle de pedidos | `tests/test_orders.py` | Lista, historial, 404 y 503. |
| Inventario y reserva | `tests/test_inventory_schema.py`, `tests/test_inventory_consumer.py` | Esquema Norte/Sur, reserva, rechazo y `event_id` repetido. |
| Almacén y reparto | `tests/test_warehouse.py`, `tests/test_delivery.py` | Preparación y etapas hasta `DELIVERED` en sus pruebas. |
| Proxy del navegador | `docs/NOTAS_PARA_FRONTEND.md` | Comentarios para el alumno 6. Esta rama no cambia `frontend/`. |
| Tablero | Abrir http://localhost:8080 | Hoy solo muestra la salud de `/api/health`. Las demás pantallas no están en este pull. |
| Recorrido completo hasta `DELIVERED` | `python scripts/acceptance_flow.py` con la plataforma activa | Exige el historial ordenado hasta `DELIVERED`. Sin Docker sigue pendiente de evidencia. |

La aceptación se ejecuta con la plataforma levantada:

```powershell
python scripts/acceptance_flow.py
```

Sale 0 cuando la salud en los puertos publicados, las lecturas, el rechazo
400 y el historial completo hasta `DELIVERED` responden. Sale 1 si falta un
servicio, el alta sigue en 501 `NOT_IMPLEMENTED`, el inventario rechaza el
pedido o el historial no completa el recorrido antes de
`ACCEPTANCE_FLOW_TIMEOUT_SECONDS` (45 por defecto). Un catálogo vacío en
`GET /api/products` se imprime como pendiente y no basta para aprobar.

Verificación local sobre `develop` `4e707b9`, el 8 de octubre de 2026:
**184 pruebas aprobadas y 1 omitida** en Python 3.11.9. La
omitida requiere `DELIVERY_TEST_DATABASE_URL`. Con Docker 29.7.2,
`health_platform.py` salió 0 y la sonda de `dead-letter` también.
`acceptance_flow.py` salió 1: el volumen PostgreSQL ya existente no tiene
`order_number_seq` ni un `DEFAULT` en `orders.order_id`, así que el alta
responde 503. No se borró el volumen.

Existen dos capturas locales de una revisión anterior, descritas como interfaz
sin API. No se generaron de nuevo ni acreditan un pedido entregado:

- `docs/evidencias/interfaz-sin-api-escritorio.png`
- `docs/evidencias/interfaz-sin-api-celular.png`

`.gitignore` excluye `evidencias/`. Esas dos imágenes quedan en el disco local
y hay que adjuntarlas al Pull Request. No entran en el commit.

Los hallazgos y pasos reproducibles para registrar Issues están en
[QA_RESULTADOS.md](QA_RESULTADOS.md). No se han creado Issues en esta revisión:

1. El alta integrada persiste en código, pero el volumen PostgreSQL vivo
   rechaza el `INSERT` porque `order_id` llega nulo. Hace falta una base
   creada con el `init.sql` actual.
2. Una imagen de Orders anterior al PR #48 puede seguir devolviendo
   `GET /api/products` vacío. En `develop` `4e707b9` esa ruta ya lee
   `products`. El stock sigue en inventario.
3. Faltan capturas del flujo completo con la plataforma en marcha.
4. Falta ejecutar la aceptación contra Compose y guardar la salida del pedido
   que llegue a `DELIVERED`.

## 13. Recuperación ante fallos

- Un evento inválido no entra al topic de negocio. Queda `PROCESSING_FAILED`
  en `dead-letter`, con el evento original y el motivo.
- `processed_events` guarda `event_id` y servicio para no aplicar dos veces la
  misma reserva, preparación o entrega.
- Los consumidores leen desde `earliest` y confirman el offset a mano.
- `delivery_events` permite volver a publicar una etapa después de una
  caída. La aceptación de punta a punta espera el historial hasta
  `DELIVERED` y falla si el recorrido se corta.

## 14. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Compose no conecta al motor | Docker Desktop abierto pero el motor Linux apagado | Arrancar el motor y repetir `docker compose ps`. No reiniciar la máquina sin confirmarlo. |
| Falta `POSTGRES_PASSWORD` o `DATABASE_URL` | No existe `.env` | Copiar `.env.example` a `.env`. |
| `kafka-init` no termina en 0 | Kafka aún no creó los seis topics | `docker compose logs kafka-init`. Recrear con `docker compose up -d --force-recreate` sin `-v`. |
| Pedidos responde 503 `DATABASE_UNAVAILABLE` al crear | El volumen es anterior a `init.sql`: `orders.order_id` no tiene `DEFAULT` y falta `order_number_seq` | Confirmarlo en los logs. Una base nueva exige `docker compose down -v` y borra los datos locales. No es el primer paso si hay pedidos que conservar. |
| El alta dice que la API no está implementada | Se está ejecutando una imagen anterior del servicio | Reconstruir Orders con `docker compose up -d --build orders`. |
| El alta devuelve `KAFKA_UNAVAILABLE` y un ID | Pedido guardado, publicación no confirmada | Consultar ese ID y los logs de Orders/Kafka antes de repetir el POST. |
| El formulario no muestra productos | La imagen de Orders es anterior al PR #48, o PostgreSQL no responde | Probar `GET http://localhost:5001/api/products`. Un 200 con lista llena el formulario. Un 503 es fallo de base. `PROD-001` solo sirve si el inventario del puerto 5002 respondió. |
| Tarjeta de servicio en error o sin API | El contenedor no responde en `/health` | `docker compose ps -a` y los logs de ese servicio. |
| El navegador no ve inventario | Nginx manda todo `/api/` a pedidos | El alumno 6 debe agregar el prefijo. Mientras tanto, `http://localhost:5002/api/inventory`. |
| Se perdieron los pedidos locales | Alguien ejecutó `docker compose down -v` | El volumen `postgres_data` se crea de nuevo con el `init.sql` actual. |

## 15. Aportaciones y alcance de esta revisión

Los nombres de integrantes, institución, profesor y enlaces de entrega deben
completarse con los datos reales del equipo. Esta rama parte de `develop`
`4e707b9` y no modifica `frontend/` ni los servicios de otros alumnos.

| Responsabilidad | Qué quedó listo |
|---|---|
| Alumno 5 | Funciones compartidas documentadas, contrato de eventos descrito, salud exigida en los siete servicios de larga duración y sonda `infrastructure/verify_runtime.py` para `dead-letter`. |
| Alumno 7 | Manual, guía técnica, matriz de QA, aceptación por puertos publicados y comentarios para el frontend. |

Los servicios de los alumnos 1–4, el frontend del alumno 6 y las secciones SQL
identificadas como aportaciones ajenas se conservan sin cambios.

`develop` ya incluye el alta persistente, `ORDER_CREATED`, el catálogo leído
de `products` (`4e707b9`, PR #48) y la elección de almacén por mayor
disponibilidad (`4592036`). La salud de la plataforma y el desvío a
`dead-letter` se ejecutaron sobre Docker local. El recorrido hasta
`DELIVERED` no pudo demostrarse: el volumen PostgreSQL vivo es anterior al
`DEFAULT` de `orders.order_id`.
