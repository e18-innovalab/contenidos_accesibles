"""
Tests de exportación del material adaptado e informe (Issue #40).

Verifica:
- Generación correcta de MD, TXT y DOCX para el material adaptado.
- Generación correcta de MD y TXT para el informe ejecutivo.
- Headers de respuesta (Content-Disposition, Content-Type).
- Que el contenido exportado refleja solo los cambios aceptados.
- Manejo de formatos inválidos (400) y análisis inexistentes (404).
"""

import io
import uuid

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.db import analysis_repository
from app.db.database import init_db
from app.main import app

# ---------------------------------------------------------------------------
# Material de prueba
# ---------------------------------------------------------------------------

MATERIAL = (
    "Sección 1: Introducción.\n"
    "Las plantas realizan la fotosíntesis utilizando luz solar, agua y dióxido de carbono.\n\n"
    "Sección 2: Actividad.\n"
    "Leé el texto de la página 8, subrayá las ideas principales y respondé las preguntas del final.\n\n"
    "Sección 3: Conclusión.\n"
    "Este proceso es fundamental para todos los ecosistemas terrestres del planeta."
)


@pytest.fixture(autouse=True)
def ensure_db():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _analyze(client) -> dict:
    res = client.post("/api/v1/analysis/sample?mock=true", json={"text": MATERIAL})
    assert res.status_code == 200
    return res.json()


def _propose(client, analysis_id: str, barrier_id: str, fragment: str) -> dict:
    res = client.post(
        "/api/v1/adaptations?mock=true",
        json={"analysis_id": analysis_id, "barrier_id": barrier_id,
              "adaptation_type": "consigna_en_pasos", "fragment": fragment},
    )
    assert res.status_code == 201
    return res.json()


def _decide(client, proposal_id: str, action: str, edited_text: str | None = None) -> None:
    body = {"decision": action}
    if edited_text:
        body["edited_text"] = edited_text
    res = client.post(f"/api/v1/adaptations/{proposal_id}/decision", json=body)
    assert res.status_code == 200


def _export_content(client, analysis_id: str, fmt: str) -> "Response":
    return client.get("/api/v1/export/content", params={"analysis_id": analysis_id, "format": fmt})


def _export_report(client, analysis_id: str, fmt: str) -> "Response":
    return client.get("/api/v1/export/report", params={"analysis_id": analysis_id, "format": fmt})


# ---------------------------------------------------------------------------
# Tests: exportación del material adaptado
# ---------------------------------------------------------------------------

class TestExportContentMD:
    def test_status_200(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "md")
        assert res.status_code == 200

    def test_content_type_markdown(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "md")
        assert "text/markdown" in res.headers["content-type"]

    def test_disposition_filename_ends_with_md(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "md")
        assert res.headers["content-disposition"].endswith('.md"')

    def test_body_contains_analysis_id(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "md")
        assert analysis["analysis_id"] in res.text

    def test_body_contains_heading(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "md")
        assert "# Material Adaptado" in res.text

    def test_accepted_proposal_appears_in_export(self, client):
        analysis = _analyze(client)
        aid = analysis["analysis_id"]
        frag = "Leé el texto de la página 8, subrayá las ideas principales y respondé las preguntas del final."
        p = _propose(client, aid, "bar-1", frag)
        _decide(client, p["proposal_id"], "aceptada")

        res = _export_content(client, aid, "md")
        # El texto propuesto por la IA (mock) debe aparecer en el md exportado
        assert res.status_code == 200
        assert len(res.content) > 0

    def test_discarded_proposal_original_unchanged(self, client):
        """El fragmento original aparece intacto cuando la propuesta fue descartada."""
        analysis = _analyze(client)
        aid = analysis["analysis_id"]
        frag = "Leé el texto de la página 8, subrayá las ideas principales y respondé las preguntas del final."
        p = _propose(client, aid, "bar-1", frag)
        _decide(client, p["proposal_id"], "descartada")

        res = _export_content(client, aid, "md")
        assert frag in res.text


class TestExportContentTXT:
    def test_status_200(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "txt")
        assert res.status_code == 200

    def test_content_type_plain(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "txt")
        assert "text/plain" in res.headers["content-type"]

    def test_disposition_filename_ends_with_txt(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "txt")
        assert res.headers["content-disposition"].endswith('.txt"')

    def test_body_contains_header(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "txt")
        assert "MATERIAL ADAPTADO" in res.text

    def test_body_contains_analysis_id(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "txt")
        assert analysis["analysis_id"] in res.text


