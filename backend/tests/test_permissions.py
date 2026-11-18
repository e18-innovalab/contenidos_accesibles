"""
Roles y permisos de la API (Issue #61): rol desde el claim `role` del token de Clerk, permisos
por rol, dueño de los archivos por usuario y rate limit de IA por usuario autenticado.

Los tokens se firman con una clave RSA de prueba (como en test_teacher_auth.py): ningún test
hace llamadas de red. Todo corre con el almacenamiento local y la IA en modo mock.
"""
import time
from urllib.parse import urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.admin import session
from app.core import rate_limit
from app.core.config import settings
from app.core.permissions import ADMIN, DOCENTE, PERMISSIONS, Caller, role_from_claim
from app.core.rate_limit import limit_ai_usage
from app.core.teacher_auth import require_permission, owner_for_test_web
from app.db import admin_member_repository as members
from app.db import analysis_repository  # noqa: F401 - registra el esquema completo
from app.db.database import get_connection, init_db
from app.main import app
from app.services import storage_service
from app.services.storage_service import LocalStorage

FRONT = "https://frontend.example"
WEB = "https://innovalab-web-pruebas.onrender.com"
PDF = b"%PDF-1.7\n% prueba\n" + b"0" * 2000


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


PRIVATE_PEM, PUBLIC_PEM = _keypair()


def clerk_token(sub="user_ana", role=None) -> str:
    now = int(time.time())
    # 1 h de vigencia: el token no vence aunque la suite tarde (Issue #114)
    claims = {"sub": sub, "azp": FRONT, "iat": now, "nbf": now, "exp": now + 3600, "sid": "sess_1"}
    if role is not None:
        claims["role"] = role
    return jwt.encode(claims, PRIVATE_PEM, algorithm="RS256")


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "BACKEND_CORS_ORIGINS", [FRONT])
    monkeypatch.setattr(settings, "TEST_WEB_URL", None)
    monkeypatch.setattr(settings, "USERS_CLERK_JWT_KEY", None)
    monkeypatch.setattr(settings, "USERS_CLERK_SECRET_KEY", None)
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    init_db()
    session.reset()
    rate_limit.reset()
    local = LocalStorage(str(tmp_path / "storage"), b"secreto-de-prueba")
    storage_service.reset_storage(local)
    yield local
    storage_service.reset_storage()
    rate_limit.reset()


@pytest.fixture
def client(storage):
    return TestClient(app)


@pytest.fixture
def teacher_auth_on(monkeypatch):
    monkeypatch.setattr(settings, "USERS_CLERK_JWT_KEY", PUBLIC_PEM)
    monkeypatch.setattr(settings, "USERS_CLERK_SECRET_KEY", SecretStr("sk_test_prueba"))


def _path(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}"


def _upload(client, headers: dict) -> str:
    """Sube y confirma un PDF; devuelve el file_id."""
    asked = client.post(
        "/api/v1/files/upload-url", headers=headers,
        json={"filename": "material.pdf", "content_type": "application/pdf", "size_bytes": len(PDF)},
    )
    assert asked.status_code == 201, asked.text
    data = asked.json()
    # La URL firmada del almacenamiento no lleva el token del docente
    put = client.put(_path(data["upload"]["url"]), content=PDF, headers=data["upload"]["headers"])
    assert put.status_code == 200, put.text
    file_id = data["file"]["file_id"]
    assert client.post(f"/api/v1/files/{file_id}/complete", headers=headers).status_code == 200
    return file_id


def _owner_of(file_id: str) -> tuple[str, str]:
    with get_connection() as conn:
        row = conn.execute("SELECT user_id, object_key FROM files WHERE id = ?", (file_id,)).fetchone()
    return row["user_id"], row["object_key"]


# ---------------------------------------------------------------------------
# Roles y permisos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("claim,role", [
    ("admin", ADMIN),
    ("docente", DOCENTE),
    (None, DOCENTE),
    ("superusuario", DOCENTE),
    ("", DOCENTE),
    (["admin"], DOCENTE),
])
def test_rol_desde_el_claim_con_docente_por_defecto(claim, role):
    assert role_from_claim(claim) == role


def test_solo_el_admin_configura_la_retencion_y_administra_usuarios():
    docente, admin = Caller("user_ana"), Caller("user_beto", ADMIN)
    for permission in ("settings:retention", "users:manage"):
        assert not docente.can(permission) and admin.can(permission)
    assert PERMISSIONS[DOCENTE] < PERMISSIONS[ADMIN]
    assert all(docente.can(p) for p in ("analysis:create", "adaptations:manage", "files:manage", "files:share", "export:create"))


