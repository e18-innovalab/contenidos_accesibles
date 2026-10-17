from fastapi import APIRouter, Depends
from app.api.v1.endpoints import (
    adaptations,
    analysis,
    documents,
    export,
    files,
    health,
    privacy,
    test_ai,
)
from app.core.teacher_auth import require_teacher

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(privacy.router, prefix="/privacy", tags=["Privacy"])
api_router.include_router(test_ai.router, prefix="/ai", tags=["AI Integration"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
# Login de docentes (Issue #60): se exige solo con USERS_CLERK_JWT_KEY configurada
_TEACHER_401 = {401: {"description": "Falta el token de sesión del docente o no es válido (solo con USERS_CLERK_JWT_KEY configurada)"}}
api_router.include_router(
    analysis.router, prefix="/analysis", tags=["Accessibility Analysis"],
    dependencies=[Depends(require_teacher)], responses=_TEACHER_401,
)
api_router.include_router(
    adaptations.router, prefix="/adaptations", tags=["AI Adaptations"],
    dependencies=[Depends(require_teacher)], responses=_TEACHER_401,
)
api_router.include_router(export.router, prefix="/export", tags=["Export"])
api_router.include_router(files.router, prefix="/files", tags=["Files"])