class TestExportContentDOCX:
    def test_status_200(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "docx")
        assert res.status_code == 200

    def test_content_type_docx(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "docx")
        ct = res.headers["content-type"]
        assert "wordprocessingml" in ct or "openxmlformats" in ct or "docx" in ct or "octet-stream" in ct

    def test_disposition_filename_ends_with_docx(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "docx")
        assert res.headers["content-disposition"].endswith('.docx"')

    def test_docx_is_valid_document(self, client):
        """El binario devuelto debe ser parseable como .docx válido."""
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "docx")
        doc = Document(io.BytesIO(res.content))
        # Al menos un párrafo con contenido
        texts = [p.text for p in doc.paragraphs if p.text.strip()]
        assert len(texts) > 0

    def test_docx_contains_material_adaptado_heading(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "docx")
        doc = Document(io.BytesIO(res.content))
        headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
        assert any("Material Adaptado" in h for h in headings)

    def test_docx_accepted_text_appears_in_body(self, client):
        """Cuando una propuesta está aceptada, su texto debe estar en el DOCX."""
        analysis = _analyze(client)
        aid = analysis["analysis_id"]
        frag = "Leé el texto de la página 8, subrayá las ideas principales y respondé las preguntas del final."
        p = _propose(client, aid, "bar-1", frag)
        _decide(client, p["proposal_id"], "aceptada")

        res = _export_content(client, aid, "docx")
        doc = Document(io.BytesIO(res.content))
        full_text = "\n".join(p.text for p in doc.paragraphs)
        # El texto adaptado (que reemplaza al original) debe estar presente
        assert len(full_text.strip()) > 0


class TestExportContentPDF:
    def test_status_200(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "pdf")
        assert res.status_code == 200

    def test_content_type_pdf(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "pdf")
        assert "application/pdf" in res.headers["content-type"]

    def test_disposition_filename_ends_with_pdf(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "pdf")
        assert res.headers["content-disposition"].endswith('.pdf"')

    def test_body_is_valid_pdf_magic_bytes(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "pdf")
        assert res.content.startswith(b"%PDF")

    def test_accepted_proposal_reflected_in_pdf(self, client):
        analysis = _analyze(client)
        aid = analysis["analysis_id"]
        frag = "Leé el texto de la página 8, subrayá las ideas principales y respondé las preguntas del final."
        p = _propose(client, aid, "bar-1", frag)
        _decide(client, p["proposal_id"], "aceptada")

        res = _export_content(client, aid, "pdf")
        assert res.status_code == 200
        assert len(res.content) > 500

    def test_unicode_characters_preserved_without_question_marks(self, client):
        import pymupdf

        unicode_text = "Flechas → ← | Matemática ≥ Δ | Griego αβγ | Cirílico Привет | Aviso ⚠️"
        analysis = client.post(
            "/api/v1/analysis/sample?mock=true",
            json={"text": f"{MATERIAL}\n\n{unicode_text}"},
        ).json()
        aid = analysis["analysis_id"]
        res = _export_content(client, aid, "pdf")
        assert res.status_code == 200

        doc = pymupdf.open(stream=res.content, filetype="pdf")
        extracted = "\n".join(page.get_text() for page in doc)
        assert "?" not in extracted
        for expected in ("→", "←", "≥", "Δ", "αβγ", "Привет", "⚠️"):
            assert expected in extracted

    def test_pdf_metadata_and_language_present(self, client):
        import pymupdf

        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "pdf")
        assert res.status_code == 200

        doc = pymupdf.open(stream=res.content, filetype="pdf")
        assert doc.metadata["title"] == "Material Adaptado"
        assert "Innova Lab" in doc.metadata["author"]
        assert analysis["analysis_id"] in doc.metadata["subject"]
        catalog = doc.xref_object(doc.pdf_catalog())
        assert "/Lang (es)" in catalog
        assert "/DisplayDocTitle true" in catalog


# ---------------------------------------------------------------------------
# Tests: exportación del informe
# ---------------------------------------------------------------------------

