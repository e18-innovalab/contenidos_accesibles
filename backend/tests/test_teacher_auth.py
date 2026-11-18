"""
Login de docentes con Clerk (Issue #60): /analysis y /adaptations exigen el token de sesión
solo si USERS_CLERK_JWT_KEY está configurada.

Los tokens se firman con una clave RSA de prueba (como en test_admin_auth.py): ningún test
hace llamadas de red.
"""
import time

import jwt
import pytest
from clerk_backend_api.security.types import TokenVerificationError, TokenVerificationErrorReason
from clerk_backend_api.security.verifytoken import verify_token
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.middleware.base import BaseHTTPMiddleware

from app.admin import session, test_web_auth
from app.api.v1.router import api_router
from app.core import rate_limit, teacher_auth
from app.core.config import settings
from app.db.database import init_db

FRONT = "https://frontend.example"
WEB = "https://innovalab-web-pruebas.onrender.com"
SAMPLE = {"text": "Leé el texto, subrayá las ideas principales y respondé las preguntas del final."}
ANALYSIS = "/api/v1/analysis/sample?mock=true"
ADAPTATIONS = "/api/v1/adaptations?analysis_id=inexistente"


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, public


PRIVATE_PEM, PUBLIC_PEM = _keypair()
OTHER_PRIVATE_PEM, _ = _keypair()


def clerk_token(sub="user_docente", azp=FRONT, exp_in=3600, key=PRIVATE_PEM) -> str:
    # 1 h de vigencia: el token no vence aunque la suite tarde (Issues #114 y #115)
    now = int(time.time())
    claims = {"sub": sub, "azp": azp, "iat": now, "nbf": now, "exp": now + exp_in, "sid": "sess_1"}
    return jwt.encode(claims, key, algorithm="RS256")


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "BACKEND_CORS_ORIGINS", [FRONT])
    monkeypatch.setattr(settings, "TEST_WEB_URL", None)
    monkeypatch.setattr(settings, "USERS_CLERK_JWT_KEY", None)
    monkeypatch.setattr(settings, "USERS_CLERK_SECRET_KEY", None)
    init_db()
    session.reset()
    rate_limit.reset()
    app = FastAPI()
    app.add_middleware(BaseHTTPMiddleware, dispatch=test_web_auth.require_test_web_session)
    app.include_router(api_router, prefix=settings.API_V1_STR)
    return TestClient(app)


@pytest.fixture
def teacher_auth_on(monkeypatch):
    monkeypatch.setattr(settings, "USERS_CLERK_JWT_KEY", PUBLIC_PEM)
    monkeypatch.setattr(settings, "USERS_CLERK_SECRET_KEY", SecretStr("sk_test_prueba"))


# ---------------------------------------------------------------------------
# Sin USERS_CLERK_JWT_KEY: la API sigue anónima (local y hasta que el Frontend mande el token)
# ---------------------------------------------------------------------------

def test_sin_clave_la_api_sigue_anonima(client):
    assert not settings.teacher_auth_enabled
    assert client.post(ANALYSIS, json=SAMPLE).status_code == 200
    assert client.get(ADAPTATIONS).status_code == 404  # pasó el login: el diagnóstico no existe


# ---------------------------------------------------------------------------
# Con USERS_CLERK_JWT_KEY
# ---------------------------------------------------------------------------

def test_token_valido_puede_usar_la_api(client, teacher_auth_on):
    headers = bearer(clerk_token())
    assert client.post(ANALYSIS, json=SAMPLE, headers=headers).status_code == 200
    assert client.get(ADAPTATIONS, headers=headers).status_code == 404  # pasó el login: el diagnóstico no existe


def test_sin_token_responde_401_tambien_en_modo_mock(client, teacher_auth_on):
    response = client.post(ANALYSIS, json=SAMPLE)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "Iniciá sesión" in response.json()["detail"]
    assert client.get(ADAPTATIONS).status_code == 401


@pytest.fixture
def rejections(monkeypatch):
    """Motivos con los que verify_token rechazó los tokens del request."""
    reasons = []

    def spy(token, options):
        try:
            return verify_token(token, options)
        except TokenVerificationError as error:
            reasons.append(error.reason)
            raise

    monkeypatch.setattr(teacher_auth, "verify_token", spy)
    return reasons


# Los tokens se firman dentro del test y no al recolectar: si no, con la suite lenta vencerían y
# el 401 llegaría por vencimiento y no por el defecto que se prueba (Issue #115). El motivo del
# rechazo se comprueba para que cada caso falle solo por su defecto.
@pytest.mark.parametrize(
    "make_token, reason",
    [
        pytest.param(lambda: clerk_token(exp_in=-60), TokenVerificationErrorReason.TOKEN_EXPIRED, id="vencido"),
        pytest.param(lambda: clerk_token(azp="https://otro-sitio.example"),
                     TokenVerificationErrorReason.TOKEN_INVALID_AUTHORIZED_PARTIES, id="otro-origen"),
        pytest.param(lambda: clerk_token(key=OTHER_PRIVATE_PEM),
                     TokenVerificationErrorReason.TOKEN_INVALID_SIGNATURE, id="firmado-con-otra-clave"),
        pytest.param(lambda: "no-es-un-jwt", TokenVerificationErrorReason.TOKEN_INVALID, id="mal-formado"),
        pytest.param(lambda: "oat_token_de_maquina", None, id="no-es-de-sesion"),  # se rechaza antes de verificarlo
    ],
)
def test_token_invalido_responde_401(client, teacher_auth_on, rejections, make_token, reason):
    response = client.post(ANALYSIS, json=SAMPLE, headers=bearer(make_token()))
    assert response.status_code == 401
    assert "Volvé a iniciar sesión" in response.json()["detail"]
    assert rejections == ([reason] if reason else [])


def test_esquema_distinto_de_bearer_cuenta_como_sin_token(client, teacher_auth_on):
    response = client.post(ANALYSIS, json=SAMPLE, headers={"Authorization": f"Basic {clerk_token()}"})
    assert response.status_code == 401


def test_health_sigue_publico(client, teacher_auth_on):
    assert client.get("/api/v1/health").status_code == 200


def test_la_web_de_pruebas_sigue_con_su_propio_login(client, teacher_auth_on, monkeypatch):
    monkeypatch.setattr(settings, "TEST_WEB_URL", WEB + "/")
    web_token = session.create_token(session.local_subject(), purpose=session.TEST_WEB)
    response = client.post(ANALYSIS, json=SAMPLE, headers={"Origin": WEB, **bearer(web_token)})
    assert response.status_code == 200
