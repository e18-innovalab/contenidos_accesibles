import asyncio
import os
import sqlite3
import pytest
import pymupdf
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.db import database
from app.db import api_key_repository as repo
from app.db import analysis_repository
from app.schemas.analysis import AccessibilityAnalysisResponse, AltTextProposal, AnalysisMetadata
from app.schemas.document import ExtractedDocument, ExtractedImage
from app.services.alt_text_service import (
    alt_text_service,
    AltTextBatchResponse,
    AltTextItem,
)
from app.services.accessibility_service import analyze_document, build_mock_analysis_response
from app.services.document_service import document_service
from app.services.key_rotation_service import (
    get_active_connection,
    NoVisionConnectionError,
)
from app.services.llm.base import AIConnection
from app.services.llm.providers import supports_vision
from app.services.llm_service import StructuredResult


def _create_sample_pdf_with_images(
    images_spec: list[dict],
    page_text_before: str = "Texto explicativo antes de las imágenes.",
    page_text_after: str = "Texto explicativo posterior a las imágenes.",
) -> bytes:
    """
    Crea un PDF sintético en memoria con PyMuPDF insertando texto e imágenes
    según la especificación recibida: [{'width': w, 'height': h, 'rect': (x0, y0, x1, y1)}].
    """
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 80), page_text_before, fontsize=12)

    for spec in images_spec:
        w = spec.get("width", 100)
        h = spec.get("height", 100)
        rect = pymupdf.Rect(*spec["rect"])
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), 0)
        pix.set_rect(pix.irect, (180, 120, 70))
        img_bytes = pix.tobytes("png")
        page.insert_image(rect, stream=img_bytes)

    page.insert_text((50, 720), page_text_after, fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# 1. Tests de Esquemas y Privacidad
# ---------------------------------------------------------------------------

def test_alt_text_proposal_and_extracted_image_schemas():
    """Valida los esquemas Pydantic y confirma que los bytes no se serializan (Privacy by Design)."""
    img = ExtractedImage(
        image_index=1,
        page_number=1,
        bbox=(50.0, 100.0, 150.0, 200.0),
        width=100,
        height=100,
        location_description="Página 1, sector central",
        context_text="Contexto pedagógico",
        image_bytes=b"\x89PNG\r\n\x1a\nfakeimagebytes",
        mime_type="image/png",
    )
    dumped = img.model_dump()
    assert "image_bytes" not in dumped, "Los bytes binarios jamás deben serializarse en el dict/JSON"
    assert dumped["image_index"] == 1
    assert dumped["location_description"] == "Página 1, sector central"

    proposal = AltTextProposal(
        image_index=1,
        page_number=1,
        location_description="Página 1, sector central",
        suggested_alt_text="Diagrama de flujo del ciclo del agua.",
        pedagogical_purpose="Explicar las fases de evaporación y condensación.",
        context_used="Contexto pedagógico",
    )
    assert proposal.image_index == 1
    assert "Diagrama" in proposal.suggested_alt_text


# ---------------------------------------------------------------------------
# 2. Extracción espacial y filtrado de decorativas en DocumentService
# ---------------------------------------------------------------------------

def test_extract_relevant_images_and_context():
    """Verifica que una imagen de contenido relevante se extraiga con su contexto espacial y ubicación."""
    pdf_bytes = _create_sample_pdf_with_images([
        {"width": 120, "height": 100, "rect": (50, 150, 200, 280)}
    ])
    doc = document_service.process_pdf(pdf_bytes, filename="material.pdf")

    assert doc.has_images is True
    assert doc.image_count == 1
    assert len(doc.extracted_images) == 1

    extracted = doc.extracted_images[0]
    assert extracted.image_index == 1
    assert extracted.page_number == 1
    assert "Página 1" in extracted.location_description
    assert "sector superior" in extracted.location_description
    assert "Texto explicativo antes" in extracted.context_text
    assert extracted.image_bytes.startswith(b"\x89PNG")


def _pdf_with_pixmap(pix: pymupdf.Pixmap, fmt: str = "png") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 80), "Texto antes de la imagen.", fontsize=12)
    page.insert_image(pymupdf.Rect(50, 150, 200, 280), stream=pix.tobytes(fmt))
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_extract_cmyk_image_converts_to_png():
    """Una imagen CMYK sin alfa (n=4) se convierte a RGB en vez de fallar con 'unsupported colorspace'."""
    pix = pymupdf.Pixmap(pymupdf.csCMYK, pymupdf.IRect(0, 0, 120, 100), 0)
    pix.set_rect(pix.irect, (0, 120, 200, 10))

    extracted_doc = document_service.process_pdf(_pdf_with_pixmap(pix, "pam"), filename="cmyk.pdf")

    assert len(extracted_doc.extracted_images) == 1
    assert extracted_doc.extracted_images[0].image_bytes.startswith(b"\x89PNG")