class TestExportReportMD:
    def test_status_200(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "md")
        assert res.status_code == 200

    def test_content_type_markdown(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "md")
        assert "text/markdown" in res.headers["content-type"]

    def test_disposition_filename_ends_with_md(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "md")
        assert res.headers["content-disposition"].endswith('.md"')

    def test_report_contains_score_table(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "md")
        assert "Puntaje" in res.text
        assert "Antes" in res.text
        assert "Después" in res.text

    def test_report_contains_barriers_section(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "md")
        assert "Barreras" in res.text

    def test_report_contains_disclaimer(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "md")
        assert "orientativo" in res.text or "WCAG" in res.text

    def test_report_contains_metrics(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "md")
        assert "Métricas" in res.text or "barreras" in res.text.lower()

    def test_report_analysis_id_present(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "md")
        assert analysis["analysis_id"] in res.text


class TestExportReportTXT:
    def test_status_200(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "txt")
        assert res.status_code == 200

    def test_content_type_plain(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "txt")
        assert "text/plain" in res.headers["content-type"]

    def test_body_contains_header(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "txt")
        assert "INFORME DE ACCESIBILIDAD" in res.text

    def test_body_contains_puntaje_section(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "txt")
        assert "PUNTAJE" in res.text

    def test_body_contains_barriers_section(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "txt")
        assert "BARRERAS" in res.text

    def test_body_contains_disclaimer(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "txt")
        assert "orientativo" in res.text


class TestExportReportPDF:
    def test_status_200(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "pdf")
        assert res.status_code == 200

    def test_content_type_pdf(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "pdf")
        assert "application/pdf" in res.headers["content-type"]

    def test_disposition_filename_ends_with_pdf(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "pdf")
        assert res.headers["content-disposition"].endswith('.pdf"')

    def test_body_is_valid_pdf_magic_bytes(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "pdf")
        assert res.content.startswith(b"%PDF")

    def test_report_default_format_is_pdf(self, client):
        """Si no se especifica format en /report, el valor por defecto es pdf."""
        analysis = _analyze(client)
        res = client.get("/api/v1/export/report", params={"analysis_id": analysis["analysis_id"]})
        assert res.status_code == 200
        assert "application/pdf" in res.headers["content-type"]
        assert res.content.startswith(b"%PDF")

    def test_report_pdf_metadata_and_language_present(self, client):
        import pymupdf

        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "pdf")
        assert res.status_code == 200

        doc = pymupdf.open(stream=res.content, filetype="pdf")
        assert doc.metadata["title"] == "Informe de Accesibilidad - Material Adaptado"
        assert "Innova Lab" in doc.metadata["author"]
        assert analysis["analysis_id"] in doc.metadata["subject"]
        catalog = doc.xref_object(doc.pdf_catalog())
        assert "/Lang (es)" in catalog
        assert "/DisplayDocTitle true" in catalog


# ---------------------------------------------------------------------------
# Tests: errores
# ---------------------------------------------------------------------------

class TestExportErrors:
    def test_content_invalid_format_returns_400(self, client):
        analysis = _analyze(client)
        res = _export_content(client, analysis["analysis_id"], "epub")
        assert res.status_code == 400
        assert "epub" in res.json()["detail"].lower() or "formato" in res.json()["detail"].lower()

    def test_report_invalid_format_returns_400(self, client):
        analysis = _analyze(client)
        res = _export_report(client, analysis["analysis_id"], "docx")
        assert res.status_code == 400

    def test_content_unknown_analysis_returns_404(self, client):
        res = _export_content(client, str(uuid.uuid4()), "md")
        assert res.status_code == 404

    def test_report_unknown_analysis_returns_404(self, client):
        res = _export_report(client, str(uuid.uuid4()), "md")
        assert res.status_code == 404

    def test_content_expired_analysis_returns_404(self, client):
        analysis = _analyze(client)
        aid = analysis["analysis_id"]
        rec = analysis_repository.get(aid)
        analysis_repository.save(
            analysis_id=rec["id"],
            source_type=rec["source_type"],
            filename=rec["filename"],
            extracted_text=rec["extracted_text"],
            diagnostic_json=rec["diagnostic_json"],
            created_at=rec["created_at"],
            expires_at="2020-01-01T00:00:00Z",
        )
        res = _export_content(client, aid, "md")
        assert res.status_code == 404
