# 🧠 Asistente de Accesibilidad para Contenidos Educativos - Backend
> **Innova Lab** | Agencia de Habilidades para el Futuro  
> *Herramienta de Inteligencia Artificial para la creación y adaptación de contenidos educativos accesibles.*

---

## 📋 Descripción del Proyecto

Los materiales educativos digitales suelen presentar barreras de accesibilidad relacionadas con su estructura, complejidad del lenguaje, legibilidad y ausencia de alternativas textuales en imágenes.

Este backend provee la API REST que impulsa el producto:
- **Escaneo y diagnóstico:** Combina reglas heurísticas automáticas con el análisis semántico de **Google Gemini API**.
- **Asistencia a la adaptación:** Genera sugerencias (simplificación de textos, consignas paso a paso, textos alternativos para imágenes) sin reemplazar el criterio pedagógico del docente.
- **Control docente:** Cada propuesta de adaptación puede ser aceptada, editada o descartada por el docente antes de exportar el material final.

---

## 🏛️ Arquitectura del Software y Decisiones Técnicas

El backend fue diseñado bajo una **arquitectura en capas desacopladas (Clean Architecture simplificada)**, asegurando escalabilidad, mantenibilidad y facilidad de prueba:

```text
backend/
├── app/
│   ├── admin/
│   │   ├── router.py                 # Panel de administración HTML (/admin): páginas, métricas, conexiones y usuarios
│   │   ├── session.py                # Sesión del panel (cookie firmada), roles y límite de intentos de login
│   │   ├── clerk_auth.py             # Login con Clerk: validación del token y cuenta del .env en Clerk
│   │   ├── test_web_auth.py          # Login de la web de pruebas (token Bearer) y su middleware
│   │   ├── diagrams/                 # HTML de los diagramas servidos en /admin/diagramas/{slug}
│   │   ├── static/                   # admin.css y admin.js (gráficos SVG, tablas y modales)
│   │   └── templates/                # base, login, dashboard y diagram (Jinja2 + Obelisco V2)
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/            # Capa de Controladores HTTP
│   │       │   ├── health.py         # Estado del sistema y entorno
│   │       │   ├── test_ai.py        # Prueba de conectividad con IA
│   │       │   ├── documents.py      # Extracción de PDF, Word, PowerPoint y texto directo
│   │       │   ├── settings.py       # Retención de archivos editable por un admin (#64)
│   │       │   └── analysis.py       # Escáner de accesibilidad con IA
│   │       ├── router.py             # Versionado y unificación de rutas v1
│   │       └── uploads.py            # Validación de archivos subidos (.pdf, .docx, .pptx)
│   ├── core/
│   │   ├── config.py                 # Configuración centralizada y tipada (Pydantic Settings)
│   │   ├── crypto.py                 # Cifrado (Fernet) de las API keys guardadas en la DB
│   │   ├── docs.py                   # /docs, /redoc y openapi.json detrás de la sesión del panel (fuera de development)
│   │   ├── owner.py                  # Dueño de los recursos del request (usuario de Clerk, web de pruebas o anon)
│   │   ├── permissions.py            # Roles de la API (docente, admin) y sus permisos
│   │   ├── rate_limit.py             # Límite de uso de IA por IP, por usuario y global
│   │   ├── security.py               # Verificación anti-CSRF (Origin) de los POST del panel
│   │   └── teacher_auth.py           # Login de docentes con Clerk: quién llama, su rol y require_permission
│   ├── db/
│   │   ├── database.py               # Conexión a SQLite (local) o D1 (producción) + esquema
│   │   ├── d1_client.py              # Cliente del Worker pasarela de Cloudflare D1
│   │   ├── d1_connection.py          # Conexión D1 con la interfaz de sqlite3 (batch atómico por bloque)
│   │   ├── api_key_repository.py     # CRUD de conexiones de IA y contadores de uso
│   │   ├── ai_usage_repository.py    # Historial de llamadas a la IA (métricas del panel)
│   │   ├── admin_member_repository.py # Usuarios de GitHub con acceso al panel y su rol
│   │   ├── settings_repository.py    # Configuración editable desde /admin (tabla app_settings)
│   │   └── user_activity_repository.py # Historial permanente de uso por usuario y usuarios de la API (#104)
│   ├── schemas/
│   │   ├── document.py               # Contratos de extracción (ExtractedDocument, TextInputRequest)
│   │   └── analysis.py               # Contratos de diagnóstico (AccessibilityAnalysisResponse)
│   ├── services/
│   │   ├── document_service.py       # Extracción de PDF en memoria (PyMuPDF, párrafos por bloque) y heurísticas
│   │   ├── office_service.py         # Extracción de Word y PowerPoint (python-docx / python-pptx) al mismo contrato
│   │   ├── accessibility_service.py  # Orquestador del diagnóstico: IA + reglas, validación de citas y puntaje
│   │   ├── rules_service.py          # Motor de reglas automáticas (oraciones/párrafos extensos, visual) y puntaje
│   │   ├── key_rotation_service.py   # Rotación automática y tracking de consumo por key
│   │   ├── llm_service.py            # Orquestación multi-proveedor de modelos de lenguaje
│   │   ├── admin_metrics_service.py  # Métricas agregadas del panel (uso de IA, conexiones y producto)
│   │   ├── retention_service.py      # Retención de archivos configurable y limpieza automática (#64)
│   │   └── llm/                      # Adaptadores de proveedores (Gemini, OpenAI-compatible)
│   └── main.py                       # Instanciación de FastAPI, Middlewares y OpenAPI
├── docs/
│   ├── riesgos_y_limitaciones_semana1.md     # Riesgos técnicos de documentos y arquitectura
│   ├── riesgos_limitaciones_semana1_ia.md    # Riesgos técnicos de IA y cuotas
│   ├── motor_reglas.md                       # Reglas automáticas, umbrales y fórmula del puntaje
│   ├── diagramas/                            # Fuentes (JSON de Archify) de los diagramas del panel
│   └── benchmarks/                           # Reportes de latencia, tokens y variabilidad
├── d1-gateway/                       # Worker pasarela de Cloudflare D1 (wrangler, migraciones)
├── scripts/
│   ├── benchmark_analysis.py         # Benchmark de IA y calibración de reglas (--rules-only)
│   ├── d1_ping.py                    # Conexión y latencia contra el Worker de D1
│   └── migrate_sqlite_to_d1.py       # Copia los datos del SQLite de Railway a D1
├── tests/                            # Tests unitarios y de integración (pytest, modo mock) y fixtures
├── app_data.db                       # DB local SQLite (desarrollo): API keys y contadores (IGNORADO en Git)
├── .env                              # Variables sensibles locales (IGNORADO en Git)
├── .env.example                      # Plantilla pública de variables requeridas
├── .gitignore                        # Reglas de exclusión de seguridad y entorno
├── requirements.txt                  # Dependencias fijadas del proyecto
├── requirements-dev.txt              # Dependencias de desarrollo (pytest)
├── pytest.ini                        # Configuración de pytest
└── README.md                         # Documentación general de arquitectura y ejecución
```

### 💡 Justificación de Decisiones Técnicas:

1. **FastAPI como Framework Web:**
   - **Asincronía nativa (`async / await`) + Threadpool (`asyncio.to_thread`):** Las llamadas a modelos de lenguaje (LLMs) usan I/O asíncrono, mientras que el procesamiento de PDFs en C++ (`PyMuPDF`) se ejecuta en hilos separados para nunca bloquear el *event loop*.
   - **Validación con Pydantic:** Validación estricta de esquemas de entrada y salida, asegurando contratos de datos claros con el equipo de Frontend y reduciendo errores en tiempo de ejecución.
2. **Procesamiento de Documentos 100% en Memoria (`PyMuPDF`):**
   - Los archivos PDF subidos por los docentes se procesan directamente en streams de memoria RAM sin persistirse en disco, cumpliendo estrictamente con las pautas de privacidad y protección de datos sensibles de estudiantes.
   - Incluye heurísticas para detectar documentos escaneados (sin capa de texto OCR) y recorte inteligente (`text_for_analysis`) para proteger las cuotas de tokens.
   - Word (`.docx`) y PowerPoint (`.pptx`) se extraen con `python-docx` / `python-pptx` al mismo `ExtractedDocument` que un PDF, así reglas, IA, textos alternativos y detección de datos personales funcionan igual. Los títulos salen de los estilos o del título de cada diapositiva, y las imágenes que ya tienen texto alternativo no se envían a la IA. Antes de abrirlos se rechazan formatos antiguos, archivos protegidos, con macros o que descomprimidos superan 150 MB (zip bombs).
