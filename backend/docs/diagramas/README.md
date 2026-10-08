# Diagramas de arquitectura

Fuentes de los diagramas que se ven en **`/admin/diagramas`** (con las credenciales de `/admin`). Se generan con [Archify](https://github.com/tt-a1i/archify), una skill para agentes de IA (Claude Code, Codex, Cursor) que valida un JSON y lo convierte en un HTML autocontenido.

| Fuente | HTML servido | Tipo |
| :--- | :--- | :--- |
| `arquitectura.json` | `app/admin/diagrams/arquitectura.html` | architecture |
| `secuencia-analisis-pdf.json` | `app/admin/diagrams/secuencia-analisis-pdf.html` | sequence |
| `rotacion-keys.json` | `app/admin/diagrams/rotacion-keys.html` | dataflow |
| `ciclo-vida-conexion.json` | `app/admin/diagrams/ciclo-vida-conexion.html` | lifecycle |

Cada caja cita en `sources` los archivos y las líneas de donde sale; `meta.repository.revision` indica el commit que describe. **No se actualizan solos**: si cambia el código que describen, hay que editar el JSON y regenerar.

## Regenerar

Requisitos: Node 18+, la skill instalada (`npx skills add tt-a1i/archify -g`) y Chrome o Chromium para la verificación en navegador.

Desde la raíz del repo:

```bash
export ARCHIFY_UPDATE_CHECK_DISABLED=1
export ARCHIFY_CHROME=/ruta/a/chrome          # si no se detecta solo
# export ARCHIFY_CHROME_NO_SANDBOX=1           # solo si Chrome falla en un sandbox (flatpak, contenedor)

node ~/.claude/skills/archify/bin/archify.mjs finalize architecture \
  docs/diagramas/arquitectura.json app/admin/diagrams/arquitectura.html \
  --repo-root . --quality showcase --json
```

Para los otros diagramas, cambiar el tipo (`sequence`, `dataflow`, `lifecycle`) y los archivos según la tabla. Actualizar también `meta.repository.revision` con el commit nuevo (`git rev-parse HEAD`).

`finalize` deja archivos de evidencia (`*.finalize.json`, `*.browser-check.json`, etc.) junto al HTML: no hace falta versionarlos. Solo se versionan el `.json` de acá y el `.html` servido.
