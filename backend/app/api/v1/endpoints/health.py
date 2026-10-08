from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings

router = APIRouter()


@router.get(
    "/health",
    summary="Verificar estado del backend",
    response_description="Estado actual del servicio, entorno y versión de la API",
)
async def health_check(settings: Settings = Depends(get_settings)):
    """
    ## Health Check del Sistema

    Verifica que el servidor de FastAPI esté en línea y que la configuración
    básica del proyecto esté cargada correctamente.

    - **status**: online si el servicio responde adecuadamente.
    - **environment**: Entorno activo (development, staging, production).
    - **version**: Versión actual del release del backend.
    - **project**: Nombre del proyecto configurado en el entorno.
    """
    return {
        "status": "online",
        "environment": settings.ENVIRONMENT,
        "version": settings.VERSION,
        "project": settings.PROJECT_NAME,
    }
