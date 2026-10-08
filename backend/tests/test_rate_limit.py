import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.config import settings
from app.db.database import init_db
from app.main import app
from app.services.llm_service import llm_service

PING = "/api/v1/ai/test-connection"
MATERIAL = "Leé el texto de la página 8, subrayá las ideas principales y respondé las preguntas del final."


@pytest.fixture(autouse=True)
def isolated_limiter(monkeypatch):
    init_db()
    rate_limit.reset()
    # Reloj controlado y sin llamadas reales a la IA
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(rate_limit, "_now", lambda: clock["now"])

    async def fake_ping():
        return {"status": "ok"}

    monkeypatch.setattr(llm_service, "ping_connection", fake_ping)
    yield clock
    rate_limit.reset()


@pytest.fixture
def client():
    return TestClient(app)


def _limits(monkeypatch, per_ip_minute=0, per_ip_day=0, global_minute=0, global_day=0):
    monkeypatch.setattr(settings, "AI_RATE_LIMIT_PER_IP_MINUTE", per_ip_minute)
    monkeypatch.setattr(settings, "AI_RATE_LIMIT_PER_IP_DAY", per_ip_day)
    monkeypatch.setattr(settings, "AI_RATE_LIMIT_GLOBAL_MINUTE", global_minute)
    monkeypatch.setattr(settings, "AI_RATE_LIMIT_GLOBAL_DAY", global_day)


def test_per_ip_minute_limit_returns_429_with_retry_after(client, monkeypatch):
    _limits(monkeypatch, per_ip_minute=2)
    assert client.post(PING).status_code == 200
    assert client.post(PING).status_code == 200

    res = client.post(PING)
    assert res.status_code == 429
    assert res.headers["Retry-After"] == "60"
    assert "esta IP" in res.json()["detail"]


def test_minute_window_slides(client, monkeypatch, isolated_limiter):
    _limits(monkeypatch, per_ip_minute=1)
    assert client.post(PING).status_code == 200
    isolated_limiter["now"] += 30
    res = client.post(PING)
    assert res.status_code == 429
    assert res.headers["Retry-After"] == "30"

    isolated_limiter["now"] += 31
    assert client.post(PING).status_code == 200


def test_per_ip_day_limit(client, monkeypatch, isolated_limiter):
    _limits(monkeypatch, per_ip_day=2)
    assert client.post(PING).status_code == 200
    isolated_limiter["now"] += 3600
    assert client.post(PING).status_code == 200
    isolated_limiter["now"] += 3600

    res = client.post(PING)
    assert res.status_code == 429
    assert int(res.headers["Retry-After"]) == 24 * 3600 - 2 * 3600

    isolated_limiter["now"] += 22 * 3600
    assert client.post(PING).status_code == 200


def test_global_limit_applies_even_without_per_ip_limit(client, monkeypatch):
    _limits(monkeypatch, global_minute=1)
    assert client.post(PING).status_code == 200

    res = client.post(PING)
    assert res.status_code == 429
    assert "límite de uso de IA" in res.json()["detail"]


def test_rejected_calls_do_not_consume_quota(client, monkeypatch, isolated_limiter):
    _limits(monkeypatch, per_ip_minute=1)
    assert client.post(PING).status_code == 200
    for _ in range(5):
        assert client.post(PING).status_code == 429

    isolated_limiter["now"] += 61
    assert client.post(PING).status_code == 200


def test_mock_calls_are_not_limited(client, monkeypatch):
    _limits(monkeypatch, per_ip_minute=1, global_minute=1)
    for _ in range(3):
        analysis = client.post("/api/v1/analysis/sample?mock=true", json={"text": MATERIAL})
        assert analysis.status_code == 200
        res = client.post(
            "/api/v1/adaptations?mock=true",
            json={
                "analysis_id": analysis.json()["analysis_id"],
                "barrier_id": "bar-1",
                "adaptation_type": "consigna_en_pasos",
            },
        )
        assert res.status_code == 201


def test_ai_endpoints_share_the_limit(client, monkeypatch):
    _limits(monkeypatch, per_ip_minute=1)
    assert client.post(PING).status_code == 200
    assert client.post("/api/v1/analysis/sample", json={"text": MATERIAL}).status_code == 429
    assert client.post("/api/v1/ai/test-gemini").status_code == 429


def test_zero_disables_limits(client, monkeypatch):
    _limits(monkeypatch)
    for _ in range(10):
        assert client.post(PING).status_code == 200
