import sqlite3
from datetime import datetime, timezone

from app.db.database import get_connection


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "source_type": row["source_type"],
        "filename": row["filename"],
        "extracted_text": row["extracted_text"],
        "diagnostic_json": row["diagnostic_json"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
    }


_table_initialized = False


def _ensure_table(conn: sqlite3.Connection) -> None:
    global _table_initialized
    if not _table_initialized:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id                      TEXT PRIMARY KEY,
                source_type             TEXT NOT NULL,
                filename                TEXT,
                extracted_text          TEXT NOT NULL,
                diagnostic_json         TEXT NOT NULL,
                created_at              TEXT NOT NULL,
                expires_at              TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_expires_at ON analyses(expires_at);")
        _table_initialized = True


def save(
    analysis_id: str,
    source_type: str,
    filename: str | None,
    extracted_text: str,
    diagnostic_json: str,
    expires_at: str,
    created_at: str | None = None,
) -> None:
    """Guarda o actualiza un diagnóstico de accesibilidad en SQLite."""
    if created_at is None:
        created_at = _now_utc_iso()

    with get_connection() as conn:
        _ensure_table(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO analyses
                (id, source_type, filename, extracted_text, diagnostic_json, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                source_type,
                filename,
                extracted_text,
                diagnostic_json,
                created_at,
                expires_at,
            ),
        )


def get(analysis_id: str) -> dict | None:
    """Obtiene un diagnóstico por su ID único sin verificar expiración."""
    with get_connection() as conn:
        _ensure_table(conn)
        row = conn.execute(
            """
            SELECT id, source_type, filename, extracted_text, diagnostic_json, created_at, expires_at
            FROM analyses
            WHERE id = ?
            """,
            (analysis_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None


def delete(analysis_id: str) -> bool:
    """Elimina un análisis por ID. Retorna True si existía y fue eliminado."""
    with get_connection() as conn:
        _ensure_table(conn)
        cur = conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
        return cur.rowcount > 0


def delete_expired(now_iso: str | None = None) -> int:
    """
    Elimina todos los análisis cuya fecha expires_at sea anterior a now_iso.
    Retorna la cantidad de registros eliminados.
    """
    if now_iso is None:
        now_iso = _now_utc_iso()

    with get_connection() as conn:
        _ensure_table(conn)
        cur = conn.execute("DELETE FROM analyses WHERE expires_at < ?", (now_iso,))
        return cur.rowcount


def count() -> int:
    """Devuelve la cantidad total de análisis almacenados (útil para pruebas e instrumentalización)."""
    with get_connection() as conn:
        _ensure_table(conn)
        row = conn.execute("SELECT COUNT(*) AS total FROM analyses").fetchone()
        return row["total"] if row else 0
