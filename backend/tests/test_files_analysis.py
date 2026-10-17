"""
Diagnóstico y extracción por file_id (Issue #63): el archivo se sube al almacenamiento (#62) y
el backend lo lee del lado del servidor. Corre contra el almacenamiento local (sin red).
"""
import io
from urllib.parse import urlsplit

import pymupdf
import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.owner import current_owner
from app.db import file_repository
from app.db.database import init_db
from app.main import app
from app.services import storage_service
from app.services.storage_service import LocalStorage

ACTIVITY = (
    "Actividad 1: Leé el texto de la página 8, subrayá las ideas principales, armá un cuadro "
    "comparativo, respondé las preguntas del final y entregá todo antes del viernes."
)
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _pdf(text: str = ACTIVITY) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 400), text, fontsize=11)
    return doc.tobytes()


def _docx(text: str = ACTIVITY) -> bytes:
    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    init_db()
    storage_service.reset_storage(LocalStorage(str(tmp_path / "storage"), b"secreto-de-prueba"))
    yield TestClient(app)
    app.dependency_overrides.clear()
    storage_service.reset_storage()


def _upload(client, content: bytes, filename="material.pdf", content_type="application/pdf", complete=True) -> str:
    data = client.post("/api/v1/files/upload-url",
                       json={"filename": filename, "content_type": content_type, "size_bytes": len(content)}).json()
    url = urlsplit(data["upload"]["url"])
    assert client.put(f"{url.path}?{url.query}", content=content, headers=data["upload"]["headers"]).status_code == 200
    file_id = data["file"]["file_id"]
    if complete:
        assert client.post(f"/api/v1/files/{file_id}/complete").status_code == 200
    return file_id


@pytest.mark.parametrize(
    "content,filename,content_type,source",
    [
        (_pdf(), "material.pdf", "application/pdf", "pdf"),
        (_docx(), "clase.docx", DOCX_TYPE, "docx"),
    ],
    ids=["pdf", "docx"],
)
def test_diagnostico_por_file_id_igual_que_por_multipart(client, content, filename, content_type, source):
    file_id = _upload(client, content, filename, content_type)
    by_id = client.post(f"/api/v1/analysis/files/{file_id}?mock=true")
    assert by_id.status_code == 200, by_id.text
    multipart = client.post("/api/v1/analysis/file?mock=true", files={"file": (filename, content, content_type)})
    a, b = by_id.json(), multipart.json()
    assert a["metadata"]["source_type"] == source and a["metadata"]["filename"] == filename
    assert a["estimated_score"] == b["estimated_score"]
    assert [x["issue"] for x in a["barriers"]] == [x["issue"] for x in b["barriers"]]
    assert a["analysis_id"] != b["analysis_id"]


def test_se_puede_diagnosticar_mas_de_una_vez(client):
    file_id = _upload(client, _pdf())
    first = client.post(f"/api/v1/analysis/files/{file_id}?mock=true").json()["analysis_id"]
    second = client.post(f"/api/v1/analysis/files/{file_id}?mock=true").json()["analysis_id"]
    assert first != second


def test_extraccion_por_file_id(client):
    file_id = _upload(client, _pdf())
    r = client.post(f"/api/v1/documents/files/{file_id}")
    assert r.status_code == 200 and "subrayá las ideas principales" in r.json()["raw_text"]


def test_sin_confirmar_la_subida_es_409(client):
    file_id = _upload(client, _pdf(), complete=False)
    for path in (f"/api/v1/analysis/files/{file_id}?mock=true", f"/api/v1/documents/files/{file_id}"):
        assert client.post(path).status_code == 409


def test_inexistente_o_de_otro_usuario_es_404(client):
    assert client.post("/api/v1/analysis/files/no-existe?mock=true").status_code == 404
    file_id = _upload(client, _pdf())
    app.dependency_overrides[current_owner] = lambda: "otro-usuario"
    assert client.post(f"/api/v1/analysis/files/{file_id}?mock=true").status_code == 404
    assert client.post(f"/api/v1/documents/files/{file_id}").status_code == 404


def test_una_exportacion_no_se_diagnostica(client):
    record = file_repository.create(user_id="anon", object_key="users/anon/exports/x.pdf", filename="x.pdf",
                                    content_type="application/pdf", size_bytes=10, ttl_hours=1, kind="export",
                                    status="uploaded")
    assert client.post(f"/api/v1/analysis/files/{record['id']}?mock=true").status_code == 404


def test_objeto_borrado_del_almacenamiento_es_404(client):
    file_id = _upload(client, _pdf())
    key = file_repository.get_for_user(file_id, "anon")["object_key"]
    storage_service.get_storage().delete(key)
    r = client.post(f"/api/v1/analysis/files/{file_id}?mock=true")
    assert r.status_code == 404 and "ya no está disponible" in r.json()["detail"]


def test_objeto_cambiado_despues_de_confirmar_se_valida_igual(client):
    """Si el objeto se reemplazara en el bucket después de /complete, la firma se vuelve a validar."""
    file_id = _upload(client, _pdf())
    key = file_repository.get_for_user(file_id, "anon")["object_key"]
    storage_service.get_storage().put(key, b"<html>otra cosa</html>", "application/pdf")
    r = client.post(f"/api/v1/analysis/files/{file_id}?mock=true")
    assert r.status_code == 400 and "%PDF-" in r.json()["detail"]


def test_mas_de_10_mb_en_el_almacenamiento_es_413(client, monkeypatch):
    monkeypatch.setattr("app.api.v1.uploads.MAX_UPLOAD_SIZE_BYTES", 100)
    file_id = _upload(client, _pdf())  # el PDF de prueba pesa más de 100 bytes
    assert client.post(f"/api/v1/analysis/files/{file_id}?mock=true").status_code == 413


def test_los_endpoints_multipart_quedan_deprecados(client):
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    for path in ("/api/v1/analysis/pdf", "/api/v1/analysis/file", "/api/v1/documents/upload-pdf", "/api/v1/documents/upload"):
        assert paths[path]["post"].get("deprecated") is True
    for path in ("/api/v1/analysis/files/{file_id}", "/api/v1/documents/files/{file_id}"):
        assert not paths[path]["post"].get("deprecated")


def test_la_web_de_pruebas_sube_a_la_url_local_sin_token(client, monkeypatch):
    """La URL firmada local no puede llevar el token de la web de pruebas: su firma alcanza."""
    monkeypatch.setattr(settings, "TEST_WEB_URL", "http://web-de-pruebas.local/")
    data = client.post("/api/v1/files/upload-url",
                       json={"filename": "m.pdf", "content_type": "application/pdf", "size_bytes": 10}).json()
    url = urlsplit(data["upload"]["url"])
    put = client.put(f"{url.path}?{url.query}", content=b"%PDF-hola!",
                     headers={**data["upload"]["headers"], "Origin": "http://web-de-pruebas.local"})
    assert put.status_code == 200
    # El resto de /api/v1 desde ese origen sigue pidiendo login
    other = client.get(f"/api/v1/files/{data['file']['file_id']}", headers={"Origin": "http://web-de-pruebas.local"})
    assert other.status_code == 401
