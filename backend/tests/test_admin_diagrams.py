import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.admin.router import DIAGRAMS
from app.admin.router import router as admin_router
from app.core.config import settings

USER, PASSWORD = "admin", "clave-de-prueba"
PATHS = ["/admin/diagramas", "/admin/diagramas/arquitectura"]


@pytest.fixture
def client(monkeypatch):
    """Solo el router de /admin: las rutas de diagramas no tocan la DB ni la IA."""
    monkeypatch.setattr(settings, "ADMIN_USERNAME", USER)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", SecretStr(PASSWORD))
    app = FastAPI()
    app.include_router(admin_router, prefix="/admin")
    return TestClient(app)


@pytest.mark.parametrize("path", PATHS)
def test_diagramas_sin_credenciales_devuelve_401(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", PATHS)
def test_diagramas_con_credenciales_invalidas_devuelve_401(client, path):
    assert client.get(path, auth=(USER, "incorrecta")).status_code == 401
    assert client.get(path, auth=("otro", PASSWORD)).status_code == 401


def test_indice_lista_todos_los_diagramas(client):
    r = client.get("/admin/diagramas", auth=(USER, PASSWORD))
    assert r.status_code == 200
    for slug in DIAGRAMS:
        assert f"/admin/diagramas/{slug}" in r.text


@pytest.mark.parametrize("slug", DIAGRAMS)
def test_cada_diagrama_devuelve_html(client, slug):
    r = client.get(f"/admin/diagramas/{slug}", auth=(USER, PASSWORD))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<svg" in r.text


@pytest.mark.parametrize("slug", ["no-existe", "..%2Fdashboard", "..%2F..%2F.env"])
def test_slug_desconocido_devuelve_404(client, slug):
    assert client.get(f"/admin/diagramas/{slug}", auth=(USER, PASSWORD)).status_code == 404
