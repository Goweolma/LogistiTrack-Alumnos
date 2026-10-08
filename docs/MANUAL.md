# Manual técnico y de usuario — LogistiTrack

Documento único de operación, APIs, eventos y pruebas. La plantilla vacía
sigue en `docs/PLANTILLA_MANUAL.md`. Este manual describe el estado real del
código: el alta ya persiste pedidos y publica `ORDER_CREATED`, y el navegador
consulta las APIs. El recorrido integrado aún requiere evidencia con Docker.

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
Nginx (frontend)
    ├── /api/orders, /api/products, /api/health  → orders:5001
    ├── /api/inventory                           → inventory:5002
    ├── /api/warehouse                           → warehouse:5003
    ├── /api/delivery                            → delivery:5004
    └── /api/services/<servicio>/health          → /health de ese servicio
            │
            ├── PostgreSQL
            └── Kafka: orders, inventory, warehouse, deliveries,
                       order-status, dead-letter
```

Los contenedores se encuentran por nombre en la red `logistitrack`. El
navegador no llama a los puertos 5001–5004: usa el mismo origen del tablero.

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

`ACCEPTANCE_BASE_URL` solo la usa `scripts/acceptance_flow.py`. Por defecto es
`http://localhost:8080`. No va en `.env`.

## 8. Manual de usuario

El tablero tiene cinco zonas: Salud, Nuevo pedido, Tablero, Seguimiento e
Inventario. En el celular el menú pasa a varias líneas y la tabla puede
desplazarse de lado.

1. Salud. El recuadro superior llama a `GET /api/health`. Las cuatro tarjetas
   llaman a `GET /api/services/<servicio>/health`. **Actualizar** repite esas
   lecturas y también pedidos, catálogo e inventario.
2. Nuevo pedido. Escribir la dirección (1 a 200 caracteres). Elegir producto
   y cantidad entera mayor que cero. **Agregar producto** suma otra línea del
   mismo producto en vez de repetirlo. **Crear pedido** envía:

   ```json
   {
     "delivery_address": "Avenida Universidad 100",
     "items": [{ "product_id": "PROD-001", "quantity": 1 }]
   }
   ```

   Si `GET /api/products` no trae catálogo, la lista se toma de
   `GET /api/inventory`. Si tampoco hay catálogo, se escribe el identificador
   a mano. La pantalla no guarda una lista fija de productos.
3. Tablero. Muestra `GET /api/orders`. La búsqueda y el filtro de estado se
   aplican en el navegador sobre esa lista. Pulsar el identificador abre el
   seguimiento.
4. Seguimiento. `GET /api/orders/{id}` pinta dirección, partidas e historial.
   El identificador tiene la forma `PED-000001`.
5. Inventario. `GET /api/inventory` separa las existencias de Norte y Sur.

El alta exitosa devuelve 201 y el ID del pedido. Si responde 503
`KAFKA_UNAVAILABLE`, el pedido ya quedó guardado: consultar el ID recibido antes
de repetir el alta, porque otro POST puede crear un segundo pedido. La pantalla
conserva el manejo de 501 `NOT_IMPLEMENTED` para versiones anteriores.

Almacén y reparto no publican hoy un listado REST. Su prefijo
(`/api/warehouse` y `/api/delivery`) ya está en Nginx para cuando lo agreguen.
Mientras tanto, su actividad se ve en la salud y, cuando el flujo exista, en
el estado y el historial del pedido.

## 9. API REST

Rutas vistas por el navegador en el puerto 8080. El proxy reenvía la ruta
completa.

### Pedidos (`orders`)

| Método y ruta | Respuesta actual |
|---|---|
| `GET /api/services/orders/health` | 200 `{"service":"orders","status":"UP"}`. Directamente en puerto 5001: `/health`. |
| `GET /api/health` | 200 `{"status":"BASE_READY","message":"..."}`. |
| `GET /api/products` | 200 y lista vacía. El catálogo de PostgreSQL todavía no sale por aquí. |
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
| `GET /api/warehouse` y `GET /api/delivery` | Prefijos reservados en Nginx. Esos servicios todavía no publican un listado. |

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
| Proxy del navegador | `tests/test_frontend_gateway.py`, `tests/test_frontend_api.py` | Cada servicio tiene prefijo y la pantalla llama esas rutas sin catálogo fijo. |
| Tablero sin APIs | Abrir el HTML servido y crear un pedido | El formulario muestra la falta de conexión y el JSON enviado. |
| Recorrido completo hasta `DELIVERED` | `python scripts/acceptance_flow.py` con la plataforma activa | Exige el historial ordenado hasta `DELIVERED`. Sin Docker sigue pendiente de evidencia. |

La aceptación se ejecuta con la plataforma levantada:

```powershell
python scripts/acceptance_flow.py
```

Sale 0 cuando el proxy, las lecturas, el rechazo 400 y el historial completo
hasta `DELIVERED` responden. Sale 1 si falta un servicio, el alta sigue en
501 `NOT_IMPLEMENTED`, el inventario rechaza el pedido o el historial no
completa el recorrido antes de `ACCEPTANCE_FLOW_TIMEOUT_SECONDS` (45 por
defecto). Un catálogo vacío en `GET /api/products` se imprime como pendiente
y no basta para aprobar.

Verificación local tras integrar `origin/develop` hasta `7501596`, el 8 de
octubre de 2026: **180 pruebas aprobadas y 1 omitida** en Python 3.11.9. La
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
2. `GET /api/products` responde una lista vacía.
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
| El catálogo pide el identificador a mano | `/api/products` está vacío y el inventario no respondió | Revisar `GET /api/inventory`. Se puede escribir `PROD-001`. |
| Tarjeta de servicio en error o sin API | El contenedor no responde en `/health` | `docker compose ps -a` y los logs de ese servicio. |
| El navegador no ve inventario | Nginx viejo mandaba todo `/api/` a pedidos | Reconstruir el frontend: `docker compose up -d --build frontend`. |
| Se perdieron los pedidos locales | Alguien ejecutó `docker compose down -v` | El volumen `postgres_data` se crea de nuevo con el `init.sql` actual. |

## 15. Aportaciones y alcance de esta revisión

Esta revisión es documental y no genera commits, pushes ni Pull Requests.
Los nombres de integrantes, institución, profesor y enlaces de entrega deben
completarse con los datos reales del equipo.

| Responsabilidad | Qué quedó listo |
|---|---|
| Alumno 5 | Funciones compartidas documentadas, contrato de eventos descrito, salud exigida en los siete servicios de larga duración y sonda `infrastructure/verify_runtime.py` para `dead-letter`. |
| Alumno 7 | Manual, guía técnica, matriz de QA y aceptación que espera `DELIVERED`. |

Los servicios de los alumnos 1–4, el frontend del alumno 6 y las secciones SQL
identificadas como aportaciones ajenas se conservan sin cambios.

El alta persistente y `ORDER_CREATED` llegaron desde `origin/develop` hasta
`7501596`, junto con la corrección de UUID estables de Warehouse. La fusión está
pendiente del commit del usuario. La salud de la plataforma y el desvío a
`dead-letter` ya se ejecutaron. El catálogo en `/api/products` sigue vacío y
el recorrido hasta `DELIVERED` no pudo demostrarse: el volumen PostgreSQL
vivo es anterior al `DEFAULT` de `orders.order_id`.
