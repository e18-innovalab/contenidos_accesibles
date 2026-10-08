import json
import sqlite3
from datetime import datetime, timezone

from app.core.crypto import decrypt_value, encrypt_value
from app.db.database import get_connection


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _current_minute_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def count_keys() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM api_keys").fetchone()
        return row["n"]


def create(
    label: str,
    raw_key: str,
    provider: str,
    base_url: str | None,
    model: str,
    priority: int,
    extra_params: dict,
    rpm_threshold: int | None,
    tpm_threshold: int | None,
    rpd_threshold: int | None,
    tpd_threshold: int | None,
    managed_by_env: bool = False,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO api_keys
                (label, encrypted_key, provider, base_url, model, priority, extra_params,
                 rpm_threshold, tpm_threshold, rpd_threshold, tpd_threshold, managed_by_env)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                label,
                encrypt_value(raw_key),
                provider,
                base_url,
                model,
                priority,
                json.dumps(extra_params),
                rpm_threshold,
                tpm_threshold,
                rpd_threshold,
                tpd_threshold,
                int(managed_by_env),
            ),
        )
        new_id = cur.lastrowid

        has_current = conn.execute(
            "SELECT 1 FROM api_keys WHERE is_current = 1"
        ).fetchone()
        if has_current is None:
            conn.execute(
                "UPDATE api_keys SET is_current = 1 WHERE id = ?", (new_id,)
            )
        return new_id


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def list_all_ordered_by_priority(include_disabled: bool = True) -> list[dict]:
    query = "SELECT * FROM api_keys"
    if not include_disabled:
        query += " WHERE enabled = 1"
    query += " ORDER BY priority ASC, id ASC"
    with get_connection() as conn:
        rows = conn.execute(query).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_env_managed() -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE managed_by_env = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        return _row_to_dict(row) if row else None


def sync_env_managed(
    key_id: int,
    label: str,
    raw_key: str,
    provider: str,
    base_url: str | None,
    model: str,
    priority: int,
) -> None:
    """Reimpone los datos de .env sobre la conexión principal. Conserva
    contadores, umbrales y parámetros extra (ajustables desde /admin)."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE api_keys
            SET label = ?, encrypted_key = ?, provider = ?, base_url = ?, model = ?,
                priority = ?, enabled = 1, updated_at = datetime('now')
            WHERE id = ?
            """,
            (label, encrypt_value(raw_key), provider, base_url, model, priority, key_id),
        )


def list_all_enabled_ordered_by_priority() -> list[dict]:
    return list_all_ordered_by_priority(include_disabled=False)


def set_current(key_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE api_keys SET is_current = 0 WHERE is_current = 1")
        conn.execute(
            "UPDATE api_keys SET is_current = 1, updated_at = datetime('now') WHERE id = ?",
            (key_id,),
        )


def update(
    key_id: int,
    label: str,
    provider: str,
    base_url: str | None,
    model: str,
    priority: int,
    extra_params: dict,
    rpm_threshold: int | None,
    tpm_threshold: int | None,
    rpd_threshold: int | None,
    tpd_threshold: int | None,
    enabled: bool,
    raw_key: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE api_keys
            SET label = ?, provider = ?, base_url = ?, model = ?, priority = ?, extra_params = ?,
                rpm_threshold = ?, tpm_threshold = ?, rpd_threshold = ?, tpd_threshold = ?,
                enabled = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                label,
                provider,
                base_url,
                model,
                priority,
                json.dumps(extra_params),
                rpm_threshold,
                tpm_threshold,
                rpd_threshold,
                tpd_threshold,
                int(enabled),
                key_id,
            ),
        )
        if raw_key:
            conn.execute(
                "UPDATE api_keys SET encrypted_key = ? WHERE id = ?",
                (encrypt_value(raw_key), key_id),
            )
        if not enabled:
            conn.execute(
                "UPDATE api_keys SET is_current = 0 WHERE id = ? AND is_current = 1",
                (key_id,),
            )


def delete(key_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))


def record_usage(
    key_id: int, prompt_tokens: int, candidates_tokens: int, total_tokens: int
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE api_keys
            SET request_count = request_count + 1,
                prompt_token_count = prompt_token_count + ?,
                candidates_token_count = candidates_token_count + ?,
                total_token_count = total_token_count + ?,
                minute_request_count = minute_request_count + 1,
                minute_token_count = minute_token_count + ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (prompt_tokens, candidates_tokens, total_tokens, total_tokens, key_id),
        )


def apply_resets_if_needed(row: dict) -> dict:
    """
    Resetea, si corresponde, los contadores de ventana diaria (RPD/TPD,
    por fecha UTC) y/o de ventana de minuto (RPM/TPM, por minuto UTC).
    Es el único mecanismo de reseteo — no hay scheduler en background.
    """
    today = _today_utc()
    minute = _current_minute_utc()
    needs_day_reset = row["last_reset_date"] != today
    needs_minute_reset = row["last_reset_minute"] != minute

    if not needs_day_reset and not needs_minute_reset:
        return row

    with get_connection() as conn:
        if needs_day_reset:
            conn.execute(
                """
                UPDATE api_keys
                SET request_count = 0, prompt_token_count = 0,
                    candidates_token_count = 0, total_token_count = 0,
                    last_reset_date = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (today, row["id"]),
            )
        if needs_minute_reset:
            conn.execute(
                """
                UPDATE api_keys
                SET minute_request_count = 0, minute_token_count = 0,
                    last_reset_minute = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (minute, row["id"]),
            )
        refreshed = conn.execute(
            "SELECT * FROM api_keys WHERE id = ?", (row["id"],)
        ).fetchone()
        return _row_to_dict(refreshed)


def decrypt_raw_key(row: dict) -> str:
    return decrypt_value(row["encrypted_key"])


def parse_extra_params(row: dict) -> dict:
    try:
        value = json.loads(row["extra_params"] or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def mask(row: dict) -> str:
    raw = decrypt_raw_key(row)
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}…{raw[-4:]}"
