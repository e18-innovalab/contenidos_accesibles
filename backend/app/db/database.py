import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.core.config import settings

# Cada fila es una "conexión de IA": proveedor + modelo + API key + umbrales.
# La tabla conserva el nombre api_keys por compatibilidad con bases existentes.
SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    label                   TEXT NOT NULL,
    encrypted_key           TEXT NOT NULL,
    enabled                 INTEGER NOT NULL DEFAULT 1,
    is_current              INTEGER NOT NULL DEFAULT 0,
    -- Proveedor ('gemini' usa el SDK nativo; el resto, API compatible con OpenAI)
    provider                TEXT NOT NULL DEFAULT 'gemini',
    base_url                TEXT,
    model                   TEXT NOT NULL DEFAULT '',
    -- Menor número = se usa primero. Ante un límite, se pasa a la siguiente.
    priority                INTEGER NOT NULL DEFAULT 100,
    -- JSON con parámetros propios del proveedor (ej. thinking_budget, reasoning_effort)
    extra_params            TEXT NOT NULL DEFAULT '{}',
    -- 1 = conexión principal sincronizada desde .env (AI_API_KEY) en cada arranque
    managed_by_env          INTEGER NOT NULL DEFAULT 0,
    -- Umbrales configurables por el admin, calcados de las 3 dimensiones
    -- que Google muestra en AI Studio (RPM / TPM / RPD). TPD es un extra
    -- opcional que Google no expone pero puede servir como techo propio.
    rpm_threshold           INTEGER,
    tpm_threshold           INTEGER,
    rpd_threshold           INTEGER,
    tpd_threshold           INTEGER,
    -- Contadores de ventana diaria (resetean por fecha UTC)
    request_count           INTEGER NOT NULL DEFAULT 0,
    prompt_token_count      INTEGER NOT NULL DEFAULT 0,
    candidates_token_count  INTEGER NOT NULL DEFAULT 0,
    total_token_count       INTEGER NOT NULL DEFAULT 0,
    last_reset_date         TEXT NOT NULL DEFAULT (date('now')),
    -- Contadores de ventana de minuto (resetean por minuto UTC)
    minute_request_count    INTEGER NOT NULL DEFAULT 0,
    minute_token_count      INTEGER NOT NULL DEFAULT 0,
    last_reset_minute       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M', 'now')),
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_api_keys_current
    ON api_keys(is_current) WHERE is_current = 1;

-- Diagnósticos de accesibilidad con expiración (TTL, Semana 4 - Issue #26)
CREATE TABLE IF NOT EXISTS analyses (
    id                      TEXT PRIMARY KEY,
    source_type             TEXT NOT NULL,
    filename                TEXT,
    extracted_text          TEXT NOT NULL,
    diagnostic_json         TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    expires_at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_expires_at
    ON analyses(expires_at);

-- Propuestas de adaptación con IA (Issue #27). Vencen junto con su diagnóstico.
CREATE TABLE IF NOT EXISTS adaptation_proposals (
    id                      TEXT PRIMARY KEY,
    analysis_id             TEXT NOT NULL,
    barrier_id              TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'pendiente',
    proposal_json           TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    expires_at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_adaptation_proposals_analysis
    ON adaptation_proposals(analysis_id);
CREATE INDEX IF NOT EXISTS idx_adaptation_proposals_expires_at
    ON adaptation_proposals(expires_at);

-- Registro de decisiones docentes sobre las propuestas (Issue #29), para el informe.
CREATE TABLE IF NOT EXISTS adaptation_decisions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id             TEXT NOT NULL,
    analysis_id             TEXT NOT NULL,
    barrier_id              TEXT NOT NULL,
    adaptation_type         TEXT NOT NULL,
    action                  TEXT NOT NULL,
    from_status             TEXT NOT NULL,
    to_status               TEXT NOT NULL,
    edited_text             TEXT,
    created_at              TEXT NOT NULL,
    expires_at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_adaptation_decisions_analysis
    ON adaptation_decisions(analysis_id);
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    Path(settings.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Columnas agregadas al pasar de "keys de Gemini" a "conexiones de IA".
# Las bases creadas antes no las tienen: se agregan con ALTER TABLE al iniciar.
_MULTI_PROVIDER_COLUMNS = {
    "provider": "TEXT NOT NULL DEFAULT 'gemini'",
    "base_url": "TEXT",
    "model": "TEXT NOT NULL DEFAULT ''",
    "priority": "INTEGER NOT NULL DEFAULT 100",
    "extra_params": "TEXT NOT NULL DEFAULT '{}'",
}


# Columna agregada con la conexión principal gestionada por .env (AI_API_KEY).
_ENV_CONNECTION_COLUMNS = {
    "managed_by_env": "INTEGER NOT NULL DEFAULT 0",
}

_ADDED_COLUMNS = {**_MULTI_PROVIDER_COLUMNS, **_ENV_CONNECTION_COLUMNS}


def _migrate_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(api_keys)")}
    missing = [c for c in _ADDED_COLUMNS if c not in existing]
    for column in missing:
        conn.execute(f"ALTER TABLE api_keys ADD COLUMN {column} {_ADDED_COLUMNS[column]}")
    if "model" in missing:
        # Todas las keys previas eran de Gemini con el modelo global de .env.
        conn.execute("UPDATE api_keys SET model = ?", (settings.GEMINI_MODEL,))
    if "extra_params" in missing:
        # Conserva el comportamiento anterior: thinking desactivado en el análisis.
        conn.execute("""UPDATE api_keys SET extra_params = '{"thinking_budget": 0}'""")


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _migrate_columns(conn)
