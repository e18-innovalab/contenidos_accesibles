from functools import lru_cache
from typing import Literal, Union
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Entorno y Servidor ---
    # Literal restringe los valores a exactamente estos tres.
    # Si alguien escribe ENVIRONMENT=produccion en .env, la app no arranca.
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    # --- Metadatos de la API ---
    PROJECT_NAME: str = "InnovaLab - Asistente de Accesibilidad"
    API_V1_STR: str = "/api/v1"
    VERSION: str = "0.1.0"

    # DEBUG False por defecto es la postura más segura.
    # En development se puede activar desde .env (DEBUG=true).
    # Controla el nivel de detalle en errores (no la visibilidad de Swagger/ReDoc).
    DEBUG: bool = False

    # Puerto del servidor (ge=1, le=65535 valida rango TCP válido con Pydantic)
    PORT: int = Field(default=8000, ge=1, le=65535)

    # --- Conexión de IA principal (gestionada por .env) ---
    # Si AI_API_KEY está definida, en cada arranque se crea o actualiza una conexión
    # con estos datos, habilitada y con la prioridad más alta. Editarla o borrarla
    # desde /admin no persiste: se restaura al reiniciar. Las demás conexiones
    # (respaldo) se siguen gestionando desde /admin.
    AI_API_KEY: SecretStr | None = None
    # Id de una plantilla de app/services/llm/providers.py (define base_url y límites).
    AI_PROVIDER: str = "groq"
    AI_MODEL: str = "openai/gpt-oss-120b"
    AI_CONNECTION_LABEL: str = "IL-1 gpt-oss-120b - PROD"

    # Modelo asignado a las keys de Gemini de bases anteriores a multi-proveedor
    # (solo lo usa la migración de app/db/database.py).
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # --- Panel de Administración (/admin, protegido con HTTP Basic Auth) ---
    ADMIN_USERNAME: str = "admin"
    # Sin default: si falta en .env, la app NO arranca (Fail-Fast).
    ADMIN_PASSWORD: SecretStr

    # --- Persistencia local (SQLite) de conexiones de IA y contadores de uso ---
    DATABASE_PATH: str = "app_data.db"

    # Tiempo de retención de diagnósticos antes de expirar (TTL en horas, Semana 4)
    ANALYSIS_TTL_HOURS: int = 24

    # Clave simétrica (Fernet) para cifrar las API keys guardadas en la DB.
    # Generarla con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    DB_ENCRYPTION_KEY: SecretStr

    # --- Documentación (/docs, /redoc, openapi.json) ---
    # En development queda abierta. En staging/production exige HTTP Basic Auth
    # con estas credenciales, separadas de las de /admin para poder compartir
    # Swagger con Frontend/QA sin dar acceso a las API keys.
    DOCS_USERNAME: str = "docs"
    DOCS_PASSWORD: SecretStr | None = None

    # --- Seguridad / CORS ---
    # Acepta tanto lista Python como string separado por comas desde el .env
    # Ej. en .env: BACKEND_CORS_ORIGINS=https://mi-app.vercel.app,http://localhost:3000
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, list[str]]) -> list[str]:
        """Parsea orígenes CORS desde string CSV o lista directa."""
        if isinstance(v, str) and not v.startswith("["):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(f"Formato no válido para BACKEND_CORS_ORIGINS: {v}")

    # --- Rate limit de los endpoints que consumen IA real (app/core/rate_limit.py) ---
    # Ventanas deslizantes en memoria; las llamadas con ?mock=true no cuentan.
    # 0 desactiva ese límite. El global protege la cuota aunque se falsee la IP.
    AI_RATE_LIMIT_PER_IP_MINUTE: int = Field(default=5, ge=0)
    AI_RATE_LIMIT_PER_IP_DAY: int = Field(default=50, ge=0)
    AI_RATE_LIMIT_GLOBAL_MINUTE: int = Field(default=20, ge=0)
    AI_RATE_LIMIT_GLOBAL_DAY: int = Field(default=500, ge=0)

    # --- Web de pruebas (web/, Static Site en Render) ---
    # URL pública de la web de pruebas. Si está definida, /admin muestra el enlace
    # y su origen se suma a CORS sin tener que repetirlo en BACKEND_CORS_ORIGINS.
    TEST_WEB_URL: str | None = None

    @property
    def cors_origins(self) -> list[str]:
        """BACKEND_CORS_ORIGINS más el origen (esquema + host) de TEST_WEB_URL."""
        origins = list(self.BACKEND_CORS_ORIGINS)
        if self.TEST_WEB_URL:
            parts = urlsplit(self.TEST_WEB_URL.strip())
            origin = f"{parts.scheme}://{parts.netloc}"
            if parts.scheme and parts.netloc and origin not in origins:
                origins.append(origin)
        return origins

    @property
    def docs_protected(self) -> bool:
        """True si /docs, /redoc y openapi.json exigen credenciales."""
        return self.ENVIRONMENT != "development"

    @model_validator(mode="after")
    def require_docs_password(self) -> "Settings":
        """Fail-Fast: fuera de development la app no arranca sin DOCS_PASSWORD."""
        if self.docs_protected and not (
            self.DOCS_PASSWORD and self.DOCS_PASSWORD.get_secret_value()
        ):
            raise ValueError(
                f"DOCS_PASSWORD es obligatoria con ENVIRONMENT={self.ENVIRONMENT}."
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Variables extra en .env se ignoran sin lanzar error
    )


@lru_cache
def get_settings() -> Settings:
    """
    Retorna una instancia única y cacheada de Settings (patrón Singleton).

    El decorador @lru_cache garantiza que el archivo .env se lea del disco
    una sola vez durante todo el ciclo de vida de la aplicación.
    Al usar Depends(get_settings) en los endpoints, FastAPI permite
    sobreescribir la configuración fácilmente en tests automatizados.
    """
    return Settings()


# Instancia de acceso directo (para uso fuera del sistema de inyección de dependencias)
settings = get_settings()