def test_extract_transparent_image_renders_page_zone():
    """Con transparencia (smask) se renderiza la zona: lo transparente se ve como el fondo blanco de la página."""
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 100), 1)
    pix.set_rect(pix.irect, (180, 120, 70, 0))  # color presente pero 100% transparente

    extracted_doc = document_service.process_pdf(_pdf_with_pixmap(pix), filename="transparente.pdf")

    assert len(extracted_doc.extracted_images) == 1
    rendered = pymupdf.Pixmap(extracted_doc.extracted_images[0].image_bytes)
    assert rendered.pixel(rendered.width // 2, rendered.height // 2) == (255, 255, 255)


def test_extract_image_falls_back_to_page_render_when_decode_fails():
    """Si decodificar la imagen embebida falla, se usa el render de la zona en vez de descartarla."""
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 100), 0)
    pix.set_rect(pix.irect, (180, 120, 70))
    pdf_bytes = _pdf_with_pixmap(pix)

    with patch.object(
        type(document_service), "_decode_embedded_png", side_effect=RuntimeError("decode error simulado")
    ):
        extracted_doc = document_service.process_pdf(pdf_bytes, filename="decode_falla.pdf")

    assert len(extracted_doc.extracted_images) == 1
    rendered = pymupdf.Pixmap(extracted_doc.extracted_images[0].image_bytes)
    assert rendered.pixel(rendered.width // 2, rendered.height // 2) == (180, 120, 70)


def test_unprocessable_image_adds_manual_review_warning():
    """Si ningún método procesa la imagen, el análisis sigue y avisa dónde está para revisarla a mano."""
    pdf_bytes = _create_sample_pdf_with_images([
        {"width": 120, "height": 100, "rect": (50, 300, 200, 430)}
    ])

    with patch.object(type(document_service), "_encode_image_png", return_value=None):
        extracted_doc = document_service.process_pdf(pdf_bytes, filename="ilegible.pdf")

    assert extracted_doc.extracted_images == []
    assert extracted_doc.image_count == 1
    assert any(
        "página 1, sector central" in w and "manualmente" in w for w in extracted_doc.warnings
    )


def test_filter_decorative_and_tiny_images():
    """Descarta íconos muy chicos (<60px), líneas con aspect ratio extremo y encabezados/pies repetitivos."""
    pdf_bytes = _create_sample_pdf_with_images([
        # 1. Ícono muy chico (<60px ancho/alto)
        {"width": 30, "height": 30, "rect": (50, 120, 75, 145)},
        # 2. Divisor horizontal o línea alargada (aspect ratio > 8.0)
        {"width": 300, "height": 10, "rect": (50, 200, 450, 210)},
        # 3. Logo en zona de encabezado superior (y1 < 7% de 800 = 56)
        {"width": 80, "height": 40, "rect": (50, 10, 150, 50)},
        # 4. Imagen válida de contenido
        {"width": 150, "height": 120, "rect": (50, 300, 250, 450)},
    ])
    doc = document_service.process_pdf(pdf_bytes, filename="con_decorativas.pdf")

    assert doc.image_count == 4
    # Solo 1 debe superar los filtros
    assert len(doc.extracted_images) == 1
    assert doc.extracted_images[0].location_description == "Página 1, sector central"


def test_image_cap_and_warning():
    """Limita la extracción a un máximo de 5 imágenes y emite una advertencia pedagógica."""
    specs = [
        {"width": 100, "height": 80, "rect": (50, 100 + i * 70, 150, 150 + i * 70)}
        for i in range(7)
    ]
    pdf_bytes = _create_sample_pdf_with_images(specs)
    doc = document_service.process_pdf(pdf_bytes, filename="muchas_imagenes.pdf")

    assert doc.image_count == 7
    assert len(doc.extracted_images) == 5
    assert any("primeras 5" in w for w in doc.warnings)


# ---------------------------------------------------------------------------
# 3. Detección de visión y rotación de claves (Mejora C)
# ---------------------------------------------------------------------------

def test_supports_vision_detection():
    """Verifica la detección determinística de capacidades multimodales por proveedor y preset."""
    # Gemini nativo soporta visión
    assert supports_vision("gemini", "gemini-2.5-flash") is True
    # Groq gpt-oss-120b es solo texto
    assert supports_vision("groq", "openai/gpt-oss-120b") is False
    # Modelos OpenAI compatibles con visión
    assert supports_vision("custom", "gpt-4o") is True
    assert supports_vision("openrouter", "meta-llama/llama-3.2-11b-vision-instruct:free") is True
    # Extra params explícito
    assert supports_vision("custom", "custom-model", extra_params={"supports_vision": True}) is True
    assert supports_vision("mistral", "mistral-small-latest", extra_params={}) is False


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Base de datos aislada para pruebas de rotación de claves."""
    db_file = str(tmp_path / "test_vision.db")
    monkeypatch.setattr(settings, "DATABASE_PATH", db_file)
    database.init_db()
    yield db_file


def test_key_rotation_filters_vision_connection(temp_db):
    """Valida que get_active_connection(require_vision=True) seleccione solo proveedores con visión."""
    # Conexión 1: Groq (prioridad 10 - principal de texto)
    repo.create(
        label="Groq Principal (Texto)",
        raw_key="gsk_test123",
        provider="groq",
        base_url="https://api.groq.com/openai/v1",
        model="openai/gpt-oss-120b",
        priority=10,
        extra_params={},
        rpm_threshold=None,
        tpm_threshold=None,
        rpd_threshold=None,
        tpd_threshold=None,
    )
    # Conexión 2: Gemini (prioridad 20 - visión secundaria)
    repo.create(
        label="Google Gemini (Visión)",
        raw_key="gemini_test123",
        provider="gemini",
        base_url=None,
        model="gemini-2.5-flash",
        priority=20,
        extra_params={},
        rpm_threshold=None,
        tpm_threshold=None,
        rpd_threshold=None,
        tpd_threshold=None,
    )

    # Consulta normal sin visión -> Elige Groq (prioridad 10)
    normal_conn = get_active_connection(require_vision=False)
    assert normal_conn.provider == "groq"
    assert normal_conn.label == "Groq Principal (Texto)"

    # Consulta con require_vision=True -> Saltea Groq y elige Gemini (prioridad 20)
    vision_conn = get_active_connection(require_vision=True)
    assert vision_conn.provider == "gemini"
    assert vision_conn.label == "Google Gemini (Visión)"


def test_key_rotation_raises_when_no_vision_available(temp_db):
    """Si no hay conexiones con visión habilitadas, debe elevar NoVisionConnectionError."""
    repo.create(
        label="Groq Text Only",
        raw_key="gsk_test",
        provider="groq",
        base_url="https://api.groq.com/openai/v1",
        model="openai/gpt-oss-120b",
        priority=10,
        extra_params={},
        rpm_threshold=None,
        tpm_threshold=None,
        rpd_threshold=None,
        tpd_threshold=None,
    )
    with pytest.raises(NoVisionConnectionError):
        get_active_connection(require_vision=True)



# ---------------------------------------------------------------------------
# 4. Modo Mock y Generación en Lote (Mejora A)
# ---------------------------------------------------------------------------

def test_generate_mock_proposals():
    """Verifica que el modo mock genere propuestas estructuradas coherentes con 0 tokens."""
    img = ExtractedImage(
        image_index=1,
        page_number=2,
        bbox=(50.0, 100.0, 200.0, 250.0),
        width=150,
        height=150,
        location_description="Página 2, sector central",
        context_text="En la siguiente figura se observa el ciclo celular.",
        image_bytes=b"bytes",
    )
    proposals = alt_text_service.generate_mock_proposals([img])
    assert len(proposals) == 1
    p = proposals[0]
    assert p.image_index == 1
    assert p.page_number == 2
    assert p.location_description == "Página 2, sector central"
    assert "[MOCK]" in p.suggested_alt_text
    assert p.pedagogical_purpose is not None
    assert "ciclo celular" in p.context_used


def test_alt_text_service_batch_call():
    """Verifica que generate_proposals ejecute una única llamada multimodal en lote."""
    images = [
        ExtractedImage(
            image_index=1,
            page_number=1,
            bbox=(50.0, 100.0, 200.0, 200.0),
            width=100,
            height=100,
            location_description="Página 1, sector superior",
            context_text="El mapa conceptual de la fotosíntesis.",
            image_bytes=b"png1",
        ),
        ExtractedImage(
            image_index=2,
            page_number=1,
            bbox=(50.0, 300.0, 200.0, 400.0),
            width=100,
            height=100,
            location_description="Página 1, sector central",
            context_text="Esquema de la célula vegetal.",
            image_bytes=b"png2",
        ),
    ]

    mock_batch_response = AltTextBatchResponse(
        proposals=[
            AltTextItem(
                image_index=1,
                suggested_alt_text="Mapa conceptual que desglosa las fases lumínica y oscura de la fotosíntesis.",
                pedagogical_purpose="Identificar reactivos y productos principales del proceso biológico.",
            ),
            AltTextItem(
                image_index=2,
                suggested_alt_text="Esquema transversal de una célula vegetal con señalización de cloroplastos y pared celular.",
                pedagogical_purpose="Diferenciar los orgánulos específicos de la célula vegetal.",
            ),
        ]
    )

    async def _run():
        with patch("app.services.alt_text_service.llm_service.generate_structured", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = StructuredResult(
                parsed=mock_batch_response,
                provider="gemini",
                model="gemini-2.5-flash",
                connection_label="Google Gemini",
                latency_ms=850,
                usage=None,
            )

            proposals = await alt_text_service.generate_proposals(images)

            # Confirmar que se ejecutó EXACTAMENTE 1 sola llamada en lote (Mejora A)
            assert mock_gen.call_count == 1
            _, kwargs = mock_gen.call_args
            assert kwargs["require_vision"] is True
            contents = kwargs["contents"]
            # Debe contener la introducción textual + 2 pares de (imagen, texto)
            assert len(contents) == 5

            # Verificar resultados
            assert len(proposals) == 2
            assert proposals[0].image_index == 1
            assert "fotosíntesis" in proposals[0].suggested_alt_text
            assert proposals[1].image_index == 2
            assert "célula vegetal" in proposals[1].suggested_alt_text

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. Integración con analyze_document y Degradación Elegante
# ---------------------------------------------------------------------------

def test_analyze_document_mock_includes_alt_text():
    """En modo mock (?mock=true), las imágenes reciben propuestas determinísticas en la respuesta."""
    pdf_bytes = _create_sample_pdf_with_images([
        {"width": 120, "height": 100, "rect": (50, 150, 200, 280)}
    ])
    doc = document_service.process_pdf(pdf_bytes, filename="mock_alt.pdf")
    response = asyncio.run(analyze_document(doc, mock=True, persist=False))

    assert len(response.alt_text_proposals) == 1
    prop = response.alt_text_proposals[0]
    assert prop.image_index == 1
    assert "[MOCK]" in prop.suggested_alt_text


def test_analyze_document_graceful_degradation_on_vision_error():
    """Si la llamada de visión falla (ej. sin keys o rate limit), el diagnóstico de texto se completa con un warning."""
    pdf_bytes = _create_sample_pdf_with_images([
        {"width": 120, "height": 100, "rect": (50, 150, 200, 280)}
    ])
    doc = document_service.process_pdf(pdf_bytes, filename="fallo_vision.pdf")

    async def _run():
        with patch("app.services.alt_text_service.alt_text_service.generate_proposals", side_effect=NoVisionConnectionError("Sin conexión de visión")):
            with patch("app.services.accessibility_service.llm_service.generate_structured") as mock_text_llm:
                from app.schemas.analysis import AccessibilityDiagnostic
                mock_text_llm.return_value = StructuredResult(
                    parsed=AccessibilityDiagnostic(
                        estimated_score=75,
                        summary="Diagnóstico textual exitoso.",
                        dimensions=[],
                        strengths=[],
                        barriers=[],
                    ),
                    provider="groq",
                    model="gpt-oss-120b",
                    connection_label="Groq",
                    latency_ms=400,
                    usage=None,
                )
                response = await analyze_document(doc, mock=False, persist=False)

                # El análisis no explotó con error 500
                assert response.estimated_score is not None
                # alt_text_proposals quedó vacío por el fallo de visión
                assert response.alt_text_proposals == []
                # Y se agregó una advertencia explicativa
                assert any("No se pudieron generar propuestas de texto alternativo" in w for w in response.warnings)

    asyncio.run(_run())


def test_pdf_endpoint_mock_returns_alt_text_proposals():
    """Prueba de integración HTTP en POST /api/v1/analysis/pdf?mock=true."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    pdf_bytes = _create_sample_pdf_with_images([
        {"width": 120, "height": 100, "rect": (50, 150, 200, 280)}
    ])

    response = client.post(
        "/api/v1/analysis/pdf?mock=true",
        files={"file": ("guia_con_imagenes.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "alt_text_proposals" in data
    assert len(data["alt_text_proposals"]) == 1
    proposal = data["alt_text_proposals"][0]
    assert proposal["image_index"] == 1
    assert proposal["page_number"] == 1
    assert "sector superior" in proposal["location_description"]
    assert "[MOCK]" in proposal["suggested_alt_text"]
    assert "image_bytes" not in str(data)

