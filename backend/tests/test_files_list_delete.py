"""
Listar y eliminar archivos del usuario (Issue #155): GET /files y DELETE /files/{file_id}.

Corre contra el almacenamiento local, igual que tests/test_files.py.
"""
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.owner import current_owner
from app.db import analysis_repository  # noqa: F401 - registra el esquema completo
from app.db.database import get_connection, init_db
from app.main import app
from app.services import storage_service
from app.services.storage_service import LocalStorage, StorageError

PDF = b"%PDF-1.7\n% prueba\n" + b"0" * 2000


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_PATH", str(tmp_path / "test.db"))
    init_db()
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    local = LocalStorage(str(tmp_path / "storage"), b"secreto-de-prueba")
    storage_service.reset_storage(local)
    yield local
    storage_service.reset_storage()


@pytest.fixture
def client(storage):
    yield TestClient(app)
    app.dependency_overrides.clear()


def _path(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}"


def _key(data: dict) -> str:
    return urlsplit(data["upload"]["url"]).path.split("/local/")[1]


def _upload(client, filename="material.pdf", confirm=True) -> dict:
    r = client.post("/api/v1/files/upload-url",
                    json={"filename": filename, "content_type": "application/pdf", "size_bytes": len(PDF)})
    assert r.status_code == 201, r.text
    data = r.json()
    assert client.put(_path(data["upload"]["url"]), content=PDF, headers=data["upload"]["headers"]).status_code == 200
    if confirm:
        assert client.post(f"/api/v1/files/{data['file']['file_id']}/complete").status_code == 200
    return data


def _count(table: str) -> int:
    with get_connection() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------------------------------------------------------------------
# GET /files
# ---------------------------------------------------------------------------

def test_listar_sin_archivos_devuelve_lista_vacia(client):
    r = client.get("/api/v1/files")
    assert r.status_code == 200 and r.json() == []


def test_listar_devuelve_los_archivos_del_mas_reciente_al_mas_antiguo(client):
    first = _upload(client, "primero.pdf")["file"]["file_id"]
    second = _upload(client, "segundo.pdf")["file"]["file_id"]
    body = client.get("/api/v1/files").json()
    assert [f["file_id"] for f in body] == [second, first]
    assert body[0]["filename"] == "segundo.pdf" and body[0]["status"] == "uploaded" and body[0]["kind"] == "upload"


def test_listar_no_muestra_archivos_de_otro_usuario_ni_vencidos(client):
    mine = _upload(client)["file"]["file_id"]
    expired = _upload(client)["file"]["file_id"]
    with get_connection() as conn:
        conn.execute("UPDATE files SET expires_at = '2020-01-01T00:00:00Z' WHERE id = ?", (expired,))
    assert [f["file_id"] for f in client.get("/api/v1/files").json()] == [mine]
    app.dependency_overrides[current_owner] = lambda: "otro-usuario"
    assert client.get("/api/v1/files").json() == []


# ---------------------------------------------------------------------------
# DELETE /files/{file_id}
# ---------------------------------------------------------------------------

def test_eliminar_borra_objeto_registro_y_enlaces(client, storage):
    data = _upload(client)
    file_id = data["file"]["file_id"]
    share = client.post(f"/api/v1/files/{file_id}/shares").json()
    assert storage.head(_key(data)) is not None and _count("file_shares") == 1

    r = client.delete(f"/api/v1/files/{file_id}")
    assert r.status_code == 204 and r.content == b""
    assert storage.head(_key(data)) is None
    assert _count("files") == 0 and _count("file_shares") == 0
    assert client.get(f"/api/v1/files/{file_id}").status_code == 404
    assert client.get("/api/v1/files").json() == []
    assert client.get(urlsplit(share["url"]).path).status_code == 404  # el enlace dejó de funcionar


def test_eliminar_una_subida_sin_confirmar(client, storage):
    data = _upload(client, confirm=False)
    assert client.delete(f"/api/v1/files/{data['file']['file_id']}").status_code == 204
    assert storage.head(_key(data)) is None and _count("files") == 0


def test_eliminar_dos_veces_o_inexistente_es_404(client):
    file_id = _upload(client)["file"]["file_id"]
    assert client.delete(f"/api/v1/files/{file_id}").status_code == 204
    assert client.delete(f"/api/v1/files/{file_id}").status_code == 404
    assert client.delete("/api/v1/files/no-existe").status_code == 404


def test_eliminar_archivo_de_otro_usuario_es_404_y_no_lo_borra(client, storage):
    data = _upload(client)
    app.dependency_overrides[current_owner] = lambda: "otro-usuario"
    assert client.delete(f"/api/v1/files/{data['file']['file_id']}").status_code == 404
    assert storage.head(_key(data)) is not None and _count("files") == 1


def test_si_el_almacenamiento_falla_no_se_borra_el_registro(client, storage, monkeypatch):
    file_id = _upload(client)["file"]["file_id"]

    def falla(key):
        raise StorageError("sin conexión")

    monkeypatch.setattr(storage, "delete", falla)
    r = client.delete(f"/api/v1/files/{file_id}")
    assert r.status_code == 502 and "almacenamiento" in r.json()["detail"]
    assert client.get(f"/api/v1/files/{file_id}").status_code == 200  # se puede reintentar
