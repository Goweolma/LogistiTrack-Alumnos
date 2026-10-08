# LogistiTrack — Base para alumnos

Proyecto colaborativo de Sistemas Distribuidos. Esta base **arranca**, expone la
interfaz y los endpoints de salud, pero el flujo logístico todavía no está
implementado. Los siete integrantes deben completarlo mediante ramas y Pull
Requests.

## Lo que ya está preparado

- Docker Compose con Kafka, PostgreSQL, cuatro microservicios y Nginx.
- Carpetas, Dockerfiles y dependencias.
- Endpoints `/health` en los cuatro servicios.
- Contrato inicial de eventos y esquema JSON.
- Base de datos mínima con productos de ejemplo.
- Interfaz inicial conectada a `/api/health`.
- Prueba de arranque y asignaciones para siete alumnos.

## Lo que debe construir el equipo

```text
RECEIVED → INVENTORY_RESERVED → PREPARING → READY_FOR_DELIVERY
→ DRIVER_ASSIGNED → IN_TRANSIT → NEAR_DESTINATION → DELIVERED
```

Cada archivo marcado con `TODO(ALUMNO-N)` pertenece al responsable indicado en
`assignments/`.

## Inicio rápido

Requisitos: Git, Docker Desktop y al menos 6 GB de memoria disponible.

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
```

Abrir <http://localhost:8080>. El tablero llama a las APIs por el mismo
origen. Si un servicio aún no implementa su ruta, la pantalla lo indica y
conserva el contrato de `POST /api/orders`.

Validar la base:

```powershell
python -m pip install -r requirements-dev.txt
python scripts\smoke_base.py
```

La prueba base solo comprueba que la plataforma arranca. La prueba de
aceptación vive en `scripts/acceptance_flow.py` y el manual único en
`docs/MANUAL.md`. Un `POST /api/orders` que responde 501 queda registrado
como bloqueado: no cuenta como recorrido completo.

## Ramas

- `main`: entrega estable.
- `develop`: integración.
- `feat/orders-service`
- `feat/inventory-service`
- `feat/warehouse-service`
- `feat/delivery-service`
- `feat/infrastructure`
- `feat/frontend-dashboard`
- `docs/manual-and-testing`

Nadie debe realizar `push` directo a `main` o `develop`.

## Puertos

| Servicio | Puerto |
|---|---:|
| Frontend | 8080 |
| Orders | 5001 |
| Inventory | 5002 |
| Warehouse | 5003 |
| Delivery | 5004 |
| PostgreSQL | 5433 externo / 5432 interno |
| Kafka | 9092 |

## Definición de terminado

Un módulo se considera terminado cuando tiene implementación, manejo de
errores, logs, pruebas, documentación y un Pull Request aprobado.

