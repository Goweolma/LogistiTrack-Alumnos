# Alumno 5 — Infraestructura e integración

Rama: `feat/infrastructure`  
Rutas: `compose.yaml`, `common/`, `contracts/` e `infrastructure/`

## Debe demostrar

- Kafka, PostgreSQL y los servicios arrancan con Compose.
- Los seis topics existen.
- Las variables no están escritas en el código.
- Los servicios se encuentran por nombre.
- Health checks y volumen funcionan.
- Los eventos inválidos llegan a `dead-letter`.

## Mejora individual

Agregar un script que valide automáticamente la salud completa de la plataforma.

