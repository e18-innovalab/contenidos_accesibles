import secrets
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import settings

security = HTTPBasic()
# Realm propio para que el navegador no mezcle estas credenciales con las de /admin.
DOCS_REALM = "docs"
docs_security = HTTPBasic(realm=DOCS_REALM)


def get_current_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Valida usuario/contraseña de administrador (HTTP Basic Auth).
    Usa secrets.compare_digest para evitar timing attacks.
    """
    is_user_ok = secrets.compare_digest(credentials.username, settings.ADMIN_USERNAME)
    is_pass_ok = secrets.compare_digest(
        credentials.password, settings.ADMIN_PASSWORD.get_secret_value()
    )
    if not (is_user_ok and is_pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de administrador inválidas.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_docs_user(credentials: HTTPBasicCredentials = Depends(docs_security)) -> str:
    """
    Valida las credenciales de la documentación (/docs, /redoc, openapi.json)
    en staging/production. Solo se registra cuando settings.docs_protected.
    """
    expected = settings.DOCS_PASSWORD.get_secret_value() if settings.DOCS_PASSWORD else ""
    is_user_ok = secrets.compare_digest(credentials.username, settings.DOCS_USERNAME)
    is_pass_ok = secrets.compare_digest(credentials.password, expected)
    if not (expected and is_user_ok and is_pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de documentación inválidas.",
            headers={"WWW-Authenticate": f'Basic realm="{DOCS_REALM}"'},
        )
    return credentials.username


def verify_same_origin(request: Request) -> None:
    """
    Mitigación CSRF para los POST de /admin: HTTP Basic Auth reenvía
    credenciales automáticamente en cualquier request al mismo origen,
    incluso si el POST fue disparado desde una página externa. Se
    rechaza si el Origin/Referer no coincide con el host del backend.
    """
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin:
        origin_host = urlparse(origin).netloc
        if origin_host and origin_host != request.url.netloc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Origen no permitido.",
            )
