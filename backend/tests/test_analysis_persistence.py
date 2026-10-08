import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.db import analysis_repository
from app.db.database import init_db
from app.main import app


@pytest.fixture(autouse=True)
def ensure_db():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def _create_sample_pdf_bytes(text: str = "Guía de Ciencias Naturales\n1. Leé el texto.\n2. Respondé.") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 400, 300), text, fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_sample_analysis_persisted_with_id_and_ttl(client):
    text = "Actividad de historia:\n1. Leé la proclama de Mayo.\n2. Explicá sus causas y consecuencias."
    response = client.post(
        "/api/v1/analysis/sample?mock=true",
        json={"text": text},
    )
    assert response.status_code == 200
    data = response.json()

    # 1. Devolver analysis_id y expires_at en el response
    assert "analysis_id" in data
    assert data["analysis_id"] is not None
    # Verifica formato UUIDv4
    uuid_obj = uuid.UUID(data["analysis_id"], version=4)
    assert str(uuid_obj) == data["analysis_id"]

    assert "expires_at" in data
    assert data["expires_at"] is not None
    assert data["expires_at"].endswith("Z")

    # 2. Guardar diagnóstico y texto extraído en SQLite
    record = analysis_repository.get(data["analysis_id"])
    assert record is not None
    assert record["id"] == data["analysis_id"]
    assert record["source_type"] == "text"
    assert record["filename"] is None
    assert text in record["extracted_text"]
    assert str(data["estimated_score"]) in record["diagnostic_json"]


def test_pdf_analysis_persisted_with_id_and_ttl(client):
    pdf_bytes = _create_sample_pdf_bytes("Trabajo Práctico de Literatura\nAnalizar el cuento propuesto.")
    response = client.post(
        "/api/v1/analysis/pdf?mock=true",
        files={"file": ("tp_literatura.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["analysis_id"] is not None
    assert data["expires_at"] is not None

    record = analysis_repository.get(data["analysis_id"])
    assert record is not None
    assert record["source_type"] == "pdf"
    assert record["filename"] == "tp_literatura.pdf"
    assert "Trabajo Práctico de Literatura" in record["extracted_text"]


def test_get_analysis_by_id_success(client):
    text = "Texto para prueba de recuperación diferida por ID."
    post_res = client.post(
        "/api/v1/analysis/sample?mock=true",
        json={"text": text},
    )
    assert post_res.status_code == 200
    created = post_res.json()
    analysis_id = created["analysis_id"]

    # Consulta diferida GET /analysis/{id}
    get_res = client.get(f"/api/v1/analysis/{analysis_id}")
    assert get_res.status_code == 200
    retrieved = get_res.json()

    assert retrieved["analysis_id"] == analysis_id
    assert retrieved["estimated_score"] == created["estimated_score"]
    assert retrieved["summary"] == created["summary"]
    assert len(retrieved["barriers"]) == len(created["barriers"])
    assert retrieved["metadata"]["provider"] == created["metadata"]["provider"]


def test_get_analysis_not_found(client):
    random_id = str(uuid.uuid4())
    res = client.get(f"/api/v1/analysis/{random_id}")
    assert res.status_code == 404
    assert res.json()["detail"] == "Diagnóstico no encontrado"


def test_get_analysis_expired_lazy_cleanup(client):
    # Guardamos un diagnóstico con fecha de expiración en el pasado
    past_iso = "2020-01-01T00:00:00Z"
    expired_id = f"expired-{uuid.uuid4()}"
    analysis_repository.save(
        analysis_id=expired_id,
        source_type="text",
        filename=None,
        extracted_text="Texto viejo expirado.",
        diagnostic_json='{"estimated_score": 80, "summary": "Viejo", "dimensions": [], "strengths": [], "barriers": [], "metadata": {"provider": "mock", "model": "mock", "connection": "mock", "latency_ms": 0, "analyzed_word_count": 3, "is_truncated": false, "unverified_fragments": 0}}',
        expires_at=past_iso,
    )

    # El registro existe en la DB
    assert analysis_repository.get(expired_id) is not None

    # Al consultarlo, debe informar que expiró (404)
    res = client.get(f"/api/v1/analysis/{expired_id}")
    assert res.status_code == 404
    assert res.json()["detail"] == "El diagnóstico ha expirado"

    # Verificamos borrado lazy: ya no está en SQLite
    assert analysis_repository.get(expired_id) is None


def test_purge_expired_analyses():
    past_iso = "2021-05-10T12:00:00Z"
    future_iso = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    id_expired = f"to-purge-{uuid.uuid4()}"
    id_valid = f"to-keep-{uuid.uuid4()}"

    analysis_repository.save(
        analysis_id=id_expired,
        source_type="text",
        filename=None,
        extracted_text="Expirado",
        diagnostic_json="{}",
        expires_at=past_iso,
    )
    analysis_repository.save(
        analysis_id=id_valid,
        source_type="text",
        filename=None,
        extracted_text="Válido",
        diagnostic_json="{}",
        expires_at=future_iso,
    )

    deleted_count = analysis_repository.delete_expired()
    assert deleted_count >= 1

    assert analysis_repository.get(id_expired) is None
    assert analysis_repository.get(id_valid) is not None

    # Limpieza final
    analysis_repository.delete(id_valid)


def test_no_pdf_file_persisted(client):
    # Criterio de aceptación: el archivo original subido nunca se persiste en disco
    backend_root = Path(__file__).resolve().parent.parent
    pdfs_before = list(backend_root.glob("*.pdf")) + list((backend_root / "app").glob("**/*.pdf"))

    pdf_bytes = _create_sample_pdf_bytes("Material sobre fotosíntesis sin persistencia en disco.")
    res = client.post(
        "/api/v1/analysis/pdf?mock=true",
        files={"file": ("efimero.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 200

    pdfs_after = list(backend_root.glob("*.pdf")) + list((backend_root / "app").glob("**/*.pdf"))
    assert set(pdfs_before) == set(pdfs_after)


def test_background_cleanup_on_new_analysis(client):
    past_iso = "2022-01-01T00:00:00Z"
    expired_id = f"bg-purge-{uuid.uuid4()}"
    analysis_repository.save(
        analysis_id=expired_id,
        source_type="text",
        filename=None,
        extracted_text="Texto para purga en background",
        diagnostic_json="{}",
        expires_at=past_iso,
    )

    assert analysis_repository.get(expired_id) is not None

    # Un nuevo análisis dispara BackgroundTask de purga
    res = client.post(
        "/api/v1/analysis/sample?mock=true",
        json={"text": "Texto que dispara limpieza en segundo plano."},
    )
    assert res.status_code == 200

    # TestClient de Starlette ejecuta las BackgroundTasks al finalizar la llamada
    assert analysis_repository.get(expired_id) is None
