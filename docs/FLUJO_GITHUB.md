# Flujo de GitHub para el equipo

## Ramas protegidas

El profesor crea y protege:

- `main`: versión estable.
- `develop`: integración aprobada.

Activar en ambas ramas:

- Require a pull request before merging.
- Require one approval.
- Require Code Owner review.
- Dismiss stale approvals.
- Require conversation resolution.
- Block force pushes and deletions.

Cambiar `@TU_USUARIO_GITHUB` en `.github/CODEOWNERS`.

## Trabajo del alumno

```bash
git switch develop
git pull origin develop
git switch -c feat/nombre-del-modulo
```

Después de programar:

```bash
git status
git add RUTA_DE_SU_MODULO
git commit -m "feat(modulo): describir cambio"
git push -u origin feat/nombre-del-modulo
```

Abrir Pull Request contra `develop`. No realizar push directo a `main` o `develop`.

## Convención de commits

```text
feat(orders): crear endpoint de pedidos
fix(inventory): evitar inventario negativo
test(delivery): probar cambio de estados
docs(manual): agregar guía de seguimiento
chore(compose): agregar healthcheck
```

## Revisión del profesor

1. Relacionar el PR con su Issue mediante `Closes #N`.
2. Revisar archivos modificados.
3. Ejecutar las instrucciones de prueba.
4. Solicitar cambios o aprobar.
5. Integrar con **Squash and merge**.

## Integración final

Cuando `develop` funcione:

1. Abrir PR `develop → main`.
2. Ejecutar demostración completa.
3. Aprobar e integrar.
4. Crear tag `v1.0.0`.

