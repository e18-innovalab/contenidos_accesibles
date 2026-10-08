import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import adaptation_repository
from app.db.database import init_db
from app.main import app

MATERIAL = "Leé el texto de la página 8, subrayá las ideas principales y respondé las preguntas del final."


@pytest.fixture(autouse=True)
def ensure_db():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def proposal(client) -> dict:
    analysis = client.post("/api/v1/analysis/sample?mock=true", json={"text": MATERIAL}).json()
    res = client.post(
        "/api/v1/adaptations?mock=true",
        json={"analysis_id": analysis["analysis_id"], "barrier_id": "bar-1", "adaptation_type": "consigna_en_pasos"},
    )
    assert res.status_code == 201
    return res.json()


def _decide(client, proposal_id: str, **body):
    return client.post(f"/api/v1/adaptations/{proposal_id}/decision", json=body)


def _log(client, analysis_id: str) -> list[dict]:
    res = client.get("/api/v1/adaptations/decisions", params={"analysis_id": analysis_id})
    assert res.status_code == 200
    return res.json()


def test_new_proposal_is_pending_without_final_text(proposal):
    assert proposal["status"] == "pendiente"
    assert proposal["final_text"] is None
    assert proposal["edited_text"] is None
    assert proposal["decided_at"] is None


def test_accept_sets_final_text_to_proposal(client, proposal):
    res = _decide(client, proposal["proposal_id"], decision="aceptada")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "aceptada"
    assert data["final_text"] == proposal["proposed_text"]
    assert data["decided_at"] is not None
    assert data["original_text"] == proposal["original_text"]


def test_edit_stores_teacher_text(client, proposal):
    res = _decide(client, proposal["proposal_id"], decision="editada", edited_text="  1. Leé.\n2. Respondé.  ")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "editada"
    assert data["edited_text"] == "1. Leé.\n2. Respondé."
    assert data["final_text"] == "1. Leé.\n2. Respondé."
    assert data["proposed_text"] == proposal["proposed_text"]
    assert data["original_text"] == proposal["original_text"]


def test_discard_leaves_no_final_text(client, proposal):
    res = _decide(client, proposal["proposal_id"], decision="descartada")
    assert res.status_code == 200
    assert res.json()["status"] == "descartada"
    assert res.json()["final_text"] is None


def test_decision_is_persisted(client, proposal):
    _decide(client, proposal["proposal_id"], decision="aceptada")
    stored = client.get(f"/api/v1/adaptations/{proposal['proposal_id']}").json()
    assert stored["status"] == "aceptada"
    assert adaptation_repository.get(proposal["proposal_id"])["status"] == "aceptada"


@pytest.mark.parametrize(
    "body",
    [
        {"decision": "editada"},
        {"decision": "editada", "edited_text": "   "},
        {"decision": "aceptada", "edited_text": "texto"},
        {"decision": "pendiente"},
        {"decision": "aprobada"},
    ],
)
def test_invalid_decision_returns_422(client, proposal, body):
    assert _decide(client, proposal["proposal_id"], **body).status_code == 422


def test_cannot_decide_twice_without_undo(client, proposal):
    assert _decide(client, proposal["proposal_id"], decision="aceptada").status_code == 200
    res = _decide(client, proposal["proposal_id"], decision="descartada")
    assert res.status_code == 409
    assert "deshacé" in res.json()["detail"]


def test_undo_reverts_to_pending_and_allows_new_decision(client, proposal):
    pid = proposal["proposal_id"]
    _decide(client, pid, decision="editada", edited_text="Texto del docente.")

    res = client.post(f"/api/v1/adaptations/{pid}/undo")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "pendiente"
    assert data["edited_text"] is None
    assert data["final_text"] is None
    assert data["decided_at"] is None
    assert data["original_text"] == proposal["original_text"]
    assert data["proposed_text"] == proposal["proposed_text"]

    assert _decide(client, pid, decision="descartada").status_code == 200


def test_undo_pending_returns_409(client, proposal):
    res = client.post(f"/api/v1/adaptations/{proposal['proposal_id']}/undo")
    assert res.status_code == 409


def test_unknown_proposal_returns_404(client):
    pid = str(uuid.uuid4())
    assert _decide(client, pid, decision="aceptada").status_code == 404
    assert client.post(f"/api/v1/adaptations/{pid}/undo").status_code == 404


def test_expired_proposal_cannot_be_decided(client, proposal):
    record = adaptation_repository.get(proposal["proposal_id"])
    adaptation_repository.save(
        proposal_id=record["id"],
        analysis_id=record["analysis_id"],
        barrier_id=record["barrier_id"],
        status=record["status"],
        proposal_json=record["proposal_json"],
        created_at=record["created_at"],
        expires_at="2020-01-01T00:00:00Z",
    )
    assert _decide(client, proposal["proposal_id"], decision="aceptada").status_code == 404


def test_decision_log_records_each_change_in_order(client, proposal):
    pid = proposal["proposal_id"]
    _decide(client, pid, decision="aceptada")
    client.post(f"/api/v1/adaptations/{pid}/undo")
    _decide(client, pid, decision="editada", edited_text="Versión del docente.")

    log = _log(client, proposal["analysis_id"])
    assert [(e["action"], e["from_status"], e["to_status"]) for e in log] == [
        ("decision", "pendiente", "aceptada"),
        ("deshacer", "aceptada", "pendiente"),
        ("decision", "pendiente", "editada"),
    ]
    assert log[2]["edited_text"] == "Versión del docente."
    assert log[0]["edited_text"] is None
    assert all(e["proposal_id"] == pid and e["barrier_id"] == "bar-1" for e in log)
    assert log[0]["adaptation_type"] == "consigna_en_pasos"


def test_rejected_decision_is_not_logged(client, proposal):
    _decide(client, proposal["proposal_id"], decision="aceptada")
    _decide(client, proposal["proposal_id"], decision="descartada")  # 409
    assert len(_log(client, proposal["analysis_id"])) == 1


def test_decision_log_unknown_analysis_returns_404(client):
    res = client.get("/api/v1/adaptations/decisions", params={"analysis_id": str(uuid.uuid4())})
    assert res.status_code == 404


def test_stale_transition_is_rejected():
    """Si otra request decidió en el medio, la transición no se aplica ni se registra."""
    pid = f"race-{uuid.uuid4()}"
    adaptation_repository.save(
        proposal_id=pid,
        analysis_id="a",
        barrier_id="bar-1",
        status="aceptada",
        proposal_json="{}",
        created_at="2030-01-01T00:00:00Z",
        expires_at="2030-01-02T00:00:00Z",
    )
    applied = adaptation_repository.transition(
        pid,
        from_status="pendiente",
        to_status="descartada",
        proposal_json="{}",
        log_entry={
            "proposal_id": pid, "analysis_id": "a", "barrier_id": "bar-1",
            "adaptation_type": "lenguaje_claro", "action": "decision",
            "from_status": "pendiente", "to_status": "descartada", "edited_text": None,
            "created_at": "2030-01-01T00:00:00Z", "expires_at": "2030-01-02T00:00:00Z",
        },
    )
    assert applied is False
    assert adaptation_repository.get(pid)["status"] == "aceptada"
    assert adaptation_repository.list_decisions("a") == []
