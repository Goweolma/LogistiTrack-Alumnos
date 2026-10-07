# Diagnóstico de entrega — Alumno 5 — 7 de octubre de 2026

## Base revisada

- Rama inicial: `develop`, árbol limpio, HEAD `2e752db`.
- `git fetch origin` detectó diez commits pendientes. Se actualizó mediante
  `git pull --ff-only origin develop` hasta `676a2e5`.
- Se revisaron Compose, `common/`, `contracts/`, `infrastructure/`, `scripts/`,
  pruebas, `.github/workflows/`, `.env.example`, `.gitignore`, asignación,
  arquitectura, handoff y documentación de integración. No se recuperaron ramas
  históricas ni se modificaron archivos de otros alumnos.
- `python -m pip install -r requirements-dev.txt` correcto. Base: **80 passed,
  0 failed, 0 skipped, 0 errores de colección**, Python local 3.11.9.
- CI ya usa Python 3.12, instala las seis dependencias legítimas y corre
  `python -m pytest -q` en push/PR hacia `develop`; no necesita cambios.

## Ya implementado

Compose define PostgreSQL 16, Kafka 4.1.0, inicializador, cuatro APIs y frontend.
Tiene healthchecks de PostgreSQL/Kafka/Orders, volumen `postgres_data`, DNS de
servicios, dependencias por salud y finalización del inicializador. Los puertos
publicados son distintos. Los seis topics coinciden entre contrato, asignación,
Compose y script: no se encontró una especificación interna de cuatro topics.

`common/events.py` valida campos, UUID, longitudes de tipo/fuente, pedido,
fecha con zona, versión entera 1 y payload objeto. `common/kafka_client.py`
valida antes de publicar y genera `PROCESSING_FAILED` con original y error.
Los consumidores usan `earliest` y commit manual.

`.env` está ignorado y no está versionado. `.env.example` contiene valores
de demostración, suficientes para el arranque. No se encontraron tokens o
claves privadas en archivos versionados. Las credenciales predeterminadas de
Compose son las de demostración y deben personalizarse juntas con `DATABASE_URL`.
`PORT` también se lee en APIs; se mantiene el puerto correspondiente de cada
servicio. Los `localhost` encontrados corresponden al host, a healthchecks del
propio contenedor o a una prueba que simula un broker inaccesible.

## Dos cambios independientes

1. `fix/alumno5-kafka-reliability`, base `develop`: inicializador que falla ante
   errores, nombre literal de red `logistitrack` y confirmación del broker para
   publicación/dead-letter. **86 passed** en Python local. Cambia Compose,
   helper Kafka, sus pruebas y documentación de infraestructura.
2. `fix/alumno5-platform-health`, base `develop`: diagnóstico portable de Docker,
   volumen real, errores y responsabilidades. **111 passed** en Python local.
   Cambia el script, sus pruebas y documentación de infraestructura.

En ambos: 0 fallos, 0 saltos, 0 errores de colección; `git diff --check` y
`docker compose config --quiet` correctos. Las ramas pueden revisarse por separado.

Ambas ramas combinadas en una rama de prueba **local**, sin fusionar `develop`:
**117 passed, 0 failed, 0 skipped, 0 errores de colección** en un contenedor
`python:3.12-slim`, instalando `requirements-dev.txt`. No se requieren cambios
en CI. La rama de prueba no se publica.

## Comprobación real de Docker

Las imágenes se construyeron. El primer arranque encontró un conflicto de
nombre de contenedor; al aplicar el nombre explícito de red quedaron referencias
a la red anterior. Se recuperó con `docker compose up -d --force-recreate`,
conservando el volumen. No se ejecutó `down -v`.

Después de completar el arranque:

- siete servicios `running`, Kafka/PostgreSQL/Orders `healthy`;
- `kafka-init`: `Exited (0)`;
- siete contenedores activos conectados a `logistitrack` (el inicializador ya salió);
- volumen real `logistitrack-alumnos_postgres_data` montado y escribible;
- frontend y cuatro APIs: HTTP 200;
- seis topics presentes;
- script mejorado: todas las comprobaciones OK, código de salida 0.
- segunda ejecución de `kafka-init`: código 0, idempotencia comprobada;
- publicación real confirmada y dead-letter consumido con original y motivo;
- prueba de error temprano del inicializador: script antiguo retorna 0 y el
  corregido retorna 42 ante el mismo fallo simulado del primer topic.

