from fastapi import APIRouter, HTTPException

from app.services.key_rotation_service import AllKeysExhaustedError
from app.services.llm.base import LLMUnavailableError
from app.services.llm_service import llm_service

router = APIRouter()


@router.post(
    "/test-connection",
    summary="Validar conexión con el proveedor de IA",
    response_description="Conexión usada y respuesta del modelo",
)
@router.post(
    "/test-gemini",
    summary="Validar conexión con el proveedor de IA (obsoleto: usar /ai/test-connection)",
    deprecated=True,
)
async def test_ai_connection():
    """
    ## Prueba de Conectividad con el Proveedor de IA

    Envía un prompt de verificación usando la conexión de IA activa según la
    prioridad configurada en el [panel de administración](/admin). Si la
    conexión falla o está limitada, rota automáticamente a la siguiente
    (aunque sea de otro proveedor).

    ### Respuestas posibles:
    - **200 OK**: La conexión respondió; se informa proveedor, modelo y respuesta.
    - **400 Bad Request**: No hay ninguna conexión de IA habilitada (agregar una desde `/admin`).
    - **429 Too Many Requests**: Todas las conexiones alcanzaron su límite.
    - **503 Service Unavailable**: Ninguna conexión pudo responder (proveedores caídos o mal configurados).
    - **500 Internal Server Error**: Error inesperado.
    """
    try:
        return await llm_service.ping_connection()
    except AllKeysExhaustedError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except LLMUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al comunicar con el proveedor de IA: {str(e)}",
        )
