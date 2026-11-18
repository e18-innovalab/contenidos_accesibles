"""
Retención de archivos configurable y limpieza automática (Issue #64).

Corre con el almacenamiento local y la IA en modo mock. Los tokens de Clerk se firman con una
clave RSA de prueba (ver test_permissions.py): ningún test hace llamadas de red.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.admin import session
from app.core.config import Settings, settings
from app.db import admin_member_repository as members
from app.db.database import get_connection
from app.main import app
from app.services import retention_service, storage_service
from app.services.storage_service import StorageError
from tests.test_permissions import FRONT, MATERIAL, PDF, PUBLIC_PEM, bearer, clerk_token, storage  # noqa: F401


# Funciones y no constantes del módulo: el token se firma al usarlo y no al recolectar los tests,
# así no vence si la suite tarda (Issue #114)
def admin() -> dict:
    return bearer(clerk_token("user_admin", role="admin"))


def docente() -> dict:
    return bearer(clerk_token("user_ana"))


@pytest.fixture
def client(storage, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "USERS_CLERK_JWT_KEY", PUBLIC_PEM)
    monkeypatch.setattr(settings, "FILE_RETENTION_HOURS", 24)
    monkeypatch.setattr(settings, "FILE_RETENTION_MAX_HOURS", 168)
    return TestClient(app)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hours_left(expires_at: str) -> float:
    return (datetime.strptime(expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 3600


def _path(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}"


def _upload(client, headers=None, confirm=True) -> dict:
    headers = headers or docente()
    asked = client.post(
        "/api/v1/files/upload-url", headers=headers,
        json={"filename": "material.pdf", "content_type": "application/pdf", "size_bytes": len(PDF)},
    )
    assert asked.status_code == 201, asked.text
    data = asked.json()
    assert client.put(_path(data["upload"]["url"]), content=PDF, headers=data["upload"]["headers"]).status_code == 200
    if confirm:
        assert client.post(f"/api/v1/files/{data['file']['file_id']}/complete", headers=headers).status_code == 200
    return data["file"]


def _row(file_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return dict(row) if row else None


def _set(file_id: str, **columns) -> None:
    with get_connection() as conn:
        for column, value in columns.items():
            conn.execute(f"UPDATE files SET {column} = ? WHERE id = ?", (value, file_id))


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

def test_sin_cambios_vale_el_valor_por_defecto(client):
    info = client.get("/api/v1/settings/retention", headers=admin()).json()
    assert info["hours"] == 24 and info["default_hours"] == 24 and info["max_hours"] == 168
    assert info["source"] == "env" and info["last_cleanup"] is None
    assert 23.9 < _hours_left(_upload(client)["expires_at"]) <= 24


def test_un_admin_cambia_la_retencion_y_solo_afecta_a_los_archivos_nuevos(client):
    before = _upload(client)
    changed = client.put("/api/v1/settings/retention", json={"hours": 72}, headers=admin())
    assert changed.status_code == 200
    info = changed.json()
    assert info["hours"] == 72 and info["source"] == "panel" and info["updated_by"] == "user_admin"

    after = _upload(client)
    assert 71.9 < _hours_left(after["expires_at"]) <= 72
    assert _row(before["file_id"])["expires_at"] == before["expires_at"]  # el anterior no cambia


def test_un_docente_no_puede_ver_ni_cambiar_la_retencion(client):
    assert client.get("/api/v1/settings/retention", headers=docente()).status_code == 403
    assert client.put("/api/v1/settings/retention", json={"hours": 1}, headers=docente()).status_code == 403
    assert client.put("/api/v1/settings/retention", json={"hours": 1}).status_code == 401
    assert retention_service.file_retention_hours() == 24


@pytest.mark.parametrize("hours", [0, -5, 169])
def test_la_retencion_tiene_que_estar_entre_1_hora_y_el_maximo(client, hours):
    assert client.put("/api/v1/settings/retention", json={"hours": hours}, headers=admin()).status_code == 422
    assert retention_service.file_retention_hours() == 24


def test_si_baja_el_maximo_la_retencion_guardada_queda_topeada(client, monkeypatch):
    retention_service.set_file_retention_hours(100, updated_by="test")
    monkeypatch.setattr(settings, "FILE_RETENTION_MAX_HOURS", 48)
    assert retention_service.file_retention_hours() == 48


def test_la_retencion_por_defecto_no_puede_superar_el_maximo():
    with pytest.raises(ValueError, match="FILE_RETENTION_MAX_HOURS"):
        Settings(FILE_RETENTION_HOURS=200, FILE_RETENTION_MAX_HOURS=168)


def test_acepta_el_nombre_anterior_file_ttl_hours(monkeypatch):
    monkeypatch.setenv("FILE_TTL_HOURS", "12")
    monkeypatch.delenv("FILE_RETENTION_HOURS", raising=False)
    assert Settings().FILE_RETENTION_HOURS == 12


def test_la_politica_de_privacidad_muestra_la_retencion_vigente(client):
    retention_service.set_file_retention_hours(48, updated_by="test")
    policy = client.get("/api/v1/privacy/policy").json()
    assert policy["storage_policy"]["retention_period_hours"] == 48
    assert "48 horas" in policy["user_rights"]


def test_el_archivo_exportado_vence_con_su_diagnostico(client):
    retention_service.set_file_retention_hours(168, updated_by="test")
    analysis = client.post("/api/v1/analysis/sample?mock=true", json={"text": MATERIAL}, headers=docente()).json()
    exported = client.get(
        f"/api/v1/export/content?analysis_id={analysis['analysis_id']}&format=txt&delivery=link", headers=docente(),
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["file"]["expires_at"] == analysis["expires_at"]  # 24 h, no 168


# ---------------------------------------------------------------------------
# Vencimiento y limpieza
# ---------------------------------------------------------------------------

def test_un_archivo_vencido_no_existe_para_la_api_aunque_no_se_haya_borrado(client):
    file = _upload(client)
    share = client.post(f"/api/v1/files/{file['file_id']}/shares", headers=docente()).json()
    _set(file["file_id"], expires_at=_iso(datetime.now(timezone.utc) - timedelta(minutes=1)))

    assert client.get(f"/api/v1/files/{file['file_id']}", headers=docente()).status_code == 404
    assert client.get(f"/api/v1/files/{file['file_id']}/download-url", headers=docente()).status_code == 404
    assert client.get(urlsplit(share["url"]).path, follow_redirects=False).status_code == 404
    assert _row(file["file_id"]) is not None


def test_la_limpieza_borra_vencidos_y_subidas_abandonadas_y_conserva_lo_vigente(client, storage):  # noqa: F811
    now = datetime.now(timezone.utc)
    vigente, vencido = _upload(client), _upload(client)
    client.post(f"/api/v1/files/{vencido['file_id']}/shares", headers=docente())
    abandonado, pendiente_reciente = _upload(client, confirm=False), _upload(client, confirm=False)
    _set(vencido["file_id"], expires_at=_iso(now - timedelta(minutes=1)))
    _set(abandonado["file_id"], created_at=_iso(now - timedelta(hours=1)))
    keys = {f["file_id"]: _row(f["file_id"])["object_key"] for f in (vigente, vencido, abandonado, pendiente_reciente)}

    result = retention_service.cleanup_files()
    assert (result["expired"], result["abandoned"], result["errors"]) == (1, 1, 0)

    for gone in (vencido, abandonado):
        assert _row(gone["file_id"]) is None
        assert not storage.path_for(keys[gone["file_id"]]).exists()
    for kept in (vigente, pendiente_reciente):
        assert _row(kept["file_id"]) is not None
    assert storage.path_for(keys[vigente["file_id"]]).exists()
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM file_shares WHERE file_id = ?", (vencido["file_id"],)).fetchone()["n"] == 0

    last = retention_service.retention_info()["last_cleanup"]
    assert last["expired"] == 1 and last["abandoned"] == 1


def test_si_el_almacenamiento_falla_el_registro_queda_para_reintentar(client, monkeypatch):
    file = _upload(client)
    _set(file["file_id"], expires_at=_iso(datetime.now(timezone.utc) - timedelta(minutes=1)))

    def broken_delete(key):
        raise StorageError("R2 no respondió")

    monkeypatch.setattr(storage_service.get_storage(), "delete", broken_delete)
    assert retention_service.cleanup_files()["errors"] == 1
    assert _row(file["file_id"]) is not None


def test_la_limpieza_procesa_mas_de_un_lote(client, monkeypatch):
    monkeypatch.setattr(retention_service, "_CLEANUP_BATCH", 2)
    ids = [_upload(client)["file_id"] for _ in range(5)]
    for file_id in ids:
        _set(file_id, expires_at=_iso(datetime.now(timezone.utc) - timedelta(minutes=1)))
    assert retention_service.cleanup_files()["expired"] == 5
    assert all(_row(i) is None for i in ids)


# ---------------------------------------------------------------------------
# Panel /admin
# ---------------------------------------------------------------------------

def _panel(client, subject: str) -> TestClient:
    client.cookies.set(session.COOKIE_NAME, session.create_token(subject))
    return client


def test_en_el_panel_solo_lectura_ve_la_retencion_y_no_la_cambia(client):
    members.add("Silvanam1", "viewer")
    viewer = _panel(client, session.github_subject("silvanam1"))
    assert viewer.get("/admin/api/retention").json()["hours"] == 24
    assert viewer.put("/admin/api/retention", json={"hours": 48}).status_code == 403
    assert viewer.delete("/admin/api/retention").status_code == 403


def test_en_el_panel_un_admin_cambia_y_restablece_la_retencion(client):
    admin = _panel(client, session.local_subject())
    changed = admin.put("/admin/api/retention", json={"hours": 48})
    assert changed.status_code == 200
    assert changed.json()["hours"] == 48 and changed.json()["updated_by"] == session.local_subject()
    assert admin.put("/admin/api/retention", json={"hours": 500}).status_code == 422

    reset = admin.delete("/admin/api/retention")
    assert reset.status_code == 200 and reset.json()["source"] == "env" and reset.json()["hours"] == 24


def test_el_panel_rechaza_cambios_desde_otro_origen(client):
    admin = _panel(client, session.local_subject())
    assert admin.put("/admin/api/retention", json={"hours": 48}, headers={"Origin": "https://otro.example"}).status_code == 403


def test_sin_sesion_del_panel_responde_401(client):
    assert client.get("/admin/api/retention").status_code == 401