@pytest.fixture
def retention_client(storage):
    """App mínima con una ruta que exige settings:retention (la usará #64)."""
    mini = FastAPI()

    @mini.get("/retencion")
    def retention(caller: Caller = Depends(require_permission("settings:retention"))):
        return {"user_id": caller.user_id, "role": caller.role}

    return TestClient(mini)


def test_un_docente_recibe_403_y_un_admin_pasa(retention_client, teacher_auth_on):
    denied = retention_client.get("/retencion", headers=bearer(clerk_token(role="docente")))
    assert denied.status_code == 403 and "permiso" in denied.json()["detail"]
    assert retention_client.get("/retencion", headers=bearer(clerk_token())).status_code == 403  # sin claim = docente

    allowed = retention_client.get("/retencion", headers=bearer(clerk_token(sub="user_beto", role="admin")))
    assert allowed.status_code == 200
    assert allowed.json() == {"user_id": "user_beto", "role": ADMIN}


def test_sin_token_es_401_antes_que_403(retention_client, teacher_auth_on):
    assert retention_client.get("/retencion").status_code == 401


def test_la_api_anonima_no_tiene_permisos_de_admin(retention_client):
    # Sin USERS_CLERK_JWT_KEY cualquiera puede llamar: el usuario anónimo es docente
    assert not settings.teacher_auth_enabled
    assert retention_client.get("/retencion").status_code == 403


# ---------------------------------------------------------------------------
# Dueño de los archivos
# ---------------------------------------------------------------------------

def test_los_archivos_quedan_a_nombre_del_docente_y_otro_no_los_ve(client, teacher_auth_on):
    ana, beto = bearer(clerk_token("user_ana")), bearer(clerk_token("user_beto"))
    file_id = _upload(client, ana)

    user_id, key = _owner_of(file_id)
    assert user_id == "user_ana" and key.startswith("users/user_ana/uploads/")
    assert client.get(f"/api/v1/files/{file_id}", headers=ana).status_code == 200

    for method, path in [
        ("get", f"/api/v1/files/{file_id}"),
        ("get", f"/api/v1/files/{file_id}/download-url"),
        ("post", f"/api/v1/files/{file_id}/shares"),
        ("get", f"/api/v1/files/{file_id}/shares"),
        ("post", f"/api/v1/documents/files/{file_id}"),
    ]:
        assert getattr(client, method)(path, headers=beto).status_code == 404, path


def test_files_export_y_documentos_por_file_id_exigen_el_login(client, teacher_auth_on):
    assert client.post(
        "/api/v1/files/upload-url", json={"filename": "a.pdf", "content_type": "application/pdf", "size_bytes": 10},
    ).status_code == 401
    assert client.get("/api/v1/files/cualquiera").status_code == 401
    assert client.post("/api/v1/documents/files/cualquiera").status_code == 401
    assert client.get("/api/v1/export/content?analysis_id=x&format=docx").status_code == 401
    # Las URLs firmadas del almacenamiento local llevan su propia firma, no el token
    assert client.get("/api/v1/files/local/users/x/a.pdf?exp=1&sig=mala&name=a.pdf&type=application/pdf").status_code == 403


def test_sin_login_de_docentes_los_archivos_siguen_siendo_de_anon(client):
    file_id = _upload(client, {})
    assert _owner_of(file_id)[0] == "anon"


def test_la_web_de_pruebas_usa_el_usuario_logueado(client, teacher_auth_on, monkeypatch):
    monkeypatch.setattr(settings, "TEST_WEB_URL", WEB + "/")
    members.add("Silvanam1", "viewer")
    admin_web = {"Origin": WEB, **bearer(session.create_token(session.local_subject(), purpose=session.TEST_WEB))}
    viewer_web = {"Origin": WEB, **bearer(session.create_token(session.github_subject("silvanam1"), purpose=session.TEST_WEB))}

    file_id = _upload(client, admin_web)
    user_id, key = _owner_of(file_id)
    assert user_id == owner_for_test_web("local", settings.ADMIN_USERNAME)
    assert key.startswith(f"users/{user_id}/uploads/")

    # Otra persona de la web de pruebas no ve el archivo
    assert client.get(f"/api/v1/files/{file_id}", headers=viewer_web).status_code == 404
    viewer_file = _upload(client, viewer_web)
    assert _owner_of(viewer_file)[0] == "test-web_github_silvanam1"


