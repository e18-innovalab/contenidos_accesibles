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
│   │   ├── router.py                 # Panel de administración HTML (/admin), HTTP Basic Auth
│   │   ├── diagrams/                 # HTML de los diagramas servidos en /admin/diagramas
│   │   └── templates/
│   │       ├── dashboard.html        # Consumo de IA + gestión de API keys (Jinja2)
│   │       └── diagrams.html         # Índice de diagramas de arquitectura
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/            # Capa de Controladores HTTP
│   │       │   ├── health.py         # Estado del sistema y entorno
│   │       │   ├── test_ai.py        # Prueba de conectividad con IA
│   │       │   ├── documents.py      # Extracción de PDF y texto directo (PyMuPDF)
│   │       │   └── analysis.py       # Escáner de accesibilidad con IA
│   │       └── router.py             # Versionado y unificación de rutas v1
│   ├── core/
│   │   ├── config.py                 # Configuración centralizada y tipada (Pydantic Settings)
│   │   ├── crypto.py                 # Cifrado (Fernet) de las API keys guardadas en la DB
│   │   └── security.py               # HTTP Basic Auth + verificación anti-CSRF del panel admin
│   ├── db/
│   │   ├── database.py               # Conexión SQLite + creación del esquema
│   │   └── api_key_repository.py     # Único punto con SQL: CRUD de keys y contadores de uso
│   ├── schemas/
│   │   ├── document.py               # Contratos de extracción (ExtractedDocument, TextInputRequest)
│   │   └── analysis.py               # Contratos de diagnóstico (AccessibilityAnalysisResponse)
│   ├── services/
│   │   ├── document_service.py       # Extracción de PDF en memoria (PyMuPDF, párrafos por bloque) y heurísticas
│   │   ├── accessibility_service.py  # Orquestador del diagnóstico: IA + reglas, validación de citas y puntaje
│   │   ├── rules_service.py          # Motor de reglas automáticas (oraciones/párrafos extensos, visual) y puntaje
│   │   ├── key_rotation_service.py   # Rotación automática y tracking de consumo por key
│   │   ├── llm_service.py            # Orquestación multi-proveedor de modelos de lenguaje
│   │   └── llm/                      # Adaptadores de proveedores (Gemini, OpenAI-compatible)
│   └── main.py                       # Instanciación de FastAPI, Middlewares y OpenAPI
├── docs/
│   ├── riesgos_y_limitaciones_semana1.md     # Riesgos técnicos de documentos y arquitectura
│   ├── riesgos_limitaciones_semana1_ia.md    # Riesgos técnicos de IA y cuotas
│   ├── motor_reglas.md                       # Reglas automáticas, umbrales y fórmula del puntaje
│   ├── diagramas/                            # Fuentes (JSON de Archify) de /admin/diagramas
│   └── benchmarks/                           # Reportes de latencia, tokens y variabilidad
├── scripts/
│   └── benchmark_analysis.py         # Benchmark de IA y calibración de reglas (--rules-only)
├── tests/                            # Tests unitarios (pytest) y fixtures de materiales
├── app_data.db                       # DB local SQLite: API keys y contadores (IGNORADO en Git)
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

Para evitar caídas de servicio cuando se agota la capa gratuita de los proveedores de IA, el backend expone un panel interno en **`/admin`** (HTML, protegido con HTTP Basic Auth vía `ADMIN_USERNAME` / `ADMIN_PASSWORD`) que permite:

- **Visualizar el consumo en tiempo real** por cada API key: requests y tokens usados vs. los límites de la capa gratuita — **RPM** (requests/minuto), **TPM** (tokens/minuto) y **RPD** (requests/día).
- **Cargar y priorizar múltiples conexiones de IA**, cada una con sus propios umbrales configurables.
- **Rotación automática**: cuando la key activa se acerca a cualquiera de sus umbrales o recibe un error de cuota (`429`/`503`), el backend cambia automáticamente a la siguiente conexión disponible.

---

## 📖 Documentación de la API (Swagger y ReDoc)

FastAPI autogenera dos interfaces de documentación interactiva:

