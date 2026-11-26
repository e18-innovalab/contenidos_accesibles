"""Tests del endpoint de métricas personales del usuario (/api/v1/metrics)."""

from fastapi.testclient import TestClient

from app.core.permissions import ANONYMOUS_OWNER
from app.db import user_activity_repository as user_activity
from app.db.database import init_db
from app.main import app


def test_metrics_endpoint_empty_user():
    init_db()
    client = TestClient(app)
    res = client.get("/api/v1/metrics?range=24h")
    assert res.status_code == 200
    data = res.json()
    assert data["range"] == "24h"
    assert len(data["buckets"]) == len(data["tokens"])
    assert "models" not in data


def test_metrics_endpoint_never_exposes_provider_or_model():
    init_db()
    user_activity.record("analysis", ANONYMOUS_OWNER, fmt="pdf", score=74, barriers=4)
    user_activity.record(
        "ai_call",
        ANONYMOUS_OWNER,
        detail="ok",
        provider="groq",
        model="openai/gpt-oss-120b",
        latency_ms=420,
        tokens=1250,
    )

    client = TestClient(app)
    res = client.get("/api/v1/metrics?range=7d")
    assert res.status_code == 200
    raw = res.text
    assert "groq" not in raw
    assert "gpt-oss-120b" not in raw

    data = res.json()
    assert data["in_range"]["analyses"] >= 1
    assert data["in_range"]["tokens"] >= 1250
    assert data["in_range"]["ai_calls"] >= 1
    assert "models" not in data
    for ev in data["recent"]:
        assert "provider" not in ev
        assert "model" not in ev