def test_el_dueno_de_la_web_de_pruebas_solo_lleva_caracteres_seguros():
    assert owner_for_test_web("local", "admin") == "test-web_local_admin"
    assert owner_for_test_web("local", "ad min/../x") == "test-web_local_ad_min____x"
    assert owner_for_test_web("github", "JAMRdev") == "test-web_github_jamrdev"


@pytest.fixture
def web_roles_client(storage, monkeypatch):
    monkeypatch.setattr(settings, "TEST_WEB_URL", WEB + "/")
    from app.admin.test_web_auth import require_test_web_session
    from starlette.middleware.base import BaseHTTPMiddleware

    mini = FastAPI()
    mini.add_middleware(BaseHTTPMiddleware, dispatch=require_test_web_session)

    @mini.get(f"{settings.API_V1_STR}/rol")
    def role(caller: Caller = Depends(require_permission("analysis:create"))):
        return {"role": caller.role, "can_retention": caller.can("settings:retention")}

    return TestClient(mini)


def test_en_la_web_de_pruebas_el_rol_sale_del_rol_del_panel(web_roles_client):
    members.add("Silvanam1", "viewer")
    for subject, role in [(session.local_subject(), ADMIN), (session.github_subject("silvanam1"), DOCENTE)]:
        headers = {"Origin": WEB, **bearer(session.create_token(subject, purpose=session.TEST_WEB))}
        got = web_roles_client.get(f"{settings.API_V1_STR}/rol", headers=headers)
        assert got.status_code == 200
        assert got.json() == {"role": role, "can_retention": role == ADMIN}


# ---------------------------------------------------------------------------
# Rate limit de IA por usuario
# ---------------------------------------------------------------------------

@pytest.fixture
def ai_client(storage, monkeypatch):
    """Ruta como las de IA: permisos del router primero, después el rate limit."""
    for name in ("AI_RATE_LIMIT_PER_IP_MINUTE", "AI_RATE_LIMIT_PER_IP_DAY", "AI_RATE_LIMIT_GLOBAL_MINUTE", "AI_RATE_LIMIT_GLOBAL_DAY"):
        monkeypatch.setattr(settings, name, 0)
    monkeypatch.setattr(settings, "AI_RATE_LIMIT_PER_USER_MINUTE", 1)
    monkeypatch.setattr(settings, "AI_RATE_LIMIT_PER_USER_DAY", 0)

    mini = FastAPI()

    @mini.post("/ia", dependencies=[Depends(require_permission("analysis:create")), Depends(limit_ai_usage)])
    def ai():
        return {"ok": True}

    return TestClient(mini)


def test_cada_docente_tiene_su_propio_limite(ai_client, teacher_auth_on):
    ana, beto = bearer(clerk_token("user_ana")), bearer(clerk_token("user_beto"))
    assert ai_client.post("/ia", headers=ana).status_code == 200

    limited = ai_client.post("/ia", headers=ana)
    assert limited.status_code == 429
    assert "tu límite" in limited.json()["detail"] and limited.headers["Retry-After"] == "60"

    # Misma IP, otro docente: no comparte el límite por usuario
    assert ai_client.post("/ia", headers=beto).status_code == 200


def test_el_limite_por_usuario_no_aplica_a_la_api_anonima(ai_client):
    assert ai_client.post("/ia").status_code == 200
    assert ai_client.post("/ia").status_code == 200


def test_modo_mock_no_cuenta_para_el_limite_por_usuario(ai_client, teacher_auth_on):
    ana = bearer(clerk_token("user_ana"))
    for _ in range(3):
        assert ai_client.post("/ia?mock=true", headers=ana).status_code == 200
    assert ai_client.post("/ia", headers=ana).status_code == 200


# ---------------------------------------------------------------------------
# Dueño de diagnósticos, propuestas y decisiones
# ---------------------------------------------------------------------------

MATERIAL = (
    "Actividad de Ciencias Naturales\n"
    + " ".join(["La fotosíntesis es el proceso por el cual las plantas transforman la energía de la luz en energía química."] * 12)
    + "\nLeé el texto de la página 8, subrayá las ideas principales y respondé las preguntas del final."
)


def _owner_column(table: str, row_id: str, column: str = "id") -> list[str]:
    with get_connection() as conn:
        return [r["user_id"] for r in conn.execute(f"SELECT user_id FROM {table} WHERE {column} = ?", (row_id,))]