* **Swagger UI (Pruebas interactivas):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)  
  *Permite probar cada endpoint en vivo haciendo clic en **"Try it out"** y luego en **"Execute"**.*
* **ReDoc (Documentación técnica limpia):** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 📡 Endpoints Implementados (Semanas 0 a 3)

| Método | Endpoint | Descripción | Estado |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Bienvenida, entorno activo y enlaces a la documentación | ✅ Operativo |
| `GET` | `/api/v1/health` | Chequeo de estado y versión del backend | ✅ Operativo |
| `POST` | `/api/v1/ai/test-gemini` | Validación de conectividad con IA (con rotación automática de keys) | ✅ Operativo |
| `POST` | `/api/v1/documents/process-text` | Procesamiento y extracción de métricas de texto plano directo | ✅ Operativo |
| `POST` | `/api/v1/documents/upload-pdf` | Carga y extracción en memoria de archivos PDF (texto, páginas, imágenes y detección de escaneo) | ✅ Operativo |
| `POST` | `/api/v1/analysis/sample` | Escáner de accesibilidad IA + reglas sobre texto pegado (`application/json` o `text/plain`) con semáforo, puntaje combinado y barreras. `?mock=true` simula la IA | ✅ Operativo |
| `POST` | `/api/v1/analysis/pdf` | Escáner de accesibilidad IA + reglas sobre un PDF subido (máx. 10 MB). `?mock=true` simula la IA | ✅ Operativo |
| `POST` | `/api/v1/adaptations` | Propuesta de adaptación con IA para una barrera (`lenguaje_claro`, `consigna_en_pasos`, `reorganizar`, `mejorar_estructura`): original + propuesta + explicación, en estado `pendiente`. `?mock=true` simula la IA | ✅ Operativo |
| `GET` | `/api/v1/adaptations?analysis_id=` | Propuestas de adaptación generadas para un diagnóstico | ✅ Operativo |
| `GET` | `/api/v1/adaptations/{proposal_id}` | Recuperar una propuesta de adaptación por ID | ✅ Operativo |
| `POST` | `/api/v1/adaptations/{proposal_id}/decision` | Revisión docente: aceptar, editar (con `edited_text`) o descartar una propuesta pendiente. El original nunca se modifica | ✅ Operativo |
| `POST` | `/api/v1/adaptations/{proposal_id}/undo` | Deshacer la decisión: la propuesta vuelve a `pendiente` | ✅ Operativo |
| `GET` | `/api/v1/adaptations/decisions?analysis_id=` | Registro cronológico de decisiones y deshaceres del diagnóstico (para el informe) | ✅ Operativo |
| `GET` | `/admin` | Panel de consumo de IA y gestión de API keys (HTML, HTTP Basic Auth) | ✅ Operativo |
| `GET` | `/admin/diagramas` | Diagramas de arquitectura del backend (HTML, mismas credenciales que `/admin`). Fuentes y cómo regenerarlos en [`docs/diagramas/`](docs/diagramas/README.md) | ✅ Operativo |

> `/admin` es HTML interno, no forma parte del contrato JSON versionado — por eso no aparece en el esquema OpenAPI de `/docs`/`/redoc` (`include_in_schema=False`).

---

## 🛠️ Guía de Puesta en Marcha Local

