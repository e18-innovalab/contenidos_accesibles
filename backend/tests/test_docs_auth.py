import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, settings
from app.core.docs import setup_protected_docs

OPENAPI_URL = "/api/v1/openapi.json"
DOC_PATHS = ["/docs", "/redoc", OPENAPI_URL]
USER, PASSWORD = "docs", "clave-de-prueba"


@pytest.fixture
def protected_client(monkeypatch):
    """App como en production: docs de FastAPI apagados y re-registrados con auth."""
    monkeypatch.setattr(settings, "DOCS_USERNAME", USER)
    monkeypatch.setattr(settings, "DOCS_PASSWORD", SecretStr(PASSWORD))
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    setup_protected_docs(app, OPENAPI_URL)
    return TestClient(app)


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_sin_credenciales_devuelve_401(protected_client, path):
    r = protected_client.get(path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == 'Basic realm="docs"'


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_con_credenciales_invalidas_devuelve_401(protected_client, path):
    assert protected_client.get(path, auth=(USER, "incorrecta")).status_code == 401
    assert protected_client.get(path, auth=("otro", PASSWORD)).status_code == 401


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_con_credenciales_validas_devuelve_200(protected_client, path):
    assert protected_client.get(path, auth=(USER, PASSWORD)).status_code == 200


def test_swagger_apunta_al_openapi_protegido(protected_client):
    html = protected_client.get("/docs", auth=(USER, PASSWORD)).text
    assert OPENAPI_URL in html


def test_openapi_no_expone_rutas_de_docs(protected_client):
    schema = protected_client.get(OPENAPI_URL, auth=(USER, PASSWORD)).json()
    assert "/api/v1/health" in schema["paths"]
    assert not {"/docs", "/redoc", OPENAPI_URL} & set(schema["paths"])


def test_api_sigue_publica(protected_client):
    assert protected_client.get("/api/v1/health").status_code == 200


def _settings(**overrides) -> Settings:
    base = {"ADMIN_PASSWORD": "admin", "DB_ENCRYPTION_KEY": "k"}
    return Settings(_env_file=None, **(base | overrides))


@pytest.mark.parametrize("env", ["staging", "production"])
def test_sin_docs_password_fuera_de_development_no_arranca(monkeypatch, env):
    monkeypatch.delenv("DOCS_PASSWORD", raising=False)
    with pytest.raises(ValidationError, match="DOCS_PASSWORD"):
        _settings(ENVIRONMENT=env)
    with pytest.raises(ValidationError, match="DOCS_PASSWORD"):
        _settings(ENVIRONMENT=env, DOCS_PASSWORD="")


def test_development_no_exige_docs_password(monkeypatch):
    monkeypatch.delenv("DOCS_PASSWORD", raising=False)
    s = _settings(ENVIRONMENT="development")
    assert s.docs_protected is False


def test_production_con_docs_password_protege():
    s = _settings(ENVIRONMENT="production", DOCS_PASSWORD="x")
    assert s.docs_protected is True
