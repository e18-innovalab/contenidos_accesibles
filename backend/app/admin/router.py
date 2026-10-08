import json
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.security import get_current_admin, verify_same_origin
from app.db import api_key_repository as repo
from app.services import key_rotation_service
from app.services.llm.providers import PRESETS, presets_as_dicts

router = APIRouter(include_in_schema=False)

_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

# Diagramas de arquitectura generados con Archify (fuentes en docs/diagramas/).
# El slug de la URL solo se busca en este diccionario: nunca se arma una ruta
# de archivo con input del usuario.
_diagrams_dir = Path(__file__).parent / "diagrams"
DIAGRAMS: dict[str, tuple[str, str]] = {
    "arquitectura": ("Arquitectura en runtime", "Front, Railway, FastAPI, servicios, proveedores de IA y SQLite."),
    "secuencia-analisis-pdf": ("Secuencia de POST /api/v1/analysis/pdf", "Extracción, reglas, IA con rotación y respuesta."),
    "rotacion-keys": ("Rotación de conexiones de IA", "Cómo se elige, usa y excluye cada conexión."),
    "ciclo-vida-conexion": ("Ciclo de vida de una conexión", "Estados standby, active, near-limit, exhausted y disabled."),
}


def _parse_extra_params(raw: str) -> dict:
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Parámetros extra: JSON inválido ({e.msg}).")
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="Parámetros extra: debe ser un objeto JSON {...}.")
    return value


def _clean_provider(provider: str) -> str:
    provider = provider.strip().lower()
    if not provider:
        raise HTTPException(status_code=400, detail="El proveedor es obligatorio.")
    return provider


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, admin: str = Depends(get_current_admin)):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "keys": key_rotation_service.list_status_for_dashboard(),
            "presets": PRESETS,
            "presets_json": presets_as_dicts(),
            "test_web_url": _test_web_link(request),
        },
    )


def _test_web_link(request: Request) -> str | None:
    """Enlace a la web de pruebas apuntando a este mismo backend (?api=<origen>)."""
    if not settings.TEST_WEB_URL:
        return None
    api_origin = str(request.base_url).rstrip("/")
    separator = "&" if "?" in settings.TEST_WEB_URL else "?"
    return f"{settings.TEST_WEB_URL.strip()}{separator}{urlencode({'api': api_origin})}"


@router.post("/keys")
def create_key(
    label: str = Form(...),
    key_value: str = Form(...),
    provider: str = Form(...),
    model: str = Form(...),
    base_url: str = Form(""),
    priority: int = Form(100),
    extra_params: str = Form(""),
    rpm_threshold: int | None = Form(None),
    tpm_threshold: int | None = Form(None),
    rpd_threshold: int | None = Form(None),
    tpd_threshold: int | None = Form(None),
    admin: str = Depends(get_current_admin),
    _origin_ok: None = Depends(verify_same_origin),
):
    repo.create(
        label=label,
        raw_key=key_value,
        provider=_clean_provider(provider),
        base_url=base_url.strip() or None,
        model=model.strip(),
        priority=priority,
        extra_params=_parse_extra_params(extra_params),
        rpm_threshold=rpm_threshold,
        tpm_threshold=tpm_threshold,
        rpd_threshold=rpd_threshold,
        tpd_threshold=tpd_threshold,
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/keys/{key_id}/update")
def update_key(
    key_id: int,
    label: str = Form(...),
    provider: str = Form(...),
    model: str = Form(...),
    base_url: str = Form(""),
    priority: int = Form(100),
    extra_params: str = Form(""),
    key_value: str = Form(""),
    rpm_threshold: int | None = Form(None),
    tpm_threshold: int | None = Form(None),
    rpd_threshold: int | None = Form(None),
    tpd_threshold: int | None = Form(None),
    enabled: bool = Form(False),
    admin: str = Depends(get_current_admin),
    _origin_ok: None = Depends(verify_same_origin),
):
    repo.update(
        key_id,
        label=label,
        provider=_clean_provider(provider),
        base_url=base_url.strip() or None,
        model=model.strip(),
        priority=priority,
        extra_params=_parse_extra_params(extra_params),
        rpm_threshold=rpm_threshold,
        tpm_threshold=tpm_threshold,
        rpd_threshold=rpd_threshold,
        tpd_threshold=tpd_threshold,
        enabled=enabled,
        raw_key=key_value or None,
    )
    return RedirectResponse("/admin", status_code=303)


@router.post("/keys/{key_id}/delete")
def delete_key(
    key_id: int,
    admin: str = Depends(get_current_admin),
    _origin_ok: None = Depends(verify_same_origin),
):
    repo.delete(key_id)
    return RedirectResponse("/admin", status_code=303)


@router.get("/diagramas", response_class=HTMLResponse)
def diagrams_index(request: Request, admin: str = Depends(get_current_admin)):
    return templates.TemplateResponse(request, "diagrams.html", {"diagrams": DIAGRAMS})


@router.get("/diagramas/{slug}")
def diagram(slug: str, admin: str = Depends(get_current_admin)):
    if slug not in DIAGRAMS:
        raise HTTPException(status_code=404, detail="Diagrama no encontrado.")
    return FileResponse(_diagrams_dir / f"{slug}.html", media_type="text/html")
