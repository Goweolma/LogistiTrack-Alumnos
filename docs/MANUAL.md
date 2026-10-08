# Manual técnico y de usuario — LogistiTrack

Documento único de operación, APIs, eventos y pruebas. La plantilla vacía
sigue en `docs/PLANTILLA_MANUAL.md`. Este manual describe el estado real del
código: la plataforma arranca y el navegador ya llama a las APIs, pero el
alta de pedidos todavía no cierra el flujo de negocio.

Fecha de esta revisión: 8 de octubre de 2026.

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
| `DELIVERY_STEP_DELAY_SECONDS` | Espera entre etapas de reparto. Por defecto 2. |

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

Cuando el alta aún no está implementada, el botón no rompe la página: muestra
que la API respondió 501 y el cuerpo que ya se envió. Eso no crea un pedido.

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
| `GET /health` | 200 `{"service":"orders","status":"UP"}`. |
| `GET /api/health` | 200 `{"status":"BASE_READY","message":"..."}`. |
| `GET /api/products` | 200 y lista vacía. El catálogo de PostgreSQL todavía no sale por aquí. |
| `GET /api/orders` | 200 y lista de `order_id`, `total`, `created_at`, `delivery_address`, `status`. 503 `DATABASE_UNAVAILABLE` si la base falla. |
| `GET /api/orders/{id}` | 200 con `history` (`status`, `created_at`) e `items` (`product_id`, `quantity`). 404 `ORDER_NOT_FOUND`. 503 si la base falla. |
| `POST /api/orders` | 400 `{"error":"INVALID_ORDER","detail":"..."}` si el cuerpo no sirve. Un cuerpo válido recibe 501 `{"error":"NOT_IMPLEMENTED"}`: no guarda ni publica `ORDER_CREATED`. |

Detalles de validación del alta: `INVALID_JSON`, `INVALID_DELIVERY_ADDRESS`,
`INVALID_ITEMS`, `INVALID_ITEM`, `INVALID_PRODUCT_ID`, `INVALID_QUANTITY`,
`DUPLICATE_PRODUCT`.

### Inventario

| Método y ruta | Respuesta actual |
|---|---|
| `GET /health` | 200 `{"service":"inventory","status":"UP"}`. |
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
| `order-status` | cambios visibles, incluido `READY_FOR_DELIVERY` y las etapas de reparto | todos | tablero y extensiones |
| `dead-letter` | `PROCESSING_FAILED` | todos | soporte |

Inventario espera `payload.items` como lista de `product_id` y `quantity`.
El detalle de cada payload de negocio sigue en el servicio que lo publica.
Cambiar nombres de eventos pide otro Pull Request y la aprobación del profesor.
Este manual no modifica `contracts/`.

## 11. Base de datos

`infrastructure/postgres/init.sql` crea, si el volumen está vacío:

- `products`, `inventory` (Norte y Sur), `processed_events`.
- `inventory_reservations` para repetir el resultado de una reserva.
- `order_number_seq`, limitada a `PED-000001` … `PED-999999`.
- `orders` (`driver_id` y `vehicle_id` quedan vacíos hasta el reparto).
- `order_history` (`event_id` y `event` sirven para recuperar una publicación).
- `order_items`.

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
| Alta válida | `python scripts/acceptance_flow.py` | **Bloqueado:** HTTP 501 `NOT_IMPLEMENTED`. No es un pedido creado. |
| Lista y detalle de pedidos | `tests/test_orders.py` | Lista, historial, 404 y 503. |
| Inventario y reserva | `tests/test_inventory_schema.py`, `tests/test_inventory_consumer.py` | Esquema Norte/Sur, reserva, rechazo y `event_id` repetido. |
| Almacén y reparto | `tests/test_warehouse.py`, `tests/test_delivery.py` | Preparación y etapas hasta `DELIVERED` en sus pruebas. |
| Proxy del navegador | `tests/test_frontend_gateway.py`, `tests/test_frontend_api.py` | Cada servicio tiene prefijo y la pantalla llama esas rutas sin catálogo fijo. |
| Tablero sin APIs | Abrir el HTML servido y crear un pedido | El formulario muestra el 501 o la falta de conexión y enseña el JSON enviado. |
| Recorrido completo hasta `DELIVERED` | Aceptación, paso de seguimiento | **Pendiente** hasta que el alta deje de responder 501. |

