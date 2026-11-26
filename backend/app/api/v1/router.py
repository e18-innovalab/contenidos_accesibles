from fastapi import APIRouter, Depends
from app.api.v1.endpoints import (
    adaptations,
    analysis,
    documents,
    export,
    files,
    health,
    metrics,
    privacy,
    settings,
    test_ai,
    transformations,
)
from app.core.teacher_auth import require_permission

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(privacy.router, prefix="/privacy", tags=["Privacy"])
api_router.include_router(test_ai.router, prefix="/ai", tags=["AI Integration"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
# Login de docentes (Issue #60) y permisos por rol (Issue #61). El login se exige solo con
# USERS_CLERK_JWT_KEY configurada. /files pide permiso ruta por ruta: sus URLs firmadas del
# almacenamiento local no llevan token.
_AUTH_RESPONSES = {
    401: {"description": "Falta el token de sesión del docente o no es válido (solo con USERS_CLERK_JWT_KEY configurada)"},
    403: {"description": "El rol del usuario no tiene permiso para esta acción."},
}
api_router.include_router(
    analysis.router, prefix="/analysis", tags=["Accessibility Analysis"],
    dependencies=[Depends(require_permission("analysis:create"))], responses=_AUTH_RESPONSES,
)
api_router.include_router(
    adaptations.router, prefix="/adaptations", tags=["AI Adaptations"],
    dependencies=[Depends(require_permission("adaptations:manage"))], responses=_AUTH_RESPONSES,
)
api_router.include_router(
    export.router, prefix="/export", tags=["Export"],
    dependencies=[Depends(require_permission("export:create"))], responses=_AUTH_RESPONSES,
)
api_router.include_router(
    transformations.router, prefix="/transformations", tags=["Transformations"],
    dependencies=[Depends(require_permission("transformations:manage"))], responses=_AUTH_RESPONSES,
)
api_router.include_router(files.router, prefix="/files", tags=["Files"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["Metrics"], responses=_AUTH_RESPONSES)
# Configuración editable por un admin (Issue #64): cada ruta exige settings:retention
api_router.include_router(settings.router, prefix="/settings", tags=["Settings"], responses=_AUTH_RESPONSES)
