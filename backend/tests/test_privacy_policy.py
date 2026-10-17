import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.document_service import MAX_ANALYSIS_WORDS


@pytest.fixture
def client():
    return TestClient(app)


def test_get_privacy_policy_success(client):
    response = client.get("/api/v1/privacy/policy")
    assert response.status_code == 200

    data = response.json()

    # Validación de procesamiento con IA externa
    assert "external_ai_processing" in data
    ai_policy = data["external_ai_processing"]
    assert ai_policy["enabled"] is True
    assert ai_policy["provider"] == settings.AI_PROVIDER
    assert ai_policy["model"] == settings.AI_MODEL
    assert ai_policy["max_words_per_analysis"] == MAX_ANALYSIS_WORDS
    assert "texto extraído" in ai_policy["data_sent_description"]
    assert "expresiones regulares" in ai_policy["pii_protection"]

    # Validación de almacenamiento y retención
    assert "storage_policy" in data
    storage = data["storage_policy"]
    assert "disco local" in storage["local_disk_storage"].lower()
    assert storage["storage_backend"] == settings.STORAGE_BACKEND
    assert storage["retention_period_hours"] == settings.FILE_TTL_HOURS
    assert storage["auto_deletion_enabled"] is True

    # Carpetas de almacenamiento segregadas
    assert "object_folders" in storage
    folders = storage["object_folders"]
    assert "uploads" in folders
    assert "results" in folders
    assert "adapted" in folders

    # Derechos docentes
    assert "user_rights" in data
    assert str(settings.FILE_TTL_HOURS) in data["user_rights"]


def test_privacy_policy_public_access(client, monkeypatch):
    # Simula configuración activa de auth para docentes (Issue #60)
    monkeypatch.setattr(settings, "USERS_CLERK_JWT_KEY", "test-key-configured")

    # Debe seguir siendo accesible públicamente sin token
    response = client.get("/api/v1/privacy/policy")
    assert response.status_code == 200
