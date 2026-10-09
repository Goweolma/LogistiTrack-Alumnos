# Comentarios para el alumno 6 — no aplicarlos en esta rama

Esta rama es de los alumnos 5 y 7. No modifica `frontend/`, `services/` ni
las APIs. El pull anterior se devolvió porque cambió CSS. Aquí solo queda
la instrucción para que la persona de frontend, o su asistente, la aplique
en `feat/frontend-dashboard`.

No copiar archivos de `feat/api-front-connection` ni del pull request 47.
Ese cambio de estilos fue el motivo del rechazo. Rehacer la interfaz con
una página por función, componentes y enrutamiento.

## Qué hay hoy en develop

`frontend/index.html` es una sola página. Comprueba `GET /api/health` y
muestra tarjetas de asignación. `frontend/nginx.conf` hace tres cosas:

- `location /api/` reenvía todo `/api/` a `orders:5001`.
- `location /` usa `try_files` y cae en `index.html`.
- `location = /frontend-health` responde `200 ok`.

Por eso el navegador en el puerto 8080 no llega a inventario, almacén ni
reparto. Esas APIs siguen en los puertos 5002, 5003 y 5004.

## Páginas y rutas

Mantener `try_files` hacia `index.html`. Con eso bastan rutas del cliente,
sin rutas nuevas de servidor para las pantallas. Usar el hash:

| Ruta | Página | Qué muestra |
|---|---|---|
| `#/salud` | Salud | Estado de pedidos, inventario, almacén y reparto. |
| `#/pedido` | Alta | Formulario de dirección y partidas. |
| `#/tablero` | Tablero | Lista de pedidos, filtro por estado y búsqueda. |
| `#/seguimiento` | Seguimiento | Historial de un `order_id`. |
| `#/inventario` | Inventario | Existencias Norte y Sur. |

Una sola `index.html` carga el enrutador. Cada ruta pinta su página y nada
más. La ruta vacía abre `#/salud`. Una ruta desconocida también abre
`#/salud`.

La mejora individual del alumno 6 es el filtro por estado y la búsqueda en
el tablero. Se hacen en el navegador sobre la lista que ya devolvió
`GET /api/orders`. No hace falta un parámetro nuevo de API.

## Componentes

Crear un archivo por componente, por ejemplo bajo `frontend/js/components/`.
Cada uno pinta su propio bloque y no depende de un CSS global grande.

| Componente | Responsabilidad |
|---|---|
| `StatusBadge` | Texto de estado del pedido o de un servicio. |
| `ServiceHealth` | Una tarjeta con el resultado de `/health`. |
| `OrderForm` | Dirección, partidas, envío y el error que responda la API. |
| `OrderFilters` | Estado y texto de búsqueda. |
| `OrderTable` | Filas de pedidos ya filtradas. |
| `TrackingTimeline` | Historial en el orden en que lo devuelve el detalle. |
| `InventoryByWarehouse` | Stock `NORTE` y `SUR` de cada producto. |

Los estilos viven junto al componente o en clases pequeñas de
`frontend/css/styles.css`. No reintroducir el parche rechazado de esa hoja.
La vista debe poder usarse en celular: el encargo pide diseño adaptable.

Archivos nuevos sugeridos, todos dentro de `frontend/`:

```text
js/router.js
js/api.js
js/pages/salud.js
js/pages/pedido.js
js/pages/tablero.js
js/pages/seguimiento.js
js/pages/inventario.js
js/components/status-badge.js
js/components/service-health.js
js/components/order-form.js
js/components/order-filters.js
js/components/order-table.js
js/components/tracking-timeline.js
js/components/inventory-by-warehouse.js
```

## APIs que ya existen y no hay que cambiar

Consumir las rutas. No editar `services/`.

| Uso | Método y ruta | Respuesta en develop `4e707b9` |
|---|---|---|
| Salud general que ya usa la página | `GET /api/health` | 200 y `status` `BASE_READY`. |
| Catálogo para el formulario | `GET /api/products` | 200 y una lista de `product_id`, `name`, `description`, `price`. 503 `DATABASE_UNAVAILABLE`. |
| Alta | `POST /api/orders` | 201 con `order_id`, `status` `RECEIVED`, `total` e `items`. |
| Tablero | `GET /api/orders` | 200 y lista. |
| Seguimiento | `GET /api/orders/{id}` | 200 con `history` e `items`. 404 `ORDER_NOT_FOUND`. |
| Inventario Norte/Sur | `GET /api/inventory` | 200 con `stock.NORTE`, `stock.SUR` y `total`. Hoy solo en el puerto 5002. |

