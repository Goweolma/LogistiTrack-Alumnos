# Instrucciones para el equipo

## Regla principal

La base compartida debe arrancar antes de comenzar. Cada integrante modifica
principalmente su ruta y solicita integración mediante Pull Request.

## Primer día

1. Clonar el repositorio.
2. Crear `.env` desde `.env.example`.
3. Ejecutar `docker compose up -d --build`.
4. Abrir `http://localhost:8080`.
5. Ejecutar `python scripts/smoke_base.py`.
6. Crear la rama asignada.
7. Registrar en un Issue la primera tarea.

## Primera meta técnica

Antes de avanzar al flujo completo debe funcionar:

```text
POST /api/orders
    ↓
pedido almacenado con estado RECEIVED
    ↓
evento ORDER_CREATED en Kafka
    ↓
inventario consume el evento
```

## Forma de trabajar

```powershell
git switch develop
git pull origin develop
git switch -c feat/nombre-modulo
```

Después de una unidad pequeña y comprobable:

```powershell
git status
git add RUTA_DE_MI_MODULO
git commit -m "feat(modulo): describir cambio"
git push -u origin feat/nombre-modulo
```

## Contenido obligatorio del Pull Request

- Problema resuelto.
- Archivos modificados.
- Pasos exactos para probar.
- Evidencia de ejecución.
- Riesgos o trabajo pendiente.
- Issue asociado usando `Closes #N`.

## Acuerdos de integración

- No cambiar nombres de eventos sin aprobación.
- No modificar el módulo de otro alumno sin avisar.
- No subir `.env`, contraseñas ni datos personales.
- No guardar listas de productos o pedidos dentro del código.
- Todo consumidor debe considerar eventos duplicados.
- Todo servicio debe conservar su endpoint `/health`.

