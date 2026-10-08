from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.docs import setup_protected_docs
from app.db import analysis_repository
from app.db.database import init_db
from app.services import key_rotation_service

# En development, Swagger/ReDoc/openapi.json quedan abiertos (rutas por defecto
# de FastAPI). En staging/production se desactivan y se registran de nuevo
# detrás de HTTP Basic Auth (DOCS_USERNAME / DOCS_PASSWORD) con setup_protected_docs.
_openapi_url = f"{settings.API_V1_STR}/openapi.json"
_public_docs = not settings.docs_protected


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    key_rotation_service.sync_env_connection()
    analysis_repository.delete_expired()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="""
# 🧠 Asistente de Accesibilidad para Contenidos Educativos
*Innova Lab - Agencia de Habilidades para el Futuro*

API REST desarrollada con **FastAPI** y modelos de lenguaje de **cualquier proveedor**
(Gemini, Groq, Mistral, OpenRouter, Ollama o cualquier API compatible con OpenAI) para
analizar, diagnosticar y adaptar materiales educativos digitales (PDF, texto), reduciendo
barreras de accesibilidad y potenciando la labor pedagógica docente.

---

### 📌 Módulos de la API:
* **Health**: Verificación del estado del servidor, entorno y versión.
* **AI Integration**: Prueba de conectividad con la conexión de IA activa.
* **Documents**: Extracción de texto y PDF en memoria.
* **Accessibility Analysis**: Diagnóstico de accesibilidad con salidas estructuradas.

---

### 🛠️ Panel de Administración (`/admin`)

Fuera de esta API versionada (es HTML, no JSON) vive un panel interno protegido con
**HTTP Basic Auth** (usuario/clave definidos en `ADMIN_USERNAME` / `ADMIN_PASSWORD` del `.env`),
por eso no aparece como path en este esquema OpenAPI. Permite:

* Cargar **conexiones de IA** sin límite de cantidad: proveedor, modelo, base URL,
  API key (cifrada en reposo con Fernet), prioridad, parámetros extra y umbrales
  propios de RPM/TPM/RPD/TPD. Incluye plantillas para los proveedores más usados.
* Visualizar el consumo en tiempo real: requests y tokens usados vs. los umbrales de
  cada conexión.
* **Rotación automática entre proveedores**: se usa la conexión disponible de mayor
  prioridad; si alcanza su umbral, el proveedor la limita (429) o falla, el backend pasa
  a la siguiente —aunque sea de otro proveedor— sin caídas ni intervención manual.

Acceso: `http://<host>:<puerto>/admin` (solo en el entorno donde se despliegue; no depende
de `ENVIRONMENT`, siempre requiere las credenciales de admin).
""",
    version=settings.VERSION,
    openapi_url=_openapi_url if _public_docs else None,
    docs_url="/docs" if _public_docs else None,
    redoc_url="/redoc" if _public_docs else None,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Middleware de CORS: orígenes configurados en .env más el de la web de pruebas (TEST_WEB_URL)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registro unificado de rutas bajo el prefijo /api/v1
app.include_router(api_router, prefix=settings.API_V1_STR)

# Panel de administración (HTML interno, protegido con HTTP Basic Auth)
app.include_router(admin_router, prefix="/admin")

if settings.docs_protected:
    setup_protected_docs(app, _openapi_url)


@app.get("/", tags=["Root"], summary="Punto de bienvenida de la API")
def root():
    """
    Ruta raíz informativa.
    Devuelve el estado del entorno activo y accesos directos a la documentación.
    """
    return {
        "message": "Bienvenido a la API de Accesibilidad Educativa (Innova Lab).",
        "environment": settings.ENVIRONMENT,
        "version": settings.VERSION,
        "docs": "/docs (requiere credenciales)" if settings.docs_protected else "/docs",
        "health": f"{settings.API_V1_STR}/health",
    }