Cuerpo del alta:

```json
{
  "delivery_address": "Avenida Universidad 100",
  "items": [{ "product_id": "PROD-001", "quantity": 1 }]
}
```

Reglas para el cliente:

- Llenar el formulario con `GET /api/products`. No dejar un catálogo escrito
  en JavaScript. El precio del catálogo no es la existencia.
- Si `GET /api/products` responde 503, mostrar ese error. No inventar
  productos. Se puede ofrecer escribir `PROD-001` solo como respaldo cuando
  el inventario del puerto 5002 sí respondió.
- Un 400 trae `error` `INVALID_ORDER` y un `detail`. Mostrar ese `detail`.
- Un 503 `KAFKA_UNAVAILABLE` incluye `order_id`: el pedido ya se guardó.
  Abrir el seguimiento de ese identificador. No repetir el POST a ciegas.
- Un 503 `DATABASE_UNAVAILABLE` no creó el pedido.
- Una imagen vieja puede responder 501 `NOT_IMPLEMENTED`. Mostrarlo como
  API pendiente. No tratarlo como pedido creado.
- El historial visible es `RECEIVED`, `INVENTORY_RESERVED`, `PREPARING`,
  `READY_FOR_DELIVERY`, `DRIVER_ASSIGNED`, `IN_TRANSIT`,
  `NEAR_DESTINATION`, `DELIVERED`. `INVENTORY_REJECTED` cierra ese intento.

## Proxy que el alumno 6 debe pegar en frontend/nginx.conf

Sustituir el `server` actual. El bloque de abajo no está aplicado en esta
rama. Va comentado aquí para copiarlo en `frontend/nginx.conf`.

Los búferes evitan `400 Request Header Or Cookie Too Large` de nginx 1.27.5
cuando el navegador manda cookies grandes de `localhost`.

`resolver 127.0.0.11` permite que Nginx arranque aunque inventario, almacén
o reparto todavía no estén en marcha. Las ubicaciones específicas van antes
de `location /api/`. La barra y el espacio importan: `location /api/` no
debe quedar escrita de una forma que también capture `/api/inventory`.

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    client_header_buffer_size 32k;
    large_client_header_buffers 8 128k;

    # Docker DNS. Se resuelve en cada petición.
    resolver 127.0.0.11 valid=10s ipv6=off;

    location = /api/services/orders/health {
        set $upstream orders:5001;
        proxy_pass http://$upstream/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 3s;
        proxy_read_timeout 10s;
    }

    location = /api/services/inventory/health {
        set $upstream inventory:5002;
        proxy_pass http://$upstream/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 3s;
        proxy_read_timeout 10s;
    }

    location = /api/services/warehouse/health {
        set $upstream warehouse:5003;
        proxy_pass http://$upstream/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 3s;
        proxy_read_timeout 10s;
    }

    location = /api/services/delivery/health {
        set $upstream delivery:5004;
        proxy_pass http://$upstream/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 3s;
        proxy_read_timeout 10s;
    }

    location /api/inventory {
        set $upstream inventory:5002;
        proxy_pass http://$upstream$request_uri;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 3s;
        proxy_read_timeout 10s;
    }

    location /api/warehouse {
        set $upstream warehouse:5003;
        proxy_pass http://$upstream$request_uri;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 3s;
        proxy_read_timeout 10s;
    }

    location /api/delivery {
        set $upstream delivery:5004;
        proxy_pass http://$upstream$request_uri;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 3s;
        proxy_read_timeout 10s;
    }

    location /api/ {
        set $upstream orders:5001;
        proxy_pass http://$upstream$request_uri;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 3s;
        proxy_read_timeout 10s;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    location = /frontend-health {
        access_log off;
        return 200 'ok';
        add_header Content-Type text/plain;
    }
}
```

Después de ese proxy, el navegador usa el mismo origen para
`/api/inventory`, `/api/warehouse`, `/api/delivery` y
`/api/services/<servicio>/health`. Hasta entonces, la prueba de aceptación
de esta rama llama a `/health` y a las APIs en los puertos 5001–5004.

Almacén y reparto no publican un listado `GET /api/warehouse` ni
`GET /api/delivery`. El proxy solo deja el prefijo listo. La salud de
almacén puede responder 503 con `DEGRADED` si Kafka no está conectado.

## Qué no hacer

- No editar esta nota para “implementar” el tablero dentro de `docs/`.
- No cambiar `services/`, `contracts/` ni el esquema de eventos.
- No ejecutar `docker compose down -v`.
- No dar por entregado un pedido si la respuesta fue 501 o 503.