Se ejecutó el script mejorado desde otra carpeta sobre el despliegue de la rama
Kafka. Eso comprueba su independencia del directorio de trabajo, sin afirmar que
las APIs implementen el flujo de negocio completo.

## Pendientes y límites

**BLOQUEADO POR DEPENDENCIA EXTERNA**:

| Archivo | Problema | Efecto en integración | Acción del responsable |
|---|---|---|---|
| `services/orders/app.py` | Pedido válido devuelve 501. | No inicia el flujo Kafka. | Alumno 1: persistir y publicar `ORDER_CREATED`. |
| `services/orders/app.py` | Catálogo devuelve `[]` fijo. | No permite demostrar selección real de productos. | Alumnos 1/2: conectar catálogo persistido. |
| `services/delivery/app.py` | Requiere columnas ausentes: `orders.driver_id/vehicle_id`, `order_history.event_id/event`. | Una entrega real falla contra el esquema actual. | Alumno 4 con 1/2: acordar migración compatible, como solicita el encabezado del módulo. |

Compatibilidad de contrato que requiere seguimiento de **Alumno 5**:
el validador Python acepta UUID sin guiones, mientras el formato UUID del esquema
los exige; `version: 1.0` pasa `const: 1` del esquema, pero Python exige entero.
No se cambió el contrato en estos PR: `contracts/events.md` exige un PR separado
y aprobación del profesor para cambios de contrato. Los eventos creados por
`build_event` siguen usando UUID canónico y versión entera 1. No se afirma
equivalencia absoluta entre ambos validadores.

Para la exposición mostrar `docker compose ps -a`, salida del script, listado
de topics y pruebas. Explicar que HTTP saludable no sustituye una prueba completa
de pedidos. La publicación confirmada permite reintentos; no elimina por sí sola
duplicados ni garantiza entrega exactamente una vez.

## Continuación del mismo día

Los dos Pull Requests siguen abiertos. Cada avance quedó en su propio commit,
sin reescribir historia y sin tocar `services/` ni `frontend/`.

En el PR de Kafka, después de exigir `DATABASE_URL` y `POSTGRES_PASSWORD` por
entorno:

- `validate_event` rechaza los UUID que el esquema no acepta (sin guiones,
  con llaves o `urn:uuid:`). Esos eventos van solo a `dead-letter`. El archivo
  de contrato no cambió.
- `version: 1.0` sigue pasando el `const: 1` del esquema y Python lo rechaza.
  Esa diferencia queda documentada y cubierta por una prueba. No se afirma
  equivalencia entre los dos validadores.
- Inventory, warehouse, delivery y frontend tienen healthcheck en Compose.
  Tras recrear solo esos contenedores, los cuatro quedaron `healthy` y sus
  endpoints respondieron HTTP 200. Postgres, Kafka, Orders y el volumen no se
  recrearon para borrar datos. `kafka-init` volvió a terminar en 0.

En el PR de salud, el script además comprueba:

- DNS interno de los servicios que siguen en ejecución, medido con `getent`
  desde Postgres. `kafka-init` no se exige porque al salir deja de resolver.
- Los ocho contenedores comparten la red etiquetada `logistitrack`, aunque el
  nombre visible de Docker lleve el prefijo del proyecto.
- `init.sql` está montado solo lectura en `docker-entrypoint-initdb.d`.

Ejecución real del script después de esos tres commits: todas las líneas en
`[OK]` y código de salida 0. La suite de esta rama quedó en 135 pruebas
aprobadas. La suite de la rama Kafka quedó en 106. Combinadas en una rama
local, sin publicarla, quedaron 154 aprobadas. No se ejecutó
`docker compose down -v`.

Siguen bloqueados por otros alumnos el alta real de pedidos y las columnas que
Delivery espera y el DDL compartido no tiene.
