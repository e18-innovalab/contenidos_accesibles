import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.admin.router import router as admin_router
from app.core.config import settings
from app.services import key_rotation_service

USER, PASSWORD = "admin", "clave-de-prueba"
WEB_URL = "https://innovalab-web-pruebas.onrender.com/"


# ---------------------------------------------------------------------------
# CORS: el origen de TEST_WEB_URL se suma a BACKEND_CORS_ORIGINS
# ---------------------------------------------------------------------------

def test_cors_origins_sin_test_web_url(monkeypatch):
    monkeypatch.setattr(settings, "BACKEND_CORS_ORIGINS", ["http://localhost:3000"])
    monkeypatch.setattr(settings, "TEST_WEB_URL", None)
    assert settings.cors_origins == ["http://localhost:3000"]


def test_cors_origins_suma_solo_el_origen_de_test_web_url(monkeypatch):
    monkeypatch.setattr(settings, "BACKEND_CORS_ORIGINS", ["http://localhost:3000"])
    monkeypatch.setattr(settings, "TEST_WEB_URL", WEB_URL + "index.html?x=1")
    assert settings.cors_origins == ["http://localhost:3000", "https://innovalab-web-pruebas.onrender.com"]


def test_cors_origins_no_duplica_ni_acepta_urls_sin_esquema(monkeypatch):
    monkeypatch.setattr(settings, "BACKEND_CORS_ORIGINS", ["https://innovalab-web-pruebas.onrender.com"])
    monkeypatch.setattr(settings, "TEST_WEB_URL", WEB_URL)
    assert settings.cors_origins == ["https://innovalab-web-pruebas.onrender.com"]

    monkeypatch.setattr(settings, "TEST_WEB_URL", "innovalab-web-pruebas.onrender.com")
    assert settings.cors_origins == ["https://innovalab-web-pruebas.onrender.com"]


def test_preflight_cors_desde_la_web_de_pruebas(monkeypatch):
    """El middleware real acepta el origen de TEST_WEB_URL en un preflight."""
    from fastapi.middleware.cors import CORSMiddleware

    monkeypatch.setattr(settings, "TEST_WEB_URL", WEB_URL)
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    @app.post("/api/v1/analysis/sample")
    def sample():
        return {}

    r = TestClient(app).options(
        "/api/v1/analysis/sample",
        headers={
            "Origin": "https://innovalab-web-pruebas.onrender.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "https://innovalab-web-pruebas.onrender.com"


# ---------------------------------------------------------------------------
# Enlace desde /admin
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_client(monkeypatch):
    """Solo el router de /admin, sin DB: el dashboard recibe una lista de conexiones vacía."""
    monkeypatch.setattr(settings, "ADMIN_USERNAME", USER)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", SecretStr(PASSWORD))
    monkeypatch.setattr(key_rotation_service, "list_status_for_dashboard", lambda: [])
    app = FastAPI()
    app.include_router(admin_router, prefix="/admin")
    return TestClient(app, base_url="https://backend.example.com")


def test_admin_muestra_enlace_a_la_web_apuntando_a_este_backend(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "TEST_WEB_URL", WEB_URL)
    r = admin_client.get("/admin/", auth=(USER, PASSWORD))
    assert r.status_code == 200
    assert f'href="{WEB_URL}?api=https%3A%2F%2Fbackend.example.com"' in r.text


def test_admin_sin_test_web_url_no_muestra_enlace(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "TEST_WEB_URL", None)
    r = admin_client.get("/admin/", auth=(USER, PASSWORD))
    assert r.status_code == 200
    assert "Web de pruebas" not in r.text