### 1. Requisitos Previos
- Python 3.10 o superior (recomendado 3.11 a 3.13).
- Obtener una API Key gratuita de Gemini en [Google AI Studio](https://aistudio.google.com/).

### 2. Clonar el repositorio y configurar el entorno
```powershell
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
# Credenciales del panel /admin (elegí tu propia contraseña)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=una_contraseña_segura

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
Acceder al panel de administración en: **[http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)**.

### 5. Ejecutar los tests
```powershell
pip install -r requirements-dev.txt
pytest
```
Los tests no llaman a la IA. Para ver las métricas del motor de reglas sobre los materiales de ejemplo (sin consumir cuota):
```powershell
python -m scripts.benchmark_analysis --rules-only
```

---

## 🚀 Deploy en Railway

El repo ya incluye la configuración necesaria:

- `railway.json`: builder Railpack, comando de arranque (`uvicorn` en `0.0.0.0:$PORT`), healthcheck en `/api/v1/health` y **1 sola réplica** (SQLite + cooldowns en memoria no admiten más).
- `.python-version`: fija Python 3.12.

Pasos en el dashboard de Railway:

1. **New Project → Deploy from GitHub repo** → elegir este repo (rama `main`).
2. **Volume**: agregar un Volume al servicio montado en `/data`.
3. **Variables**:
   ```env
   ENVIRONMENT=production
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=<contraseña fuerte>
   DOCS_USERNAME=docs
   DOCS_PASSWORD=<contraseña fuerte, distinta de ADMIN_PASSWORD>
   AI_API_KEY=<API key de Groq>
   DB_ENCRYPTION_KEY=<generada con el comando Fernet de arriba>
   DATABASE_PATH=/data/app_data.db
   BACKEND_CORS_ORIGINS=https://<dominio-del-frontend>
   ```
   `PORT` no se define: la inyecta Railway. Guardar `DB_ENCRYPTION_KEY` en un lugar seguro: si cambia, las API keys guardadas en la DB ya no se pueden desencriptar.
4. **Settings → Networking → Generate Domain**.
5. Verificar `https://<dominio>/api/v1/health` y, si hace falta, cargar conexiones de IA de respaldo desde `https://<dominio>/admin`.

La conexión de IA principal sale de `AI_API_KEY`: en cada arranque se crea o actualiza la conexión **"IL-1 gpt-oss-120b - PROD"** (Groq, `openai/gpt-oss-120b`) con prioridad 0, por delante de las de `/admin`. Editarla o borrarla desde el panel no persiste. Proveedor, modelo y nombre se pueden cambiar con `AI_PROVIDER`, `AI_MODEL` y `AI_CONNECTION_LABEL`.

Con `ENVIRONMENT=production` (o `staging`), `/docs`, `/redoc` y `/api/v1/openapi.json` piden usuario y contraseña (HTTP Basic Auth con `DOCS_USERNAME` / `DOCS_PASSWORD`). Son credenciales propias para poder compartir Swagger con Frontend/QA sin dar acceso a `/admin`. Si falta `DOCS_PASSWORD`, la app no arranca. Los endpoints de la API siguen públicos y en `development` (localhost) la documentación queda abierta.

---

## 🧪 Web de pruebas (Render)

`web/` es una página estática (HTML + JS, sin build ni dependencias) para recorrer el flujo completo de la API con texto o PDF:

1. Extracción opcional (`/documents/process-text`, `/documents/upload-pdf`).
2. Diagnóstico (`/analysis/sample`, `/analysis/pdf`) o recuperación por `analysis_id` (`GET /analysis/{id}`).
3. Propuesta de adaptación por barrera (`POST /adaptations`), con tipo y fragmento opcional.
4. Revisión docente: aceptar, editar, descartar y deshacer (`/adaptations/{id}/decision`, `/undo`).
5. Registro de decisiones (`GET /adaptations/decisions`).

Cada llamada queda en un registro con el request, la respuesta JSON y el `curl` equivalente. El modo mock (`?mock=true`) viene activado para no gastar cuota; se desmarca para usar la IA real.

**Deploy (Static Site gratuito, no se duerme):**

1. En Render: **New → Blueprint** → elegir este repo. Toma `render.yaml` y crea el sitio `innovalab-web-pruebas` desde `web/`. (Alternativa manual: **New → Static Site**, *Root Directory* `web`, *Publish Directory* `.`, sin build command.)
2. En Railway, agregar la variable del backend con la URL que asignó Render:
   ```env
   TEST_WEB_URL=https://<sitio>.onrender.com
   ```
   Con eso el origen de la web se suma a CORS (no hace falta repetirlo en `BACKEND_CORS_ORIGINS`) y `/admin` muestra el enlace **"Web de pruebas"**, que la abre apuntando a ese mismo backend (`?api=<backend>`).

La URL del backend también se puede cambiar desde la propia página (queda guardada en el navegador); el valor por defecto está en `web/config.js`.

**Local:** `python -m http.server 8765 --directory web` y en el `.env` del backend `TEST_WEB_URL=http://127.0.0.1:8765`.

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