3. **Salidas Estructuradas y Control de Alucinaciones:**
   - El escáner utiliza `response_schema` para garantizar respuestas JSON tipadas con semáforo por dimensión (`comprension`, `estructura`, `accesibilidad_visual`) y verifica textualmente cada cita (`fragment_found`) contra el documento original.
4. **Documentación OpenAPI Automática (Swagger UI):**
   - Disponibilidad inmediata de documentación interactiva en `/docs` y `/redoc` sin necesidad de mantener colecciones manuales en Postman.
5. **Capa de Servicios y Adaptadores LLM Aislados (`services/`):**
   - La lógica de integración con proveedores de IA está desacoplada de los controladores HTTP, permitiendo rotar entre múltiples API keys y proveedores por orden de prioridad.
6. **Manejo Seguro de Secretos y Configuración (`pydantic-settings`):**
   - Ninguna credencial sensible está hardcodeada. Las claves se leen dinámicamente desde variables de entorno (`.env`) con `SecretStr` y cifrado en reposo mediante **Fernet** (`cryptography`).
7. **Políticas de CORS Preconfiguradas:**
   - Configuración explícita de orígenes seguros (`localhost:3000`, `localhost:5173`) para evitar problemas de bloqueo de peticiones cruzadas durante el desarrollo con React/Vite/Next.js.
8. **Motor de Reglas Automáticas y Puntaje Combinado (`rules_service.py`):**
   - Reglas determinísticas en Python (oraciones de más de 35 palabras, párrafos de más de 150, imágenes y PDF escaneado) que corren sobre el texto completo sin consumir tokens. El `estimated_score` pondera IA (70%) y reglas (30%) y expone su cálculo en `score_breakdown`. Detalle en [`docs/motor_reglas.md`](docs/motor_reglas.md).

---

## 🔐 Panel de Administración y Rotación de API Keys

Para evitar caídas de servicio cuando se agota la capa gratuita de los proveedores de IA, el backend expone un panel interno en **`/admin`** (HTML con Obelisco V2) que permite:

