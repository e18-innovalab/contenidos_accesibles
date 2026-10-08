import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db import adaptation_repository, analysis_repository
from app.db.database import init_db
from app.main import app
from app.schemas.adaptation import AdaptationAIOutput
from app.schemas.analysis import BarrierReport
from app.services.adaptation_service import FragmentRequiredError, resolve_fragment
from app.services.llm.base import Usage
from app.services.llm_service import StructuredResult

CONSIGNA = "Leé el texto de la página 8, subrayá las ideas principales y respondé las preguntas del final."
LONG_PARAGRAPH = " ".join(
    ["La fotosíntesis es el proceso por el cual las plantas transforman la energía de la luz en energía química."] * 12
)
MATERIAL = f"Actividad de Ciencias Naturales\n{LONG_PARAGRAPH}\n{CONSIGNA}"


@pytest.fixture(autouse=True)
def ensure_db():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def _analyze(client, text: str = MATERIAL) -> dict:
    res = client.post("/api/v1/analysis/sample?mock=true", json={"text": text})
    assert res.status_code == 200
    return res.json()


def _barrier(analysis: dict, issue_prefix: str) -> dict:
    return next(b for b in analysis["barriers"] if b["issue"].startswith(issue_prefix))


def _barrier_report(original_text: str, **overrides) -> BarrierReport:
    data = {
        "id": "bar-1",
        "category": "estructura",
        "severity": "para_revisar",
        "issue": "Párrafo extenso",
        "original_text": original_text,
        "explanation": "x",
        "recommendation": "y",
        "fragment_found": True,
        "source": "rules",
    }
    return BarrierReport(**{**data, **overrides})


# --- Endpoint (modo mock) ------------------------------------------------------