La aceptación se ejecuta con la plataforma levantada:

```powershell
python scripts/acceptance_flow.py
```

Sale 0 si el proxy, las lecturas y el rechazo 400 responden, aunque el alta
válida siga bloqueada. Sale 1 si el frontend o un servicio obligatorio no
responde. Imprime `[BLOQUEADO]` en el 501 para que no se confunda con un
éxito de negocio.

En esta revisión el motor de Docker no estaba aceptando conexiones, así que
`health_platform.py` y `acceptance_flow.py` no se ejecutaron contra Compose.
La interfaz sí se abrió en un servidor estático, en escritorio y en un ancho
de 390 px. Esas capturas muestran el tablero cuando las APIs no responden;
no son la evidencia del pedido entregado.

- `docs/evidencias/interfaz-sin-api-escritorio.png`
- `docs/evidencias/interfaz-sin-api-celular.png`

`.gitignore` excluye `evidencias/`. Esas dos imágenes quedan en el disco local
y hay que adjuntarlas al Pull Request. No entran en el commit.

Los fallos que hay que abrir como Issues, sin cerrarlos con este documento:

1. `POST /api/orders` válido responde 501 y no publica `ORDER_CREATED`.
2. `GET /api/products` responde una lista vacía.
3. Faltan capturas del flujo completo con la plataforma en marcha.

## 13. Recuperación ante fallos

- Un evento inválido no entra al topic de negocio. Queda `PROCESSING_FAILED`
  en `dead-letter`, con el evento original y el motivo.
- `processed_events` guarda `event_id` y servicio para no aplicar dos veces la
  misma reserva, preparación o entrega.
- Los consumidores leen desde `earliest` y confirman el offset a mano.
- El historial de reparto puede volver a publicar una etapa después de una
  caída. La prueba de negocio de ese recorrido sigue en los tests de cada
  servicio; la aceptación de punta a punta espera a que el alta persista.

## 14. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Compose no conecta al motor | Docker Desktop abierto pero el motor Linux apagado | Arrancar el motor y repetir `docker compose ps`. No reiniciar la máquina sin confirmarlo. |
| Falta `POSTGRES_PASSWORD` o `DATABASE_URL` | No existe `.env` | Copiar `.env.example` a `.env`. |
| `kafka-init` no termina en 0 | Kafka aún no creó los seis topics | `docker compose logs kafka-init`. Recrear con `docker compose up -d --force-recreate` sin `-v`. |
| Pedidos responde 503 | La base no coincide con `init.sql` o no acepta conexiones | Revisar logs de `orders`. No borrar el volumen como primer paso. |
| El alta dice que la API no está implementada | El cuerpo es válido y el servicio responde 501 | Esperar el cierre de Alumno 1. El tablero ya envía el contrato. |
| El catálogo pide el identificador a mano | `/api/products` está vacío y el inventario no respondió | Revisar `GET /api/inventory`. Se puede escribir `PROD-001`. |
| Tarjeta de servicio en error o sin API | El contenedor no responde en `/health` | `docker compose ps -a` y los logs de ese servicio. |
| El navegador no ve inventario | Nginx viejo mandaba todo `/api/` a pedidos | Reconstruir el frontend: `docker compose up -d --build frontend`. |
| Se perdieron los pedidos locales | Alguien ejecutó `docker compose down -v` | El volumen `postgres_data` se crea de nuevo con el `init.sql` actual. |

## 15. Aportaciones de esta revisión

Rama de trabajo: `feat/api-front-connection`, en tres commits separados.

| Responsabilidad | Qué quedó listo |
|---|---|
| Alumno 5 | Nginx resuelve por nombre pedidos, inventario, almacén y reparto. La salud de los cuatro servicios sale por el mismo origen. El frontend espera a que esos contenedores existan. |
| Conexión con el front | Formulario, tablero con filtro, seguimiento, inventario por almacén y salud. El 501, el 404 y la caída de red se explican sin inventar pedidos. |
| Alumno 7 | Este manual, la matriz, los defectos para Issues y `scripts/acceptance_flow.py`. |

Siguen a cargo de otros módulos el alta persistente, la publicación de
`ORDER_CREATED`, el catálogo en `/api/products` y el recorrido completo hasta
`DELIVERED`.
