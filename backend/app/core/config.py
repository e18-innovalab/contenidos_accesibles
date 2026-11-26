import json
from functools import lru_cache
from typing import Annotated, Literal, Union
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    # --- Panel de Administración (/admin): cuenta del .env, siempre admin ---
    ADMIN_USERNAME: str = "admin"
    # Sin default: si falta en .env, la app NO arranca (Fail-Fast).
    ADMIN_PASSWORD: SecretStr

    # --- Login del panel /admin con Clerk (aplicación de Clerk propia del panel, separada de la de docentes) ---
    # "local": solo usuario/contraseña del .env · "clerk": solo Clerk · "ambos": Clerk + el login local como respaldo
    ADMIN_AUTH: Literal["local", "clerk", "ambos"] = "ambos"
    ADMIN_CLERK_PUBLISHABLE_KEY: str | None = None
    ADMIN_CLERK_SECRET_KEY: SecretStr | None = None
    # Clave pública PEM de Clerk (JWT public key): valida los tokens sin llamadas de red
    ADMIN_CLERK_JWT_KEY: str | None = None
    # Usuarios de GitHub con acceso al panel, separados por comas. Se cargan al arrancar si no existen;
    # después se administran desde la zona de usuarios del panel.
    ADMIN_GITHUB_ADMINS: str = ""
    ADMIN_GITHUB_VIEWERS: str = ""

    # --- Login de docentes con Clerk (Issue #60): aplicación de Clerk de docentes (Google y Microsoft) ---
    # Con USERS_CLERK_JWT_KEY cargada, /analysis y /adaptations exigen el token de sesión (Authorization: Bearer).
    # Sin ella la API sigue anónima: así se usa en local y hasta que el Frontend mande el token.
    USERS_CLERK_SECRET_KEY: SecretStr | None = None
    # Clave pública PEM de la aplicación de docentes: valida los tokens sin llamadas de red
    USERS_CLERK_JWT_KEY: str | None = None

    # --- Persistencia local (SQLite) de conexiones de IA y contadores de uso ---
    DATABASE_PATH: str = "app_data.db"

    # --- Cloudflare D1 vía Worker pasarela (backend/d1-gateway, Issue #58) ---
    # "sqlite" (por defecto): base local, como siempre. "d1": usar D1 a través del Worker
    # (producción, o desde local solo para probar la conexión con Cloudflare).
    # Con "d1" toda la capa de datos usa D1 (app/db/d1_connection.py) y el esquema sale de las
    # migraciones de wrangler (d1-gateway/migrations); al arrancar solo se verifica que estén.
    DATABASE_BACKEND: Literal["sqlite", "d1"] = "sqlite"
    D1_GATEWAY_URL: str | None = None
    D1_GATEWAY_TOKEN: SecretStr | None = None
    D1_GATEWAY_TIMEOUT_S: float = 10.0

    # --- Archivos de los docentes (Issue #62) ---
    # "local" (por defecto, desarrollo): carpeta LOCAL_STORAGE_PATH, con URLs firmadas que
    # sirve el propio backend. "r2": bucket privado de Cloudflare R2 (producción); los
    # archivos van directo del navegador a R2 y nunca pasan por la API.
    STORAGE_BACKEND: Literal["local", "r2"] = "local"
    LOCAL_STORAGE_PATH: str = "local_storage"
    R2_ACCOUNT_ID: str | None = None
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: SecretStr | None = None
    R2_BUCKET: str | None = None
    # Vigencia de las URLs firmadas de subida y descarga
    FILE_UPLOAD_URL_TTL_S: int = Field(default=300, ge=30, le=3600)
    FILE_DOWNLOAD_URL_TTL_S: int = Field(default=300, ge=30, le=3600)
    # Retención de los archivos (Issue #64): valor por defecto, que un admin puede cambiar desde
    # /admin hasta FILE_RETENTION_MAX_HOURS. También se acepta el nombre anterior, FILE_TTL_HOURS.
    FILE_RETENTION_HOURS: int = Field(default=24, ge=1, validation_alias=AliasChoices("FILE_RETENTION_HOURS", "FILE_TTL_HOURS"))
    FILE_RETENTION_MAX_HOURS: int = Field(default=168, ge=1)
    # Cada cuántos minutos se borran de R2 y de la base los archivos vencidos (0 = sin limpieza programada)
    FILE_CLEANUP_INTERVAL_MINUTES: int = Field(default=60, ge=0)
    # Enlaces para compartir (Issue #65): /s/{token} redirige a una URL firmada de pocos minutos.
    # Rate limit en memoria por IP y global (0 desactiva ese límite).
    SHARE_RATE_LIMIT_PER_IP_MINUTE: int = Field(default=30, ge=0)
    SHARE_RATE_LIMIT_GLOBAL_MINUTE: int = Field(default=300, ge=0)

    # Tiempo de retención de diagnósticos antes de expirar (TTL en horas, Semana 4)
    ANALYSIS_TTL_HOURS: int = 24

    # Días que se conserva el historial de llamadas a la IA (métricas del panel)
    AI_USAGE_RETENTION_DAYS: int = 30

    # Clave simétrica (Fernet) para cifrar las API keys guardadas en la DB.
    # Generarla con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    DB_ENCRYPTION_KEY: SecretStr

    # --- Documentación (/docs, /redoc, openapi.json) ---
    # En development queda abierta. En staging/production exige la sesión del panel
    # (Clerk o ADMIN_USERNAME/ADMIN_PASSWORD; admin y solo lectura pueden verla).

    # --- Seguridad / CORS ---
    # Acepta string separado por comas o lista JSON desde el .env:
    #   BACKEND_CORS_ORIGINS=https://mi-app.vercel.app,http://localhost:3000
    #   BACKEND_CORS_ORIGINS=["https://mi-app.vercel.app","http://localhost:3000"]
    # NoDecode evita que pydantic-settings lo decodifique como JSON antes del
    # validador: sin él, el formato con comas rompe el arranque (Issue #57).
    BACKEND_CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "https://via18.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    @model_validator(mode="after")
    def require_d1_gateway(self) -> "Settings":
        """Fail-Fast: con DATABASE_BACKEND=d1 la app no arranca sin la URL y el token del Worker."""
        if self.DATABASE_BACKEND == "d1":
            missing = [
                name for name, value in (("D1_GATEWAY_URL", self.D1_GATEWAY_URL), ("D1_GATEWAY_TOKEN", self.D1_GATEWAY_TOKEN))
                if not value or (isinstance(value, SecretStr) and not value.get_secret_value())
            ]
            if missing:
                raise ValueError(f"DATABASE_BACKEND=d1 requiere {' y '.join(missing)}.")
        return self

    @model_validator(mode="after")
    def check_file_retention(self) -> "Settings":
        """Fail-Fast: la retención por defecto no puede superar el máximo permitido."""
        if self.FILE_RETENTION_HOURS > self.FILE_RETENTION_MAX_HOURS:
            raise ValueError(
                f"FILE_RETENTION_HOURS ({self.FILE_RETENTION_HOURS}) supera FILE_RETENTION_MAX_HOURS ({self.FILE_RETENTION_MAX_HOURS})."
            )
        return self

    @model_validator(mode="after")
    def require_r2_credentials(self) -> "Settings":
        """Fail-Fast: con STORAGE_BACKEND=r2 la app no arranca sin la cuenta, las credenciales y el bucket."""
        if self.STORAGE_BACKEND == "r2":
            values = {
                "R2_ACCOUNT_ID": self.R2_ACCOUNT_ID, "R2_ACCESS_KEY_ID": self.R2_ACCESS_KEY_ID,
                "R2_SECRET_ACCESS_KEY": self.R2_SECRET_ACCESS_KEY, "R2_BUCKET": self.R2_BUCKET,
            }
            missing = [
                name for name, value in values.items()
                if not value or (isinstance(value, SecretStr) and not value.get_secret_value())
            ]
            if missing:
                raise ValueError(f"STORAGE_BACKEND=r2 requiere {', '.join(missing)}.")
        return self

    @field_validator("ADMIN_CLERK_JWT_KEY", "USERS_CLERK_JWT_KEY", mode="before")
    @classmethod
    def normalize_pem(cls, v: str | None) -> str | None:
        """
        La PEM puede llegar en una línea con "\\n" literales (así queda al pegarla en el panel de
        Railway, que no interpreta escapes como el .env): se convierten en saltos de línea reales.
        """
        if not isinstance(v, str):
            return v
        v = v.strip().strip('"').strip("'").replace("\\r\\n", "\n").replace("\\n", "\n").strip()
        return v or None

    @field_validator("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", mode="before")
    @classmethod
    def clean_r2_value(cls, v: str | None) -> str | None:
        """Quita espacios, saltos de línea y comillas que quedan al pegar las credenciales en Railway."""
        if not isinstance(v, str):
            return v
        return v.strip().strip('"').strip("'").strip() or None

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, list[str]]) -> list[str]:
        """Parsea orígenes CORS desde string CSV, lista JSON o lista directa."""
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                try:
                    return json.loads(v)
                except json.JSONDecodeError as e:
                    raise ValueError(f"BACKEND_CORS_ORIGINS no es una lista JSON válida: {e}") from e
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return v
        raise ValueError(f"Formato no válido para BACKEND_CORS_ORIGINS: {v}")

    # --- Rate limit de los endpoints que consumen IA real (app/core/rate_limit.py) ---
    # Ventanas deslizantes en memoria; las llamadas con ?mock=true no cuentan.
    # 0 desactiva ese límite. El global protege la cuota aunque se falsee la IP.
    AI_RATE_LIMIT_PER_IP_MINUTE: int = Field(default=5, ge=0)
    AI_RATE_LIMIT_PER_IP_DAY: int = Field(default=50, ge=0)
    # Por usuario autenticado (docente con token o persona logueada en la web de pruebas, Issue #61)
    AI_RATE_LIMIT_PER_USER_MINUTE: int = Field(default=5, ge=0)
    AI_RATE_LIMIT_PER_USER_DAY: int = Field(default=50, ge=0)
    AI_RATE_LIMIT_GLOBAL_MINUTE: int = Field(default=20, ge=0)
    AI_RATE_LIMIT_GLOBAL_DAY: int = Field(default=500, ge=0)
    # Transformar material (Issue #116): además de los límites de IA, un tope diario por usuario
    # (o por IP sin login) y por formato. El audio es más caro que el texto (TTS, Issue #121).
    TRANSFORMATION_RATE_LIMIT_PER_DAY: int = Field(default=20, ge=0)
    TRANSFORMATION_AUDIO_RATE_LIMIT_PER_DAY: int = Field(default=5, ge=0)
    # Transformaciones generándose a la vez por usuario: las demás esperan con 429
    TRANSFORMATION_MAX_ACTIVE_PER_USER: int = Field(default=2, ge=1)

    # --- Texto a voz (TTS, Issue #121) ---
    # Motor elegido en #120: Gemini 2.5 Flash TTS con las conexiones Gemini de /admin. El modelo de
    # TTS tiene su propia cuota en Google: no suma a los contadores de la conexión (RPM, RPD) del texto.
    TTS_PROVIDER: Literal["gemini"] = "gemini"
    TTS_MODEL: str = "gemini-2.5-flash-preview-tts"
    TTS_VOICE: str = "Kore"
    # Instrucción de estilo que va antes de cada fragmento, la misma en todos: cada llamada es independiente y,
    # sin indicaciones precisas, el modelo cambia de ánimo entre partes. Con los modelos 3.8 hay que dejarla
    # vacía: la leen en voz alta.
    TTS_STYLE: str = (
        "Leé en voz alta el texto que sigue, con acento rioplatense y voz de docente que explica la clase: "
        "tono cálido y sereno, ritmo pausado y constante, volumen parejo y el mismo ánimo tranquilo de principio "
        "a fin, sin dramatizar ni cambiar de personaje. Es una parte de un audio más largo: soná exactamente igual "
        "que en las demás partes. No leas estas indicaciones:"
    )
    # Largo máximo por pedido (≈ 20 min de audio) y por fragmento: con textos largos el modelo omite partes
    TTS_MAX_CHARS: int = Field(default=20_000, ge=100)
    TTS_CHUNK_CHARS: int = Field(default=1_500, ge=200)
    TTS_TIMEOUT_S: int = Field(default=120, ge=10)
    # Secciones de un audio que se generan a la vez (#122). Con un límite por minuto bajo, los 429 se esperan solos
    TTS_CONCURRENCY: int = Field(default=5, ge=1, le=10)

    # --- Web de pruebas (web/, Static Site en Render) ---
    # URL pública de la web de pruebas. Si está definida, /admin muestra el enlace
    # y su origen se suma a CORS sin tener que repetirlo en BACKEND_CORS_ORIGINS.
    TEST_WEB_URL: str | None = None

    # --- Frontend para docentes (Vercel) ---
    # Solo para la pestaña Estado de /admin (chequeo y URL). No se suma a CORS: el origen
    # habilitado sigue saliendo de BACKEND_CORS_ORIGINS.
    FRONTEND_URL: str | None = "https://contenidos-accesibles.vercel.app/"

    # --- Plataforma de QA (tester/plataforma, Worker en Cloudflare, Issue #123) ---
    # Solo para la pestaña Estado de /admin (chequeo de /health y URL). Vacía para no chequearla.
    QA_PLATFORM_URL: str | None = "https://innovalab-qa.jamrdev2.workers.dev"

    @property
    def test_web_origin(self) -> str | None:
        """Origen (esquema + host) de la web de pruebas, o None si TEST_WEB_URL no está definida."""
        if not self.TEST_WEB_URL:
            return None
        parts = urlsplit(self.TEST_WEB_URL.strip())
        return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else None

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
    def admin_clerk_enabled(self) -> bool:
        """Clerk solo se ofrece si el modo lo permite y están las tres claves."""
        return self.ADMIN_AUTH != "local" and bool(
            self.ADMIN_CLERK_PUBLISHABLE_KEY and self.ADMIN_CLERK_SECRET_KEY and self.ADMIN_CLERK_JWT_KEY
        )

    @property
    def teacher_auth_enabled(self) -> bool:
        """El login de docentes se exige solo si está la clave pública de su aplicación de Clerk."""
        return bool(self.USERS_CLERK_JWT_KEY)

    @property
    def admin_local_login_enabled(self) -> bool:
        """El login con usuario/contraseña del .env queda como respaldo si Clerk no está configurado."""
        return self.ADMIN_AUTH != "clerk" or not self.admin_clerk_enabled

    @property
    def admin_github_seed(self) -> dict[str, str]:
        """{usuario_de_github: rol} a cargar al arrancar. Si alguien figura en las dos listas, queda como admin."""
        def parse(raw: str) -> list[str]:
            return [u.strip().lstrip("@") for u in raw.split(",") if u.strip()]

        seed = {u: "viewer" for u in parse(self.ADMIN_GITHUB_VIEWERS)}
        seed.update({u: "admin" for u in parse(self.ADMIN_GITHUB_ADMINS)})
        return seed

    @property
    def docs_protected(self) -> bool:
        """True si /docs, /redoc y openapi.json exigen credenciales."""
        return self.ENVIRONMENT != "development"


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
