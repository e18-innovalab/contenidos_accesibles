"""
Login de docentes con Clerk (Issue #60) y quién hace cada request, con su rol (Issue #61).

El Frontend inicia sesión con Clerk (Google o Microsoft) y manda el token de sesión en cada
request (`Authorization: Bearer <token>`). Esta dependencia lo valida sin llamadas de red, con
la clave pública de la aplicación de docentes (USERS_CLERK_JWT_KEY), igual que el panel valida el suyo
en app/admin/clerk_auth.py:

- Solo se aceptan tokens de sesión (los de máquina no aplican).
- El token tiene que haber sido emitido para uno de los orígenes del Frontend (authorized_parties
  = orígenes de CORS): un token robado no sirve desde otro sitio.
- El rol sale del claim `role` (publicMetadata.role en la plantilla del token de sesión de Clerk).

Sin USERS_CLERK_JWT_KEY no se exige nada (local y hasta que el Frontend esté listo): quien llama es
el usuario anónimo, con rol docente. Las llamadas de la web de pruebas ya llegan validadas por su
propio login (app/admin/test_web_auth.py): sus recursos quedan a nombre de esa persona y su rol
de la API sale del rol del panel (admin -> admin, solo lectura -> docente).
"""
import re
from contextvars import ContextVar

from clerk_backend_api.security.types import (
    TokenType,
    TokenVerificationError,
    TokenVerificationErrorReason,
    VerifyTokenOptions,
)
from clerk_backend_api.security.verifytoken import get_token_type, verify_token
from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings
from app.core.permissions import ADMIN, ANONYMOUS_OWNER, DOCENTE, Caller, role_from_claim

_caller: ContextVar[Caller | None] = ContextVar("caller", default=None)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _bearer_token(request: Request) -> str | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def owner_for_test_web(kind: str, username: str) -> str:
    """Dueño de los recursos creados desde la web de pruebas: test-web_<tipo>_<usuario>.

    En minúsculas (GitHub no distingue mayúsculas) y solo con caracteres seguros, porque va en
    las claves de R2 (users/<dueño>/...). No choca con los ids de Clerk, que empiezan con "user_".
    """
    return f"test-web_{kind}_{re.sub(r'[^a-z0-9-]', '_', username.lower())}"


def _resolve_caller(request: Request) -> Caller:
    principal = getattr(request.state, "test_web_principal", None)
    if principal is not None:
        return Caller(
            owner_for_test_web(principal.kind, principal.username),
            ADMIN if principal.can_edit else DOCENTE,
            authenticated=True,
        )
    if not settings.teacher_auth_enabled:
        return Caller(ANONYMOUS_OWNER)

    token = _bearer_token(request)
    if token is None:
        raise _unauthorized("Iniciá sesión para usar la API.")
    try:
        if get_token_type(token) != TokenType.SESSION_TOKEN:
            raise TokenVerificationError(TokenVerificationErrorReason.INVALID_TOKEN_TYPE)
        claims = verify_token(
            token,
            VerifyTokenOptions(jwt_key=settings.USERS_CLERK_JWT_KEY, authorized_parties=settings.cors_origins),
        )
    except TokenVerificationError:
        raise _unauthorized("La sesión no es válida o venció. Volvé a iniciar sesión.")
    return Caller(claims["sub"], role_from_claim(claims.get("role")), authenticated=True)


async def current_caller(request: Request) -> Caller:
    """Dependencia: quién llama. 401 si el login de docentes está activo y no hay un token válido.

    Queda en request.state.caller para el rate limit por usuario (app/core/rate_limit.py) y en el
    contexto del request (caller_in_context) para el historial de uso (Issue #104): así la llamada
    a la IA queda a nombre del usuario sin pasarlo por todos los servicios. Es async para que el
    valor del contexto llegue al endpoint (una dependencia sync corre en otro hilo y lo perdería).
    """
    caller = getattr(request.state, "caller", None)
    if caller is None:
        caller = _resolve_caller(request)
        request.state.caller = caller
    _caller.set(caller)
    return caller


def caller_in_context() -> Caller | None:
    """Quién hace el request en curso; None fuera de un request de la API (p. ej. el panel)."""
    return _caller.get()


def require_permission(permission: str):
    """Dependencia: 401 sin sesión válida (si el login está activo) y 403 si el rol no tiene el permiso."""

    def dependency(caller: Caller = Depends(current_caller)) -> Caller:
        if not caller.can(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu usuario no tiene permiso para esta acción.",
            )
        return caller

    return dependency