def _analysis_with_proposal(client, headers: dict) -> tuple[str, str]:
    analysis = client.post("/api/v1/analysis/sample?mock=true", json={"text": MATERIAL}, headers=headers)
    assert analysis.status_code == 200, analysis.text
    analysis_id = analysis.json()["analysis_id"]
    proposal = client.post(
        "/api/v1/adaptations?mock=true", headers=headers,
        json={"analysis_id": analysis_id, "barrier_id": "bar-1", "adaptation_type": "lenguaje_claro"},
    )
    assert proposal.status_code == 201, proposal.text
    return analysis_id, proposal.json()["proposal_id"]


def test_diagnosticos_propuestas_y_decisiones_quedan_a_nombre_del_docente(client, teacher_auth_on):
    ana = bearer(clerk_token("user_ana"))
    analysis_id, proposal_id = _analysis_with_proposal(client, ana)
    decided = client.post(f"/api/v1/adaptations/{proposal_id}/decision", json={"decision": "aceptada"}, headers=ana)
    assert decided.status_code == 200, decided.text

    assert _owner_column("analyses", analysis_id) == ["user_ana"]
    assert _owner_column("adaptation_proposals", proposal_id) == ["user_ana"]
    assert _owner_column("adaptation_decisions", proposal_id, "proposal_id") == ["user_ana"]


def test_otro_docente_no_ve_ni_modifica_lo_ajeno(client, teacher_auth_on):
    ana, beto = bearer(clerk_token("user_ana")), bearer(clerk_token("user_beto"))
    analysis_id, proposal_id = _analysis_with_proposal(client, ana)

    for method, path, body in [
        ("get", f"/api/v1/analysis/{analysis_id}", None),
        ("post", "/api/v1/adaptations?mock=true", {"analysis_id": analysis_id, "barrier_id": "bar-2", "adaptation_type": "lenguaje_claro"}),
        ("get", f"/api/v1/adaptations?analysis_id={analysis_id}", None),
        ("get", f"/api/v1/adaptations/decisions?analysis_id={analysis_id}", None),
        ("get", f"/api/v1/adaptations/final-version?analysis_id={analysis_id}", None),
        ("get", f"/api/v1/adaptations/report?analysis_id={analysis_id}", None),
        ("get", f"/api/v1/adaptations/{proposal_id}", None),
        ("post", f"/api/v1/adaptations/{proposal_id}/decision", {"decision": "descartada"}),
        ("post", f"/api/v1/adaptations/{proposal_id}/undo", None),
        ("get", f"/api/v1/export/content?analysis_id={analysis_id}&format=txt", None),
        ("get", f"/api/v1/export/report?analysis_id={analysis_id}&format=txt", None),
    ]:
        kwargs = {"headers": beto} | ({"json": body} if body is not None else {})
        assert getattr(client, method)(path, **kwargs).status_code == 404, path

    # Lo de Ana sigue intacto y accesible para ella
    proposal = client.get(f"/api/v1/adaptations/{proposal_id}", headers=ana)
    assert proposal.status_code == 200 and proposal.json()["status"] == "pendiente"
    assert client.get(f"/api/v1/analysis/{analysis_id}", headers=ana).status_code == 200
    assert client.get(f"/api/v1/export/content?analysis_id={analysis_id}&format=txt", headers=ana).status_code == 200


def test_sin_login_de_docentes_todo_sigue_siendo_de_anon(client):
    analysis_id, proposal_id = _analysis_with_proposal(client, {})
    assert _owner_column("analyses", analysis_id) == ["anon"]
    assert _owner_column("adaptation_proposals", proposal_id) == ["anon"]
    assert client.get(f"/api/v1/adaptations/{proposal_id}").status_code == 200


def test_una_base_local_anterior_recibe_la_columna_user_id(tmp_path, monkeypatch):
    import sqlite3

    path = tmp_path / "vieja.db"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE analyses (id TEXT PRIMARY KEY, source_type TEXT NOT NULL, filename TEXT, extracted_text TEXT NOT NULL,"
        " diagnostic_json TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);"
        "CREATE TABLE adaptation_proposals (id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL, barrier_id TEXT NOT NULL,"
        " status TEXT NOT NULL DEFAULT 'pendiente', proposal_json TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL);"
        "INSERT INTO analyses VALUES ('a1', 'text', NULL, 't', '{}', 'x', 'y');"
    )
    old.commit()
    old.close()

    monkeypatch.setattr(settings, "DATABASE_PATH", str(path))
    init_db()
    assert _owner_column("analyses", "a1") == ["anon"]
    with get_connection() as conn:
        for table in ("adaptation_proposals", "adaptation_decisions"):
            assert "user_id" in {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