- **Ver métricas de uso** de la IA por período (24 h, 7 y 30 días): llamadas, tokens, latencia p95 y errores, tokens por proveedor y llamadas por resultado. También uso del producto: diagnósticos, puntajes, barreras y decisiones del docente.
- **Ver la actividad de archivos y enlaces compartidos** del período (pestaña Uso del producto, #98): subidas, exportaciones, descargas, enlaces creados y abiertos, volumen subido, archivos por formato, enlaces por estado y exportaciones por forma de entrega. Sale de `file_events`, un registro con la fecha, el tipo de evento, el formato y el tamaño, nunca el nombre ni el contenido del archivo. Se conserva `AI_USAGE_RETENTION_DAYS` (30 días). Los gráficos tienen leyenda, tooltip, navegación con teclado y vista de tabla, con colores validados para daltonismo.
- **Ver quién usa la herramienta y cuánto** (pestaña **Uso por usuario**, #104): usuarios activos y nuevos, acciones por origen (Frontend, web de pruebas o anónimo), rankings de los más activos y de los que más tokens consumen, y una tabla con cada usuario (nombre o id, origen, rol, primer y último uso, diagnósticos, propuestas, decisiones, archivos, tokens y respuestas 429). El detalle de un usuario muestra sus totales históricos, la actividad por hora o día, los formatos que usa, sus adaptaciones y decisiones, los modelos de IA y sus últimas 50 acciones. Sale de `user_activity` (una fila por acción, con metadatos y nunca el material, los textos propuestos ni nombres de archivo) y de `api_users`. **Este historial es permanente**: no vence con los diagnósticos ni con los archivos y ninguna limpieza lo borra. El nombre y el email de los docentes se leen de la API de Clerk con `USERS_CLERK_SECRET_KEY`, en segundo plano y cacheados 7 días, nunca en los requests de la API. Lo ven admin y solo lectura.
- **Visualizar el consumo en tiempo real** por conexión: requests y tokens usados vs. sus umbrales — **RPM** (requests/minuto), **TPM** (tokens/minuto), **RPD** (requests/día) y **TPD** (tokens/día).
- **Cargar y priorizar múltiples conexiones de IA**, cada una con sus propios umbrales configurables.
- **Rotación automática**: cuando la key activa se acerca a cualquiera de sus umbrales o recibe un error de cuota (`429`/`503`), el backend cambia automáticamente a la siguiente conexión disponible.
- **Administrar el acceso**: qué usuarios de GitHub entran y con qué rol.
- **Ver el estado de los servicios** (pestaña **Estado**): API, base de datos, Worker de D1, conexiones de IA, Clerk (panel y docentes), web de pruebas, plataforma de QA (`QA_PLATFORM_URL`) y frontend, más las URLs del proyecto.

**Pestaña Estado.** Es una página de estado liviana (`app/services/status_service.py`, `GET /admin/api/status`):

- Los servicios se consultan solo mientras alguien tiene la pestaña abierta (cada 30 s, y nada si la pestaña del navegador está oculta). No hay tareas en segundo plano ni historial.
- La ronda de chequeos se reutiliza durante 20 s, así que varios paneles abiertos no multiplican las consultas. Lo único que se recuerda, en memoria, es desde cuándo cada servicio está en su estado actual.
- Cada chequeo es un GET a una URL pública (5 s máximo) o un `SELECT 1` en la base. A los proveedores de IA no se les manda nada: su estado sale de la rotación de conexiones, sin gastar cuota.
- Estados: **Operativo**, **Con problemas** (respuesta 4xx o más de 1,5 s), **Caído** (sin respuesta o 5xx) y **Sin configurar** (falta la variable; no cuenta para el estado general).
- **Al sumar un servicio externo** al proyecto, agregar su chequeo en `_registry()` y, si tiene URL pública, en `links()` del mismo archivo.

**Acceso y roles.** Se entra en `/admin/login` con **Clerk** (cuenta de GitHub del equipo o el usuario `ADMIN_USERNAME`) o con el formulario de respaldo (`ADMIN_USERNAME` / `ADMIN_PASSWORD`), según `ADMIN_AUTH` (`local`, `clerk` o `ambos`). La sesión dura 8 h (cookie firmada `HttpOnly`, `SameSite=Strict`, `Secure` fuera de development) y se bloquea tras 5 intentos fallidos por IP o 30 en total en 10 minutos.

| Rol | Quién | Puede |
| :--- | :--- | :--- |
| Admin | Cuenta del `.env` y los usuarios de `ADMIN_GITHUB_ADMINS` | Todo: conexiones, usuarios y web de pruebas con IA real |
| Solo lectura | Usuarios de `ADMIN_GITHUB_VIEWERS` | Ver el panel completo (menos la pestaña Usuarios), Swagger y la web de pruebas en modo mock |

Las listas de GitHub solo cargan usuarios al arrancar; después se administran desde la pestaña **Usuarios** y los cambios aplican al instante. Las rutas viejas `/adminv2/...` redirigen a `/admin/...`.

---

## 📖 Documentación de la API (Swagger y ReDoc)

FastAPI autogenera dos interfaces de documentación interactiva:

* **Swagger UI (Pruebas interactivas):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)  
  *Permite probar cada endpoint en vivo haciendo clic en **"Try it out"** y luego en **"Execute"**.*
* **ReDoc (Documentación técnica limpia):** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

En local (`ENVIRONMENT=development`) quedan abiertas. En staging/production piden **iniciar sesión en el panel** (`/admin/login`) y vuelven solas a la documentación después de entrar.

---

## 📡 Endpoints Implementados (Semanas 0 a 3)

| Método | Endpoint | Descripción | Estado |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Bienvenida, entorno activo y enlaces a la documentación | ✅ Operativo |
| `GET` | `/api/v1/health` | Chequeo de estado y versión del backend | ✅ Operativo |
| `POST` | `/api/v1/ai/test-gemini` | Validación de conectividad con IA (con rotación automática de keys) | ✅ Operativo |
| `POST` | `/api/v1/documents/process-text` | Procesamiento y extracción de métricas de texto plano directo | ✅ Operativo |
| `POST` | `/api/v1/documents/upload-pdf` | Carga y extracción en memoria de archivos PDF (texto, páginas, imágenes y detección de escaneo) | ⚠️ Deprecado (#63) |
| `POST` | `/api/v1/documents/upload` | Igual que `upload-pdf`, aceptando también Word (`.docx`) y PowerPoint (`.pptx`) | ⚠️ Deprecado (#63) |
| `POST` | `/api/v1/documents/files/{file_id}` | Extracción de un archivo ya subido al almacenamiento (#63): lo lee el backend, en memoria | ✅ Operativo |
| `POST` | `/api/v1/analysis/sample` | Escáner de accesibilidad IA + reglas sobre texto pegado (`application/json` o `text/plain`) con semáforo, puntaje combinado y barreras. `?mock=true` simula la IA | ✅ Operativo |
| `POST` | `/api/v1/analysis/pdf` | Escáner de accesibilidad IA + reglas sobre un PDF subido (máx. 10 MB). `?mock=true` simula la IA | ⚠️ Deprecado (#63) |
| `POST` | `/api/v1/analysis/file` | Igual que `/analysis/pdf`, aceptando `.pdf`, `.docx` y `.pptx` (máx. 10 MB). `?mock=true` simula la IA | ⚠️ Deprecado (#63) |
| `POST` | `/api/v1/analysis/files/{file_id}` | Igual que `/analysis/file`, para un archivo ya subido al almacenamiento (#63): el archivo no viaja en el pedido. `?mock=true` simula la IA | ✅ Operativo |
| `POST` | `/api/v1/adaptations` | Propuesta de adaptación con IA para una barrera (`lenguaje_claro`, `consigna_en_pasos`, `reorganizar`, `mejorar_estructura`): original + propuesta + explicación, en estado `pendiente`. Como mucho una pendiente por barrera: otra responde `409` (`pending_proposal_exists`) sin llamar a la IA. `?mock=true` simula la IA | ✅ Operativo |
| `GET` | `/api/v1/adaptations?analysis_id=` | Propuestas de adaptación generadas para un diagnóstico | ✅ Operativo |
| `GET` | `/api/v1/adaptations/{proposal_id}` | Recuperar una propuesta de adaptación por ID | ✅ Operativo |
| `POST` | `/api/v1/adaptations/{proposal_id}/decision` | Revisión docente: aceptar, editar (con `edited_text`) o descartar una propuesta pendiente. El original nunca se modifica | ✅ Operativo |
| `POST` | `/api/v1/adaptations/{proposal_id}/undo` | Deshacer la decisión: la propuesta vuelve a `pendiente` | ✅ Operativo |
| `GET` | `/api/v1/adaptations/decisions?analysis_id=` | Registro cronológico de decisiones y deshaceres del diagnóstico (para el informe) | ✅ Operativo |
| `GET` | `/api/v1/adaptations/final-version?analysis_id=` | Versión final del material: aplica solo las propuestas aceptadas o editadas (solapamientos resueltos a favor de la edición del docente y la decisión más reciente) | ✅ Operativo |
| `GET` | `/api/v1/export/content?analysis_id=&format=` | Descarga del material adaptado en `docx` (por defecto), `pdf`, `md` o `txt`, generado en memoria con solo los cambios aceptados o editados. Con `&delivery=link`, en lugar del archivo devuelve una URL firmada de descarga (#62) | ✅ Operativo |
| `GET` | `/api/v1/export/report?analysis_id=&format=` | Descarga del informe en `pdf` (por defecto), `md` o `txt`. En PDF, los caracteres fuera de latin-1 salen como `?` (#87). Con `&delivery=link`, URL firmada (#62) | ✅ Operativo |
| `POST` | `/api/v1/files/upload-url` | Pide una URL firmada `PUT` para subir un `.pdf`, `.docx` o `.pptx` (máx. 10 MB) directo al almacenamiento (#62) | ✅ Operativo |
| `POST` | `/api/v1/files/{file_id}/complete` | Confirma la subida: verifica tamaño, tipo y firma del archivo | ✅ Operativo |
| `GET` | `/api/v1/files` | Archivos vigentes del usuario (subidos y exportados), del más reciente al más antiguo (#155) | ✅ Operativo |
| `GET` | `/api/v1/files/{file_id}` | Metadatos del archivo (estado, tamaño, vencimiento) | ✅ Operativo |
| `DELETE` | `/api/v1/files/{file_id}` | Elimina el archivo del almacenamiento y revoca sus enlaces (#155) | ✅ Operativo |
| `GET` | `/api/v1/files/{file_id}/download-url` | URL firmada `GET` de descarga, con el nombre original | ✅ Operativo |
| `POST` | `/api/v1/files/{file_id}/shares` | Crea un enlace para compartir el archivo (`/s/{token}`), revocable y con vencimiento (#65) | ✅ Operativo |
| `GET` | `/api/v1/files/{file_id}/shares` | Enlaces activos del archivo, con cuántas veces se abrieron | ✅ Operativo |
| `DELETE` | `/api/v1/files/{file_id}/shares/{share_id}` | Revoca un enlace: deja de funcionar al instante | ✅ Operativo |
| `GET`/`PUT` | `/api/v1/settings/retention` | Retención de archivos vigente y última limpieza; cambiarla para los archivos nuevos (permiso `settings:retention`, rol admin, #64) | ✅ Operativo |
| `GET` | `/s/{token}` | Enlace compartido (público): `302` a una URL firmada de descarga de minutos; `404` si se revocó o venció | ✅ Operativo |
| `GET` | `/api/v1/adaptations/report?analysis_id=` | Informe final: barreras con la decisión del docente, resumen y puntaje antes/después (comparable: conserva la IA y las reglas del archivo, recalcula las de texto; 0 tokens) | ✅ Operativo |
| `POST` | `/api/v1/transformations` | Transformar material (#116): `format` (`no_images`, `mind_map`, `infographic`, `audio`) y `analysis_id` o `file_id`. Asíncrono: responde `202` con `status = "pending"`. Con IA real: `no_images` (#117), `mind_map` (#118), `infographic` (#119) y `audio` (#122) | ✅ Operativo |
| `GET` | `/api/v1/transformations` | Mis transformaciones vigentes (las últimas 50) | ✅ Operativo |
| `GET` | `/api/v1/transformations/{id}` | Estado (`pending` → `processing` → `ready` / `failed`), resultado estructurado, `views` (mapa mental: lista anidada en Markdown y sintaxis Mermaid `mindmap`; audio: `transcript`, el guion en Markdown; infografía: `svg`, dibujada con texto real, y `markdown`, su versión en texto), `progress` mientras se genera el audio y URL firmada de vista previa del archivo generado | ✅ Operativo |
| `POST` | `/api/v1/transformations/{id}/decision` | Revisión docente: aceptar, editar (`edited_result`, validado con el esquema del formato) o descartar. Lo aceptado con archivo queda en `/files` para descargar y compartir. Audio: se revisa el guion, y al aceptarlo pasa a `processing` y se genera el audio | ✅ Operativo |
| `POST` | `/api/v1/transformations/{id}/file` | Audio (#122): reintenta el audio de un guion aceptado cuyo audio falló (sin cuota de TTS, reinicio). Cuenta para el límite diario de audio | ✅ Operativo |
| `GET` | `/api/v1/transformations/{id}/export?format=` | Exporta el resultado aceptado o editado. Sin imágenes: `docx`, `pdf`, `md` o `txt`, como el material adaptado; en `docx` y `pdf` los datos de gráficos y tablas van como tablas reales, con fila de encabezado. Mapa mental: `md` o `txt` (lista anidada). Audio: `md` o `txt` (la transcripción). Infografía: `png`, `pdf` (con el texto real), `svg` o `md`. Con `&delivery=link`, URL firmada | ✅ Operativo |
| `POST` | `/api/v1/ai/test-tts` | Texto a voz (#121): convierte un texto corto (hasta 1.000 caracteres) en MP3 con Gemini 2.5 Flash TTS, voz Kore, acento rioplatense. Para escucharlo en Swagger. `?mock=true` devuelve un tono corto | ✅ Operativo |
| `GET` | `/admin` | Panel de administración: métricas, conexiones de IA, uso del producto, usuarios y diagramas (HTML, requiere sesión) | ✅ Operativo |
| `GET`/`POST` | `/admin/login` | Login del panel: Clerk (GitHub o usuario/contraseña) y respaldo con el usuario del `.env` | ✅ Operativo |
| `GET` | `/admin/diagramas/{slug}` | Diagrama de arquitectura dentro del panel. Fuentes y cómo regenerarlos en [`docs/diagramas/`](docs/diagramas/README.md) | ✅ Operativo |
| `GET` | `/admin/api/metrics?range=24h\|7d\|30d` | Métricas agregadas del panel (JSON, requiere sesión) | ✅ Operativo |
| `GET`/`POST`/`PATCH`/`DELETE` | `/admin/api/members` | Usuarios de GitHub con acceso al panel y su rol (JSON, solo admins) | ✅ Operativo |
| `GET`/`PUT`/`DELETE` | `/admin/api/retention` | Retención de archivos y última limpieza (ver: cualquier sesión; cambiar o restablecer: solo admins) | ✅ Operativo |
| `GET`/`POST` | `/api/v1/test-web/auth/...` | Login de la web de pruebas: configuración, usuario/contraseña, Clerk y sesión actual (token Bearer) | ✅ Operativo |

> `/admin` y `/api/v1/test-web/auth` son internos, no forman parte del contrato de la API — por eso no aparecen en el esquema OpenAPI de `/docs`/`/redoc` (`include_in_schema=False`).

---

## 🛠️ Guía de Puesta en Marcha Local

### 1. Requisitos Previos
- Python 3.10 o superior (recomendado 3.11 a 3.13).
- Obtener una API Key gratuita de Gemini en [Google AI Studio](https://aistudio.google.com/).

### 2. Clonar el repositorio y configurar el entorno
El backend vive en la carpeta `backend/` del monorepo: todos los comandos de esta guía se corren desde ahí.
```powershell
git clone https://github.com/e18-innovalab/contenidos_accesibles.git
cd contenidos_accesibles/backend

# 1. Crear el entorno virtual
py -m venv venv

# 2. Activar el entorno virtual (Windows PowerShell)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1

# 3. Instalar las dependencias
pip install -r requirements.txt
```

### 3. Configurar variables de entorno
Copiar la plantilla `.env.example` para crear el archivo local `.env`:
```powershell
Copy-Item .env.example .env
```
Editar `.env` y completar, como mínimo:
```env
# Credenciales del panel /admin (elegí tu propia contraseña). En local se entra solo con ellas, sin Clerk.
ADMIN_USERNAME=admin
ADMIN_PASSWORD=una_contraseña_segura
ADMIN_AUTH=local

# Clave de cifrado para las API keys guardadas en la DB local (generarla una sola vez)
DB_ENCRYPTION_KEY=
```
Generar `DB_ENCRYPTION_KEY` con:
```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4. Ejecutar el servidor de desarrollo
```powershell
uvicorn app.main:app --reload
```
Acceder a la documentación interactiva en: **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**.  
Acceder al panel de administración en: **[http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)** (login con `ADMIN_USERNAME` / `ADMIN_PASSWORD`).

### 5. Ejecutar los tests
```powershell
pip install -r requirements-dev.txt
pytest
```
Los tests no llaman a la IA (todo en `?mock=true`) y no necesitan `.env`: `tests/conftest.py` define variables de prueba y usa una base SQLite temporal, así que nunca tocan `app_data.db`. `tests/test_endpoints_integration.py` recorre el flujo mínimo del MVP (material → diagnóstico → propuestas → revisión → versión final → informe) y los errores de entrada de cada endpoint.

**CI:** [`.github/workflows/backend-tests.yml`](../.github/workflows/backend-tests.yml) corre `pytest` con Python 3.12 (la versión de `.python-version`, la misma que producción) en cada PR que toque `backend/` y en cada push a `main`. No usa secretos ni gasta tokens.

Para ver las métricas del motor de reglas sobre los materiales de ejemplo (sin consumir cuota):
```powershell
python -m scripts.benchmark_analysis --rules-only
```

---

## 🚀 Deploy en Railway

El repo ya incluye la configuración necesaria:

- `railway.json`: builder Railpack, comando de arranque (`uvicorn` en `0.0.0.0:$PORT`), healthcheck en `/api/v1/health` y **1 sola réplica** (los cooldowns de las conexiones de IA y el rate limit viven en memoria).
- `.python-version`: fija Python 3.12.

Pasos en el dashboard de Railway:

1. **New Project → Deploy from GitHub repo** → elegir `e18-innovalab/contenidos_accesibles` (rama `main`). En **Settings** del servicio, por ser un monorepo:
   - **Root Directory**: `/backend`
   - **Config File Path**: `/backend/railway.json` (Railway no lo busca dentro del Root Directory)
   - **Watch Paths**: `/backend/**`, para no redeployar con cambios de frontend, diseño u otras carpetas
   - **Region**: **US East (Virginia)**, junto a la base D1 (ENAM). Desde US West cada consulta a D1 tardaba ~3,4 veces más.
2. **Base de datos**: Cloudflare D1 a través del Worker pasarela (ver la sección **Cloudflare D1** más abajo). **No hace falta Volume**: el disco del contenedor se borra en cada deploy y con D1 no se usa.
3. **Variables**:
   ```env
   ENVIRONMENT=production
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=<contraseña fuerte>
   ADMIN_AUTH=ambos
   ADMIN_CLERK_PUBLISHABLE_KEY=<pk_test_... de la aplicación de Clerk del panel>
   ADMIN_CLERK_SECRET_KEY=<sk_test_...>
   ADMIN_CLERK_JWT_KEY=<JWT public key en PEM, pegada tal cual>
   USERS_CLERK_SECRET_KEY=<sk_test_... de la aplicación de Clerk de docentes>
   USERS_CLERK_JWT_KEY=<JWT public key en PEM de la aplicación de docentes>
   ADMIN_GITHUB_ADMINS=JAMRdev,VictoriaMackenzie,malessan4
   ADMIN_GITHUB_VIEWERS=camposmatias,Silvanam1,Jos022
   TEST_WEB_URL=https://<sitio-de-render>.onrender.com
   AI_API_KEY=<API key de Groq>
   DB_ENCRYPTION_KEY=<generada con el comando Fernet de arriba>
   DATABASE_BACKEND=d1
   D1_GATEWAY_URL=https://contenidos-accesibles-d1-gateway.jamrdev2.workers.dev
   D1_GATEWAY_TOKEN=<el mismo secreto cargado en el Worker con wrangler secret put>
   STORAGE_BACKEND=r2
   R2_ACCOUNT_ID=<ID de la cuenta de Cloudflare>
   R2_ACCESS_KEY_ID=<del token de API de R2>
   R2_SECRET_ACCESS_KEY=<del token de API de R2>
   R2_BUCKET=contenidos-accesibles-archivos
   BACKEND_CORS_ORIGINS=https://<dominio-del-frontend>,http://localhost:5173
   ```
   `BACKEND_CORS_ORIGINS` acepta orígenes separados por comas o una lista JSON (`["https://a.app","http://localhost:5173"]`). Reemplaza la lista por defecto, así que hay que incluir los orígenes locales si se van a usar. Cada origen va sin `/` final ni ruta.

   `PORT` no se define: la inyecta Railway. Guardar `DB_ENCRYPTION_KEY` en un lugar seguro: si cambia, las API keys guardadas en la DB ya no se pueden desencriptar.
4. **Settings → Networking → Generate Domain**.
5. Verificar `https://<dominio>/api/v1/health` y, si hace falta, cargar conexiones de IA de respaldo desde `https://<dominio>/admin`.

La conexión de IA principal sale de `AI_API_KEY`: en cada arranque se crea o actualiza la conexión **"IL-1 gpt-oss-120b - PROD"** (Groq, `openai/gpt-oss-120b`) con prioridad 0, por delante de las de `/admin`. Editarla o borrarla desde el panel no persiste. Proveedor, modelo y nombre se pueden cambiar con `AI_PROVIDER`, `AI_MODEL` y `AI_CONNECTION_LABEL`.

Con `ENVIRONMENT=production` (o `staging`), `/docs`, `/redoc` y `/api/v1/openapi.json` piden la **sesión del panel**: sin sesión llevan a `/admin/login` y vuelven solas después de entrar (con GitHub vía Clerk o con `ADMIN_USERNAME` / `ADMIN_PASSWORD`). Las cuentas de solo lectura también pueden verlas. Los endpoints de la API siguen públicos y en `development` (localhost) la documentación queda abierta. `DOCS_USERNAME` / `DOCS_PASSWORD` ya no se usan (si quedaron cargadas, se ignoran).

#### Login del panel y de la web de pruebas

- `ADMIN_AUTH=ambos` ofrece Clerk (GitHub o usuario/contraseña) y, como respaldo, el formulario con `ADMIN_USERNAME` / `ADMIN_PASSWORD`. En local se usa `ADMIN_AUTH=local` (solo el usuario del `.env`, sin Clerk).
- Al arrancar con Clerk, el backend crea o actualiza en Clerk la cuenta `ADMIN_USERNAME` con `ADMIN_PASSWORD` (aparece en el log).
- Los usuarios de GitHub y su rol (admin o solo lectura) se cargan desde `ADMIN_GITHUB_ADMINS` / `ADMIN_GITHUB_VIEWERS` y después se administran en la pestaña **Usuarios** de `/admin`.
- La web de pruebas (`TEST_WEB_URL`) pide el mismo login: toda llamada a la API desde ese origen necesita sesión. Con solo lectura, la web funciona únicamente en modo mock.

#### Login de docentes (Issue #60)

- Los docentes inician sesión en el Frontend con **Clerk** (Google o Microsoft), en una aplicación de Clerk **distinta** de la del panel. El Frontend manda el token de sesión en cada request: `Authorization: Bearer <token>`.
- Con `USERS_CLERK_JWT_KEY` configurada, `/analysis/*`, `/adaptations/*`, `/transformations/*`, `/export/*`, `/files/*` y `POST /documents/files/{file_id}` exigen ese token, **también con `?mock=true`**. Sin token, o con uno vencido, de otro origen o inválido, responden `401` con el header `WWW-Authenticate: Bearer`. `/health` sigue público.
- El token se valida sin llamadas de red con la clave pública y solo si fue emitido para un origen de `BACKEND_CORS_ORIGINS` (protección CSRF).
- Sin `USERS_CLERK_JWT_KEY` la API sigue anónima: así funciona en local y hasta que el Frontend mande el token. La web de pruebas sigue usando su propio login.

#### Roles y permisos de la API (Issue #61)

- Roles: **docente** (analiza, adapta, sube, exporta y comparte sus propios archivos) y **admin** (además configura la retención de archivos y administra usuarios).
- El rol se guarda en `publicMetadata.role` del usuario en Clerk y viaja en el token de sesión como claim `role`. Para eso, en la aplicación de Clerk de docentes, **Sessions → Customize session token** tiene que incluir `{"role": "{{user.public_metadata.role}}"}`. Sin claim, o con un valor desconocido, el rol es `docente`: es el rol por defecto al registrarse.
- Los permisos se derivan del rol en `app/core/permissions.py` (`analysis:create`, `adaptations:manage`, `transformations:manage`, `files:manage`, `files:share`, `export:create`, `settings:retention`, `users:manage`). Sin el permiso, la API responde `403`.
- Los diagnósticos, las propuestas, las decisiones y los archivos quedan a nombre de quien los crea (columna `user_id`): el id de usuario de Clerk, `test-web_<tipo>_<usuario>` desde la web de pruebas (con el rol de la API según el del panel: admin → admin, solo lectura → docente) o `anon` mientras la API es anónima.
- Un docente solo accede a lo suyo: el diagnóstico, la propuesta, el informe o el archivo de otro usuario responde `404`, igual que uno inexistente.
- **Antes de desplegar este cambio en producción** hay que aplicar la migración `0005_user_id.sql` en D1 (`cd d1-gateway && npm run migrate:remote`): con D1, el arranque verifica que esté la columna `user_id`. En SQLite local la columna se agrega sola al iniciar; lo previo queda a nombre de `anon`.
- El panel `/admin` mantiene sus propios roles (admin y solo lectura) y su login; no depende de los roles de docentes.

### Rate limit de IA

Como la API es pública, los endpoints que consumen IA real (`POST /analysis/sample`, `POST /analysis/pdf`, `POST /analysis/file`, `POST /adaptations`, `POST /transformations`, `POST /ai/test-connection` y `POST /ai/test-tts`) tienen un límite en memoria con ventanas deslizantes de 1 minuto y 24 horas. Al superarlo responden `429` con el header `Retry-After`. Las llamadas con `?mock=true` no cuentan. En `POST /transformations` el pedido cuenta recién con el material validado (un `404` o `422` no descuenta cuota), y una generación que no llama a la IA (material sin imágenes, o `no_images` con los textos alternativos del diagnóstico) no cuenta para los límites de IA.

| Variable | Default | Alcance |
| :--- | :--- | :--- |
| `AI_RATE_LIMIT_PER_IP_MINUTE` | `5` | Por IP, último minuto |
| `AI_RATE_LIMIT_PER_IP_DAY` | `50` | Por IP, últimas 24 h |
| `AI_RATE_LIMIT_PER_USER_MINUTE` | `5` | Por usuario autenticado (token de docente o web de pruebas), último minuto |
| `AI_RATE_LIMIT_PER_USER_DAY` | `50` | Por usuario autenticado, últimas 24 h |
| `AI_RATE_LIMIT_GLOBAL_MINUTE` | `20` | Todas las IP, último minuto |
| `AI_RATE_LIMIT_GLOBAL_DAY` | `500` | Todas las IP, últimas 24 h |

`0` desactiva ese límite. El global protege la cuota aunque se falsee la IP (detrás del proxy, la IP sale de `X-Forwarded-For`). Los contadores se reinician con cada deploy.

`POST /transformations` (#116) suma un tope diario por formato, por usuario autenticado (o por IP sin login), y un máximo de transformaciones generándose a la vez:

| Variable | Default | Alcance |
| :--- | :--- | :--- |
| `TRANSFORMATION_RATE_LIMIT_PER_DAY` | `20` | Por formato (sin imágenes, mapa mental, infografía), últimas 24 h |
| `TRANSFORMATION_AUDIO_RATE_LIMIT_PER_DAY` | `5` | Audio (TTS, más caro), últimas 24 h. Cuentan los guiones pedidos y los reintentos del audio |
| `TRANSFORMATION_MAX_ACTIVE_PER_USER` | `2` | Generándose a la vez por usuario (también el audio después de aceptar el guion); la siguiente responde `429` |

### Infografía

La infografía (#119) no usa modelos de generación de imágenes: escriben mal el español, no son gratis y una imagen no es accesible.

- **Contenido:** la IA devuelve un JSON con título, bajada, de 3 a 6 secciones (título, texto breve, dato destacado e ícono de una lista cerrada), un cierre y la plantilla que mejor le queda. Los campos se recortan a lo que entra legible.
- **Plantillas** (`app/services/transformations/infographic_templates.py`): `vertical`, `pasos` (numerados, para un proceso) y `comparativa` (en dos columnas).
  - El backend dibuja un **SVG con texto real**, en orden de lectura, con `role="img"`, `<title>` y `<desc>` con el texto completo, y los adornos con `aria-hidden`.
  - Los tests verifican el contraste AA de todos los pares de texto y fondo.
  - Es una propuesta inicial para que la ajuste el equipo de diseño (FigJam, Design System Obelisco): la paleta, los tamaños y los íconos están al principio del módulo.
- **Exportación:** PNG (2160 px de ancho) y PDF con PyMuPDF, que ya es una dependencia. El PDF conserva el texto real y tiene título e idioma. No hace falta Chromium en Railway, y dibujar una infografía tarda unos milisegundos.
- **Edición:** el docente puede cambiar los textos, los íconos y la plantilla antes de aceptar. El resultado editado se valida con el mismo esquema.

### Texto a voz (TTS)

El audio de los materiales (#121) lo genera **Gemini 2.5 Flash TTS** con la voz **Kore** y acento rioplatense, el motor que eligió el equipo en #120 (muestras en `/tts/` de la web de pruebas). Detalles:

- **Claves:** usa las conexiones Gemini de `/admin`, por prioridad. El modelo de TTS tiene su propia cuota en Google, así que no suma a los contadores (RPM, RPD) de la conexión ni la marca agotada para el análisis. Ante un 429 o un error, cada conexión queda en una pausa propia del TTS y se usa la siguiente.
- **Errores:** ante un límite por minuto, si no hay otra conexión libre, espera hasta ~1 minuto y sigue. Con la cuota diaria agotada o el proveedor caído, el pedido falla con un mensaje claro. Por ahora no hay un motor de fallback (`TTSProvider` en `app/services/tts/base.py` deja lugar para sumarlo).
- **Privacidad:** en la capa gratuita, Google usa el texto para mejorar sus productos. Antes de que docentes reales generen audio, las conexiones Gemini tienen que ser de un proyecto con facturación activa (≈ US$ 0,015 por minuto de audio).
- **Voz pareja:** cada llamada al motor es independiente. Para que no parezca otra persona en cada parte, todas llevan la misma instrucción de estilo (`TTS_STYLE`). Además, el backend nivela el volumen de la voz de cada fragmento antes de unirlo: sin contar los silencios y sin que los picos saturen.
- **En paralelo:** las secciones de un audio se generan de a `TTS_CONCURRENCY` a la vez y se unen en orden. Si una falla, las que esperaban turno no se piden.
- **Fragmentos:** el texto se genera por fragmentos de hasta `TTS_CHUNK_CHARS` caracteres (por párrafo y, si no entra, por oración), porque con textos largos el modelo omite partes. Los fragmentos se unen con una pausa corta.
- **Formato:** MP3 mono a 32 kbps (≈ 240 KB por minuto), codificado con `lameenc`, sin ffmpeg. La síntesis es asíncrona y la codificación corre en un hilo, así que el resto de la API sigue respondiendo mientras se genera.
- **Audio de un material (#122):**
  1. `POST /transformations` con `format = "audio"` genera un **guion para escuchar**, con título y secciones. Tiene frases cortas, y los números, las fechas, las siglas y los símbolos escritos como se dicen. Las imágenes y tablas se describen con la lógica del material sin imágenes (#117).
  2. El docente revisa o edita el guion. Recién al aceptarlo se genera el audio, así que no se gasta TTS en un guion descartado.
  3. Salen el MP3 completo (`file`) y un ZIP con un MP3 por sección (`extra_files`, los capítulos). Los dos quedan en `/files`.
  4. El guion final es la transcripción: está en `views.transcript` y se exporta en `md` o `txt`.
  5. El largo del guion está limitado por `TTS_MAX_CHARS`: un guion editado más largo responde `422`.
- **Métricas:** cada fragmento queda en `ai_usage_events` (`kind = 'tts'`) con los caracteres y los segundos de audio, y se ve en el gráfico "Texto a voz" del Resumen de `/admin`. El servicio aparece en la sección Estado.

| Variable | Default | Uso |
| :--- | :--- | :--- |
| `TTS_PROVIDER` | `gemini` | Motor de TTS (por ahora, solo Gemini) |
| `TTS_MODEL` | `gemini-2.5-flash-preview-tts` | Modelo de Gemini |
| `TTS_VOICE` | `Kore` | Voz prearmada de Gemini |
| `TTS_STYLE` | `Leé en voz alta el texto que sigue, con acento rioplatense y voz de docente…` | Instrucción de estilo, la misma antes de cada fragmento: tono, ritmo, volumen y ánimo constantes, y que suene igual que en las demás partes. Con los modelos 3.8 hay que dejarla vacía: la leen en voz alta |
| `TTS_MAX_CHARS` | `20000` | Largo máximo de un audio (≈ 20 min) |
| `TTS_CHUNK_CHARS` | `1500` | Largo máximo de cada fragmento |
| `TTS_TIMEOUT_S` | `120` | Timeout de cada fragmento |
| `TTS_CONCURRENCY` | `5` | Secciones de un audio que se generan a la vez. Con un límite por minuto bajo, los `429` se esperan solos |

---

## 🗄️ Cloudflare D1 (Worker pasarela)

El backend puede usar **SQLite** (local, por defecto) o **Cloudflare D1** (producción) según `DATABASE_BACKEND`. El backend sigue en Railway, fuera de Cloudflare: no puede usar el *binding* de D1 y la API REST de D1 comparte el límite general de la API de Cloudflare (1200 requests cada 5 min), insuficiente porque el backend escribe en cada llamada a la IA. Por eso habla con un **Worker propio** (`d1-gateway/`) que sí tiene el binding (#58).

| Endpoint del Worker | Uso |
| :--- | :--- |
| `GET /health` | Estado, sin token |
| `POST /query` | `{ "sql": "...", "params": [...] }`: una sentencia parametrizada |
| `POST /batch` | `{ "statements": [{ "sql", "params" }, ...] }`: varias sentencias atómicas (si una falla, no se aplica ninguna) |

`/query` y `/batch` exigen `Authorization: Bearer <D1_GATEWAY_TOKEN>` (comparación en tiempo constante; sin token correcto, 401). Solo aceptan sentencias con `?` y parámetros (texto, número, booleano o `null`), una por elemento. El token da acceso completo a la base: es un secreto del backend. Del lado del backend, `app/db/d1_client.py` (`D1Client`) agrega timeout y reintentos ante errores transitorios (red, 502/503/504).

**Local (sin cuenta de Cloudflare).** El backend sigue con SQLite (`DATABASE_BACKEND=sqlite`). Para probar el Worker con una D1 simulada:

```bash
cd d1-gateway
npm install
cp .dev.vars.example .dev.vars          # token local del Worker
npm run migrate:local                   # migraciones en la D1 simulada
npm run dev                             # Worker en http://127.0.0.1:8787
# en otra terminal, desde backend/:
D1_GATEWAY_URL=http://127.0.0.1:8787 D1_GATEWAY_TOKEN=token-local-de-prueba python scripts/d1_ping.py
```

Para probar desde local contra el Worker de Cloudflare, poner en el `.env` `D1_GATEWAY_URL` y `D1_GATEWAY_TOKEN` del Worker desplegado y correr `python scripts/d1_ping.py` (lecturas y escrituras con latencia p50/p95). Para correr **el backend completo** sobre D1 (el local o el de Cloudflare), además `DATABASE_BACKEND=d1`: la app exige la URL y el token y, al arrancar, que las migraciones estén aplicadas.

**Cómo funciona la capa de datos sobre D1 (#59).** Los repositorios no cambian: `get_connection()` devuelve un `D1Connection` (`app/db/d1_connection.py`) con la misma interfaz que sqlite3.

- Las lecturas se ejecutan al momento; las escrituras de un bloque `with get_connection()` se mandan juntas en **un batch atómico** al salir (equivale a la transacción de SQLite: si algo falla antes, no se aplica nada).
- Si el código necesita el resultado de una escritura (`rowcount`, `lastrowid`) o lee después de escribir, primero se mandan las escrituras pendientes.
- Los parámetros con nombre (`:nombre`) se pasan a `?`, el único formato que admite D1.
- El esquema viene de `d1-gateway/migrations/` (`0001_schema_backend.sql` es el mismo `SCHEMA` de `app/db/database.py`; un test verifica que coincidan). Un cambio de esquema necesita una migración nueva y actualizar `SCHEMA`.
- Las llamadas a la base desde código asíncrono van en hilos aparte (`asyncio.to_thread`) o en endpoints síncronos, para no bloquear el servidor mientras D1 responde.
- `TEST_DATABASE_BACKEND=d1 pytest` corre toda la suite contra el adaptador con un D1 de prueba sobre SQLite que aplica las migraciones (`tests/fake_d1.py`); el CI la corre en los dos modos.

Llamadas a D1 por request (cada una ~95 ms desde Railway en US East): análisis 2, propuesta 3, decisión 3, versión final 3, exportar 3, informe 6, métricas del panel 7, y 4 por cada llamada a la IA real.

**Producción corre sobre D1 desde el 15/10/2026** (#59). Antes, `DATABASE_PATH` apuntaba al disco del contenedor (no había volumen), así que la base se reiniciaba en cada deploy y lo cargado desde el panel se perdía; desde el corte, los datos persisten. Cómo se hizo, por si hay que repetirlo en otro entorno:

1. Aplicar el esquema en D1: `cd d1-gateway && npm run migrate:remote`.
2. En la consola de Railway: `python scripts/migrate_sqlite_to_d1.py --dry-run` y, si está bien, `python scripts/migrate_sqlite_to_d1.py`. Copia todas las tablas con sus ids y las API keys cifradas, y no pisa tablas con datos (salvo `--force`). Hacerlo **antes** de cambiar `DATABASE_BACKEND`: al arrancar sobre D1 el backend crea la conexión del `.env` y los usuarios semilla, y la copia se frenaría por tabla no vacía.
3. Enseguida, en Railway: `DATABASE_BACKEND=d1`, quitar `DATABASE_PATH` y redeploy. El arranque verifica el esquema.
4. Verificar el panel, un análisis y que aparezca en D1 (`npx wrangler d1 execute DB --remote --command "SELECT COUNT(*) FROM analyses"`).

Volver a SQLite (`DATABASE_BACKEND=sqlite`) solo tiene sentido con un volumen en Railway; sin él, la base local se pierde en cada deploy.

**Producción (solo con `wrangler`).** Desde `d1-gateway/`, con la sesión de `wrangler` en la cuenta de Cloudflare del proyecto (`npx wrangler whoami` para confirmarla):

```bash
npx wrangler d1 create contenidos-accesibles     # copiar el database_id a wrangler.toml
npm run migrate:remote
npx wrangler secret put D1_GATEWAY_TOKEN         # el mismo valor que D1_GATEWAY_TOKEN en Railway
npm run deploy
```

**Despliegue actual:** Worker `contenidos-accesibles-d1-gateway` en `https://contenidos-accesibles-d1-gateway.jamrdev2.workers.dev`, base `contenidos-accesibles` (región ENAM). `account_id` y `database_id` están fijados en `wrangler.toml`, así que `wrangler` despliega siempre a esa cuenta.

**Latencia medida** con `scripts/d1_ping.py` (incluye ida y vuelta HTTPS hasta el Worker y la consulta en D1):

| Desde | Lectura (`/query`) p50 / p95 | Escritura (`/batch` de 2) p50 / p95 | Fecha |
| :--- | :--- | :--- | :--- |
| Local (Argentina) | 164 / 171 ms | 191 / 199 ms | 15/10/2026 |
| Railway en US West (antes) | 318 / 340 ms | 340 / 449 ms | 15/10/2026 |
| **Railway en US East (actual)** | **94 / 159 ms** | **123 / 148 ms** | 15/10/2026 |

La base vive en ENAM (este de Norteamérica). Con el servicio de Railway en US West cada consulta tardaba ~320 ms; al pasarlo a **US East (Virginia)** bajó a ~95 ms. Si hace falta más velocidad: evaluar *Smart Placement* en el Worker y agrupar las escrituras de cada llamada a la IA (contadores de uso e historial) en un solo `batch`.

Los tests unitarios del cliente corren sin red. El de integración usa el Worker local si se define `D1_GATEWAY_TEST_URL` (ver `tests/test_d1_client.py`).

---

## 📁 Archivos de los docentes (Cloudflare R2)

Regla de diseño (#62): **la API no transporta archivos** y **los archivos no se guardan en la base**, solo sus metadatos (tabla `files`). El navegador sube y descarga directo con URLs firmadas de pocos minutos:

1. `POST /api/v1/files/upload-url` con `filename`, `content_type` y `size_bytes`. El backend valida formato (`.pdf`, `.docx`, `.pptx`), tipo y tamaño (máx. 10 MB), crea el registro (`pending`) y devuelve `upload.url` con `upload.headers`.
2. El navegador hace `PUT upload.url` con el archivo y **esos headers** (el `Content-Type` va firmado: si cambia, se rechaza).
3. `POST /api/v1/files/{file_id}/complete`. El backend verifica con `HEAD` que el objeto llegó con el tamaño y el tipo declarados, y que la firma binaria corresponde a la extensión (`%PDF-` o ZIP de Office). Si no coincide, lo borra y responde 422.

Para diagnosticarlo o extraerlo: `POST /api/v1/analysis/files/{file_id}` y `POST /api/v1/documents/files/{file_id}` (#63). El backend lee el objeto del lado del servidor, en memoria, con el límite de 10 MB y la validación de firma; el archivo no viaja en el pedido ni vuelve al cliente. Los endpoints multipart (`/analysis/pdf`, `/analysis/file`, `/documents/upload-pdf`, `/documents/upload`) siguen funcionando, marcados como deprecados, hasta que el frontend migre.

Para descargar: `GET /api/v1/files/{file_id}/download-url`.

**Compartir (#65).** `POST /api/v1/files/{file_id}/shares` devuelve un enlace corto del backend (`https://<backend>/s/<token>`) para pegar en el aula virtual, un mensaje o un correo. Quien lo abre recibe un `302` a una URL firmada de pocos minutos y descarga **directo de R2**; el archivo no pasa por la API.

- Se eligió un enlace con redirección y no una URL firmada de R2, porque esta dura como máximo 7 días y no se puede revocar.
- El enlace **se puede revocar** (`DELETE .../shares/{share_id}`) y deja de funcionar al instante: la redirección no se cachea (`Cache-Control: no-store`).
- Vence a las `expires_in_hours` horas, nunca después que el archivo.
- En la base se guarda el **hash SHA-256 del token**, nunca el token, así que quien lea la base no puede abrir los enlaces. Por eso el enlace completo se muestra solo al crearlo; el listado da el `share_id`, el vencimiento y la cantidad de accesos.
- `/s/{token}` tiene rate limit en memoria: `SHARE_RATE_LIMIT_PER_IP_MINUTE` (30) y `SHARE_RATE_LIMIT_GLOBAL_MINUTE` (300).
- Solo el dueño crea, lista y revoca (provisional `anon` hasta #60; el permiso `files:share` llega con #61). También se pueden compartir las exportaciones.
- Antes de desplegar, aplicar la migración `0003_file_shares.sql` en D1 (`npm run migrate:remote`).
- Cada subida, exportación, descarga y enlace queda en `file_events` (migración `0004_file_events.sql`) para las métricas del panel. Registrar un evento nunca hace fallar la operación. Las exportaciones (`/export/content` y `/export/report`) con `delivery=link` guardan el archivo generado y devuelven la misma estructura; sin ese parámetro siguen devolviendo el archivo, hasta que el frontend pase a usar enlaces.

- **Claves**: `users/<usuario>/uploads/<aleatorio>.<ext>` y `users/<usuario>/exports/...`. No son adivinables y tienen prefijo por usuario.
- **Dueño**: cada archivo es de quien lo subió (`app/core/owner.py`, ver *Roles y permisos de la API*); otro usuario recibe `404`. Mientras la API es anónima (sin `USERS_CLERK_JWT_KEY`) todos son de `anon` y el acceso depende de conocer el `file_id` (UUID aleatorio).
- **Retención (#64)**: cada archivo vence a las horas de retención vigentes al crearlo: `FILE_RETENTION_HOURS` (24 h) o la que configure un admin en `/admin` (pestaña **Uso del producto**) o con `PUT /api/v1/settings/retention` (permiso `settings:retention`), hasta `FILE_RETENTION_MAX_HOURS` (168 h). Cambiarla no altera los archivos que ya existen. Los exportados vencen, como mucho, con su diagnóstico. El valor se guarda en la tabla `app_settings` (migración `0006_app_settings.sql`).
- **Vencido = inexistente**: un archivo vencido deja de aparecer en la API y sus enlaces dejan de funcionar al instante, aunque todavía no se haya borrado.
- **Limpieza automática**: cada `FILE_CLEANUP_INTERVAL_MINUTES` (60) el backend borra de R2 y de la base los archivos vencidos, sus enlaces y las subidas que nunca se confirmaron. Si R2 falla con un archivo, se reintenta en la próxima pasada. La última ejecución se ve en `/admin`. Como respaldo, el bucket tiene una regla de lifecycle que borra lo que esté bajo `users/` 8 días después de creado: el máximo permitido (7 días) más uno de margen (`npm run r2:lifecycle`). Si se sube `FILE_RETENTION_MAX_HOURS`, hay que ajustar la regla.
- **Desarrollo** (`STORAGE_BACKEND=local`, por defecto): los archivos van a `LOCAL_STORAGE_PATH` (`local_storage/`, fuera de Git). Las URLs firmadas (HMAC) apuntan a `/api/v1/files/local/...`, que hace de R2 y solo responde en este modo. El frontend no distingue el modo.
- **Producción** (`STORAGE_BACKEND=r2`): bucket privado `contenidos-accesibles-archivos` (ENAM) con CORS solo para el frontend y la web de pruebas (`d1-gateway/r2-cors.json`). La pestaña **Estado** de `/admin` lo chequea con un `HEAD` del bucket.

**Crear el bucket** (una vez, con la cuenta del proyecto; R2 tiene que estar habilitado en el dashboard):

```bash
cd d1-gateway
npm run r2:create   # bucket privado en ENAM
npm run r2:cors     # aplica r2-cors.json (repetir si cambian los orígenes)
```

Después, en el dashboard: **R2 → Manage API tokens → Create API token** con permiso **Object Read & Write** solo sobre ese bucket. El *Access Key ID* y el *Secret Access Key* van a `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY` en Railway, junto con `R2_ACCOUNT_ID`, `R2_BUCKET` y `STORAGE_BACKEND=r2`.

**Antes de desplegar #121** hay que aplicar la migración `0009_tts_usage.sql` en D1 (`npm run migrate:remote`): agrega a `ai_usage_events` las columnas `characters` y `audio_seconds` del texto a voz. Con D1, el arranque verifica que estén.

**Antes de desplegar #116** hay que aplicar la migración `0008_transformations.sql` en D1 (`npm run migrate:remote`): crea la tabla `transformations`. Con D1, el arranque verifica que esté.

**Antes de desplegar #104** hay que aplicar la migración `0007_user_activity.sql` en D1 (`npm run migrate:remote`): crea `user_activity` y `api_users` y pasa al historial los diagnósticos, propuestas, decisiones y archivos que todavía no vencieron.

**Antes de desplegar #64** hay que aplicar la migración `0006_app_settings.sql` en D1 (`npm run migrate:remote`) y la regla de lifecycle (`npm run r2:lifecycle`).

**Antes de desplegar este cambio en producción** hay que aplicar la migración `0002_files.sql` en D1 (`npm run migrate:remote`): con D1, el arranque verifica que estén todas las tablas.

---

## 🧪 Web de pruebas (Render)

`web/` es una página estática (HTML + JS, sin build ni dependencias) para recorrer el flujo completo de la API con texto o un archivo PDF, Word o PowerPoint:

1. Material: texto, o un archivo que se sube **directo al almacenamiento** (`POST /files/upload-url` → `PUT` con progreso → `/files/{id}/complete`), una sola vez. Extracción opcional (`/documents/process-text`, `/documents/files/{file_id}`).
2. Diagnóstico (`/analysis/sample`, `/analysis/files/{file_id}`) o recuperación por `analysis_id` (`GET /analysis/{id}`).
3. Propuesta de adaptación por barrera (`POST /adaptations`), con tipo y fragmento opcional. Las barreras que citan el mismo fragmento se muestran juntas, y cada una indica su estado (sin propuesta, propuesta pendiente, resuelta o descartada) y se actualiza con cada decisión. Las resueltas y descartadas se ocultan, con opción de verlas. Una barrera con propuesta pendiente no ofrece pedir otra: lleva a la existente.
4. Revisión docente: aceptar, editar, descartar y deshacer (`/adaptations/{id}/decision`, `/undo`).
5. Registro de decisiones (`GET /adaptations/decisions`).
6. Versión adaptada (`GET /adaptations/final-version`): original y versión final lado a lado con los cambios resaltados, para copiar o descargar como `.txt`. Se regenera sola al cambiar una decisión.
7. Informe final (`GET /adaptations/report`): puntaje antes → después, resumen, decisión por barrera y penalizaciones de reglas antes/después, descargable como `.txt`. También se regenera solo.
8. Exportar el material (`docx`, `pdf`, `md`, `txt`) y el informe (`pdf`, `md`, `txt`) con `GET /export/...&delivery=link`: el archivo queda en el almacenamiento y se descarga con una URL firmada de 5 minutos.
9. Archivos y enlaces compartidos: los subidos y exportados en la sesión (o agregados por `file_id`). Por cada uno: datos, descarga (`download-url`), crear enlaces (`/files/{id}/shares`) con vigencia opcional, ver sus aperturas y revocarlos. El enlace completo se ve solo al crearlo, con botón para copiar.
10. Transformar material (`POST /transformations`): formato y material (diagnóstico actual o archivo subido). La página consulta el estado hasta `ready` o `failed`, muestra el resultado, sus vistas (lista anidada y Mermaid del mapa mental, transcripción del audio) y reproduce el audio con su vista previa, y permite aceptar, editar el JSON, descartar y exportar lo aceptado. En el audio, al aceptar el guion la página sigue el progreso de la síntesis y permite reintentarla si falla. Lo aceptado con archivo (el audio y sus capítulos) pasa a la lista del paso 9.

Si el material tiene posibles datos personales (`422 sensitive_data_detected`), la página muestra los hallazgos enmascarados y permite descartar los que no lo son y reintentar (`?dismissed=`).

`web/tts/` es una página aparte y **pública** (no carga `auth.js`, así que no pide login): la comparación de motores de texto a voz del Issue #120, con las muestras de audio para escucharlas. Queda en `/tts/` de la web de pruebas. Los scripts que generaron las muestras están en [`scripts/tts_benchmark/`](scripts/tts_benchmark/README.md).

Cada llamada queda en un registro con el request, la respuesta JSON y el `curl` equivalente. El modo mock (`?mock=true`) viene activado para no gastar cuota; se desmarca para usar la IA real.

**Login.** La página pide el mismo acceso que el panel (Clerk o el usuario del `.env`) y recibe un token de 8 h que manda en cada llamada (`Authorization: Bearer`). El backend lo exige a toda llamada cuyo `Origin` sea `TEST_WEB_URL`. Las cuentas de solo lectura solo pueden usar el modo mock. Si el backend no tiene `TEST_WEB_URL` (por ejemplo, en local sin configurarla), la página no pide login.

**Deploy (Static Site gratuito, no se duerme):**

1. En Render: **New → Blueprint** → elegir `e18-innovalab/contenidos_accesibles` con *Blueprint Path* `backend/render.yaml`. Crea el sitio `innovalab-web-pruebas` desde `backend/web/`. (Alternativa manual: **New → Static Site**, *Root Directory* `backend/web`, *Publish Directory* `.`, sin build command.)
2. En Railway, agregar la variable del backend con la URL que asignó Render:
   ```env
   TEST_WEB_URL=https://<sitio>.onrender.com
   ```
   Con eso el origen de la web se suma a CORS (no hace falta repetirlo en `BACKEND_CORS_ORIGINS`) y `/admin` muestra el enlace **"Web de pruebas"**, que la abre apuntando a ese mismo backend (`?api=<backend>`).

La URL del backend también se puede cambiar desde la propia página (queda guardada en el navegador); el valor por defecto está en `web/config.js`.

**Local:** `python -m http.server 8765 --directory web` y en el `.env` del backend `TEST_WEB_URL=http://127.0.0.1:8765` (con eso la página también pide login, igual que en Render).

---

## 🗺️ Roadmap de Backend (Plan de 12 Semanas)

- [x] **Semana 0 (Sprint Planning):** Setup del entorno, arquitectura modular, configuración de CORS y validación de Gemini API.
- [x] **Semana 0 (Infra adicional):** Panel de administración (`/admin`) para consumo de IA y rotación automática de API keys con cifrado Fernet.
- [x] **Semana 1 (Sprint 1 - Exploración):** Pipeline de procesamiento en memoria de texto y PDFs (`PyMuPDF`), primeras pruebas de análisis estructurado con IA y documentación de riesgos técnicos (`docs/`).
- [x] **Semana 2-3 (Sprint 1/2 - Flujo Completo e Ideación):** Endpoint unificado PDF -> Diagnóstico, motor de reglas automáticas en Python + lógica de puntaje orientativo (0-100) y modo Mock para Frontend.
- [ ] **Semana 4 (Sprint 2 - Escáner Funcional):** Clasificación completa de barreras por categoría y registro de resultados.
- [ ] **Semana 5-6 (Sprint 3 - Desarrollo):** Generación de adaptaciones con IA (lenguaje claro, consignas en pasos, descripciones de imágenes).
- [ ] **Semana 7-8 (Sprint 4 - Consolidación):** Consolidación de informe final y exportación del material adaptado.
- [ ] **Semana 9-10 (Sprint 5 - Iteración):** Optimización de latencias, prompts estructurados y mitigación de falsos positivos.
- [ ] **Semana 11-12 (Sprint 6 - Cierre):** Entorno estable y validaciones para el **Demo Day**.
