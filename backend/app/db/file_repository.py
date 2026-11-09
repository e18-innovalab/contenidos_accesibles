"""Metadatos de los archivos de los docentes (Issue #62). El archivo vive en R2, no en la base."""
import uuid
from datetime import datetime, timedelta, timezone

from app.db.database import get_connection

_COLUMNS = (
    "id, user_id, object_key, kind, filename, content_type, size_bytes, status, "
    "created_at, uploaded_at, expires_at"
)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create(*, user_id: str, object_key: str, filename: str, content_type: str, size_bytes: int,
           ttl_hours: int, kind: str = "upload", status: str = "pending", not_after: str | None = None) -> dict:
    """Registra el archivo. Vence a las ttl_hours, o antes si not_after (ISO UTC) es anterior."""
    now = datetime.now(timezone.utc)
    expires_at = _iso(now + timedelta(hours=ttl_hours))
    if not_after:
        expires_at = min(expires_at, not_after)
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "object_key": object_key,
        "kind": kind,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "status": status,
        "created_at": _iso(now),
        "uploaded_at": _iso(now) if status == "uploaded" else None,
        "expires_at": expires_at,
    }
    with get_connection() as conn:
        conn.execute(
            f"INSERT INTO files ({_COLUMNS}) VALUES "
            "(:id, :user_id, :object_key, :kind, :filename, :content_type, :size_bytes, :status, "
            ":created_at, :uploaded_at, :expires_at)",
            record,
        )
    return record


def get_for_user(file_id: str, user_id: str) -> dict | None:
    """El archivo solo si es de ese usuario y no venció (si no, para el usuario no existe)."""
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM files WHERE id = ? AND user_id = ? AND expires_at > ?",
            (file_id, user_id, _iso(datetime.now(timezone.utc))),
        ).fetchone()
    return dict(row) if row else None


def list_for_user(user_id: str) -> list[dict]:
    """Archivos vigentes del usuario (Issue #155), del más reciente al más antiguo."""
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM files WHERE user_id = ? AND expires_at > ? "
            "ORDER BY created_at DESC, rowid DESC",
            (user_id, _iso(datetime.now(timezone.utc))),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_uploaded(file_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE files SET status = 'uploaded', uploaded_at = ? WHERE id = ?",
            (_iso(datetime.now(timezone.utc)), file_id),
        )


def delete(file_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))


def list_to_clean(now: str, pending_before: str, limit: int = 200) -> list[dict]:
    """Archivos vencidos y subidas que nunca se confirmaron (pendientes desde antes de pending_before)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, object_key, status, expires_at FROM files "
            "WHERE expires_at <= ? OR (status = 'pending' AND created_at < ?) ORDER BY expires_at LIMIT ?",
            (now, pending_before, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_with_shares(file_id: str) -> None:
    """Borra el registro del archivo y sus enlaces, en una sola unidad de trabajo."""
    with get_connection() as conn:
        conn.execute("DELETE FROM file_shares WHERE file_id = ?", (file_id,))
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
