import sqlite3

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.db import api_key_repository as repo
from app.db.database import init_db
from app.services import key_rotation_service as krs

LABEL = "IL-1 gpt-oss-120b - PROD"


@pytest.fixture
def db(tmp_path, monkeypatch):
    """DB SQLite temporal y conexión de .env configurada como en producción."""
    monkeypatch.setattr(settings, "DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "AI_API_KEY", SecretStr("gsk_prueba_1"))
    monkeypatch.setattr(settings, "AI_PROVIDER", "groq")
    monkeypatch.setattr(settings, "AI_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setattr(settings, "AI_CONNECTION_LABEL", LABEL)
    init_db()


def _backup(priority: int = 100) -> int:
    return repo.create(
        label="Respaldo", raw_key="otra", provider="gemini", base_url=None,
        model="gemini-2.5-flash", priority=priority, extra_params={},
        rpm_threshold=None, tpm_threshold=None, rpd_threshold=None, tpd_threshold=None,
    )


def test_crea_la_conexion_groq_con_prioridad_maxima(db):
    krs.sync_env_connection()
    row = repo.get_env_managed()
    assert row["label"] == LABEL
    assert row["provider"] == "groq"
    assert row["base_url"] == "https://api.groq.com/openai/v1"
    assert row["model"] == "openai/gpt-oss-120b"
    assert row["priority"] == krs.ENV_CONNECTION_PRIORITY
    assert repo.decrypt_raw_key(row) == "gsk_prueba_1"


def test_es_la_conexion_activa_aunque_existan_otras(db):
    _backup()
    krs.sync_env_connection()
    assert krs.get_active_connection().label == LABEL


def test_reinicios_no_duplican_la_conexion(db):
    krs.sync_env_connection()
    krs.sync_env_connection()
    assert repo.count_keys() == 1


def test_restaura_cambios_hechos_desde_admin(db, monkeypatch):
    krs.sync_env_connection()
    row = repo.get_env_managed()
    repo.update(
        row["id"], label="Renombrada", provider="custom", base_url="http://x", model="otro",
        priority=500, extra_params={"a": 1}, rpm_threshold=5, tpm_threshold=None,
        rpd_threshold=None, tpd_threshold=None, enabled=False,
    )
    monkeypatch.setattr(settings, "AI_API_KEY", SecretStr("gsk_prueba_2"))
    krs.sync_env_connection()

    row = repo.get_env_managed()
    assert (row["label"], row["provider"], row["model"]) == (LABEL, "groq", "openai/gpt-oss-120b")
    assert row["enabled"] == 1 and row["priority"] == krs.ENV_CONNECTION_PRIORITY
    assert repo.decrypt_raw_key(row) == "gsk_prueba_2"
    # Umbrales y parámetros extra ajustados desde /admin se conservan.
    assert row["rpm_threshold"] == 5


def test_se_recrea_si_la_borran_desde_admin(db):
    krs.sync_env_connection()
    repo.delete(repo.get_env_managed()["id"])
    krs.sync_env_connection()
    assert repo.get_env_managed()["label"] == LABEL


@pytest.mark.parametrize("key", [None, SecretStr(""), SecretStr("   ")])
def test_sin_ai_api_key_no_crea_nada(db, monkeypatch, key):
    monkeypatch.setattr(settings, "AI_API_KEY", key)
    krs.sync_env_connection()
    assert repo.count_keys() == 0


def test_proveedor_invalido_falla_al_arrancar(db, monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "inexistente")
    with pytest.raises(ValueError, match="AI_PROVIDER"):
        krs.sync_env_connection()


def test_migra_bases_sin_columna_managed_by_env(tmp_path, monkeypatch):
    path = tmp_path / "vieja.db"
    monkeypatch.setattr(settings, "DATABASE_PATH", str(path))
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE api_keys (id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT NOT NULL,"
            " encrypted_key TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,"
            " is_current INTEGER NOT NULL DEFAULT 0)"
        )
    init_db()
    with sqlite3.connect(path) as conn:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(api_keys)")}
    assert "managed_by_env" in columns