@pytest.mark.parametrize(
    "adaptation_type", ["lenguaje_claro", "consigna_en_pasos", "reorganizar", "mejorar_estructura"]
)
def test_each_type_returns_original_proposal_and_explanation(client, adaptation_type):
    analysis = _analyze(client)
    res = client.post(
        "/api/v1/adaptations?mock=true",
        json={"analysis_id": analysis["analysis_id"], "barrier_id": "bar-1", "adaptation_type": adaptation_type},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["original_text"]
    assert data["proposed_text"]
    assert data["explanation"]
    assert data["preserved_objective"]
    assert data["adaptation_type"] == adaptation_type
    assert data["status"] == "pendiente"
    assert data["barrier_id"] == "bar-1"
    assert data["analysis_id"] == analysis["analysis_id"]
    assert data["expires_at"] == analysis["expires_at"]
    assert data["metadata"]["provider"] == "mock"
    assert data["metadata"]["total_tokens"] == 0


def test_mock_does_not_call_ai(client):
    analysis = _analyze(client)
    with patch(
        "app.services.adaptation_service.llm_service.generate_structured", new_callable=AsyncMock
    ) as mock_gen:
        res = client.post(
            "/api/v1/adaptations?mock=true",
            json={"analysis_id": analysis["analysis_id"], "barrier_id": "bar-1", "adaptation_type": "lenguaje_claro"},
        )
    assert res.status_code == 201
    mock_gen.assert_not_called()


def test_consigna_en_pasos_mock_numbers_each_action(client):
    analysis = _analyze(client, CONSIGNA)
    barrier = _barrier(analysis, "Consigna con múltiples acciones")
    res = client.post(
        "/api/v1/adaptations?mock=true",
        json={
            "analysis_id": analysis["analysis_id"],
            "barrier_id": barrier["id"],
            "adaptation_type": "consigna_en_pasos",
        },
    )
    assert res.status_code == 201
    assert res.json()["proposed_text"].splitlines() == [
        "1. Leé el texto de la página 8.",
        "2. Subrayá las ideas principales.",
        "3. Respondé las preguntas del final.",
    ]


def test_truncated_rule_excerpt_is_expanded_to_full_paragraph(client):
    analysis = _analyze(client)
    barrier = _barrier(analysis, "Párrafo extenso")
    assert barrier["original_text"].endswith("…")
    res = client.post(
        "/api/v1/adaptations?mock=true",
        json={"analysis_id": analysis["analysis_id"], "barrier_id": barrier["id"], "adaptation_type": "reorganizar"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["original_text"] == LONG_PARAGRAPH
    assert data["fragment_source"] == "barrier"


def test_fragment_from_request_overrides_barrier(client):
    analysis = _analyze(client)
    res = client.post(
        "/api/v1/adaptations?mock=true",
        json={
            "analysis_id": analysis["analysis_id"],
            "barrier_id": "bar-1",
            "adaptation_type": "lenguaje_claro",
            "fragment": CONSIGNA,
        },
    )
    assert res.status_code == 201
    assert res.json()["original_text"] == CONSIGNA
    assert res.json()["fragment_source"] == "request"


def test_original_analysis_is_not_modified(client):
    analysis = _analyze(client)
    before = analysis_repository.get(analysis["analysis_id"])
    client.post(
        "/api/v1/adaptations?mock=true",
        json={"analysis_id": analysis["analysis_id"], "barrier_id": "bar-1", "adaptation_type": "lenguaje_claro"},
    )
    after = analysis_repository.get(analysis["analysis_id"])
    assert after["extracted_text"] == before["extracted_text"]
    assert after["diagnostic_json"] == before["diagnostic_json"]


def test_unknown_analysis_returns_404(client):
    res = client.post(
        "/api/v1/adaptations?mock=true",
        json={"analysis_id": str(uuid.uuid4()), "barrier_id": "bar-1", "adaptation_type": "lenguaje_claro"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Diagnóstico no encontrado"


def test_unknown_barrier_returns_404(client):
    analysis = _analyze(client)
    res = client.post(
        "/api/v1/adaptations?mock=true",
        json={"analysis_id": analysis["analysis_id"], "barrier_id": "bar-99", "adaptation_type": "lenguaje_claro"},
    )
    assert res.status_code == 404
    assert "bar-99" in res.json()["detail"]


def test_expired_analysis_returns_404(client):
    analysis = _analyze(client)
    record = analysis_repository.get(analysis["analysis_id"])
    analysis_repository.save(**{**_record_to_save(record), "expires_at": "2020-01-01T00:00:00Z"})
    res = client.post(
        "/api/v1/adaptations?mock=true",
        json={"analysis_id": analysis["analysis_id"], "barrier_id": "bar-1", "adaptation_type": "lenguaje_claro"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "El diagnóstico ha expirado"


def _record_to_save(record: dict) -> dict:
    return {
        "analysis_id": record["id"],
        "source_type": record["source_type"],
        "filename": record["filename"],
        "extracted_text": record["extracted_text"],
        "diagnostic_json": record["diagnostic_json"],
        "expires_at": record["expires_at"],
        "created_at": record["created_at"],
    }


@pytest.mark.parametrize(
    "body",
    [
        {"barrier_id": "bar-1", "adaptation_type": "lenguaje_claro"},  # falta analysis_id
        {"analysis_id": "a", "barrier_id": "barrera-1", "adaptation_type": "lenguaje_claro"},
        {"analysis_id": "a", "barrier_id": "bar-1", "adaptation_type": "resumir"},
        {"analysis_id": "a", "barrier_id": "bar-1", "adaptation_type": "lenguaje_claro", "fragment": "corto"},
    ],
)
def test_invalid_request_returns_422(client, body):
    res = client.post("/api/v1/adaptations?mock=true", json=body)
    assert res.status_code == 422


def test_get_and_list_proposals(client):
    analysis = _analyze(client)
    created = [
        client.post(
            "/api/v1/adaptations?mock=true",
            json={"analysis_id": analysis["analysis_id"], "barrier_id": "bar-1", "adaptation_type": t},
        ).json()
        for t in ("lenguaje_claro", "consigna_en_pasos")
    ]

    res = client.get(f"/api/v1/adaptations/{created[0]['proposal_id']}")
    assert res.status_code == 200
    assert res.json() == created[0]

    res = client.get("/api/v1/adaptations", params={"analysis_id": analysis["analysis_id"]})
    assert res.status_code == 200
    assert [p["proposal_id"] for p in res.json()] == [p["proposal_id"] for p in created]

    assert client.get(f"/api/v1/adaptations/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/v1/adaptations", params={"analysis_id": str(uuid.uuid4())}).status_code == 404


def test_expired_proposals_are_purged():
    proposal_id = f"expired-{uuid.uuid4()}"
    adaptation_repository.save(
        proposal_id=proposal_id,
        analysis_id="x",
        barrier_id="bar-1",
        status="pendiente",
        proposal_json="{}",
        created_at="2020-01-01T00:00:00Z",
        expires_at="2020-01-02T00:00:00Z",
    )
    assert adaptation_repository.delete_expired() >= 1
    assert adaptation_repository.get(proposal_id) is None


# --- Resolución del fragmento ------------------------------------------------------


def test_placeholder_barrier_requires_fragment():
    barrier = _barrier_report("[Documento completo: guia.pdf]")
    with pytest.raises(FragmentRequiredError):
        resolve_fragment(barrier, MATERIAL, "lenguaje_claro")


def test_placeholder_barrier_via_endpoint_returns_422(client):
    analysis = _analyze(client)
    record = analysis_repository.get(analysis["analysis_id"])
    diagnostic = record["diagnostic_json"].replace(
        analysis["barriers"][0]["original_text"].replace('"', '\\"'), "[Evaluación global de legibilidad]", 1
    )
    analysis_repository.save(**{**_record_to_save(record), "diagnostic_json": diagnostic})
    res = client.post(
        "/api/v1/adaptations?mock=true",
        json={"analysis_id": analysis["analysis_id"], "barrier_id": "bar-1", "adaptation_type": "lenguaje_claro"},
    )
    assert res.status_code == 422
    assert "fragment" in res.json()["detail"]


def test_ai_ellipsis_resolves_to_sentence_for_steps():
    barrier = _barrier_report("Leé el texto de la página 8... respondé las preguntas del final.", source="ai")
    fragment, warnings = resolve_fragment(barrier, MATERIAL, "consigna_en_pasos")
    assert fragment == CONSIGNA
    assert warnings == []


def test_exact_fragment_is_used_as_is():
    barrier = _barrier_report(CONSIGNA)
    assert resolve_fragment(barrier, MATERIAL, "lenguaje_claro") == (CONSIGNA, [])


def test_unverified_fragment_adds_warning():
    barrier = _barrier_report("Un fragmento que la IA inventó.", fragment_found=False, source="ai")
    fragment, warnings = resolve_fragment(barrier, MATERIAL, "lenguaje_claro")
    assert fragment == "Un fragmento que la IA inventó."
    assert len(warnings) == 1


# --- Ruta con IA (LLM parcheado, sin llamadas reales) ----------------------------------


def _structured(output: AdaptationAIOutput) -> StructuredResult:
    return StructuredResult(
        parsed=output,
        provider="groq",
        model="test-model",
        connection_label="Test",
        latency_ms=42,
        usage=Usage(prompt_tokens=100, output_tokens=50, thinking_tokens=0, total_tokens=150),
    )


def test_ai_path_sends_barrier_fragment_and_type_instructions(client):
    analysis = _analyze(client, CONSIGNA)
    barrier = _barrier(analysis, "Consigna con múltiples acciones")
    output = AdaptationAIOutput(
        proposed_text="1. Leé el texto.\n2. Subrayá.\n3. Respondé.",
        explanation="Se separaron las acciones.",
        preserved_objective="Comprender el texto de la página 8.",
    )
    with patch(
        "app.services.adaptation_service.llm_service.generate_structured", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = _structured(output)
        res = client.post(
            "/api/v1/adaptations",
            json={
                "analysis_id": analysis["analysis_id"],
                "barrier_id": barrier["id"],
                "adaptation_type": "consigna_en_pasos",
            },
        )

    assert res.status_code == 201
    data = res.json()
    assert data["proposed_text"] == output.proposed_text
    assert data["preserved_objective"] == output.preserved_objective
    assert data["metadata"]["provider"] == "groq"
    assert data["metadata"]["total_tokens"] == 150
    assert data["warnings"] == []

    kwargs = mock_gen.call_args.kwargs
    assert kwargs["schema"] is AdaptationAIOutput
    assert "Conservá el objetivo pedagógico" in kwargs["system_instruction"]
    assert CONSIGNA in kwargs["contents"]
    assert "pasos numerados" in kwargs["contents"]
    assert barrier["issue"] in kwargs["contents"]


def test_ai_path_empty_proposal_returns_502(client):
    analysis = _analyze(client)
    output = AdaptationAIOutput(proposed_text="  ", explanation="x", preserved_objective="y")
    with patch(
        "app.services.adaptation_service.llm_service.generate_structured", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = _structured(output)
        res = client.post(
            "/api/v1/adaptations",
            json={"analysis_id": analysis["analysis_id"], "barrier_id": "bar-1", "adaptation_type": "lenguaje_claro"},
        )
    assert res.status_code == 502


def test_ai_path_unchanged_proposal_adds_warning(client):
    analysis = _analyze(client)
    with patch(
        "app.services.adaptation_service.llm_service.generate_structured", new_callable=AsyncMock
    ) as mock_gen:
        res_original = client.post(
            "/api/v1/adaptations?mock=true",
            json={"analysis_id": analysis["analysis_id"], "barrier_id": "bar-1", "adaptation_type": "lenguaje_claro"},
        ).json()["original_text"]
        mock_gen.return_value = _structured(
            AdaptationAIOutput(proposed_text=res_original, explanation="x", preserved_objective="y")
        )
        res = client.post(
            "/api/v1/adaptations",
            json={"analysis_id": analysis["analysis_id"], "barrier_id": "bar-1", "adaptation_type": "lenguaje_claro"},
        )
    assert res.status_code == 201
    assert any("igual al fragmento original" in w for w in res.json()["warnings"])
