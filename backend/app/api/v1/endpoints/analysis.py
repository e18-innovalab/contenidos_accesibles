import asyncio
import json
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.rate_limit import limit_ai_usage
from app.db import analysis_repository
from app.schemas.analysis import AccessibilityAnalysisResponse, AnalysisSampleRequest
from app.services.accessibility_service import EmptyDocumentError, analyze_document
from app.services.document_service import document_service
from app.services.key_rotation_service import AllKeysExhaustedError
from app.services.llm.base import LLMInvalidResponseError, LLMUnavailableError

router = APIRouter()

# Límite máximo de archivo PDF: 10 MB
MAX_PDF_SIZE_BYTES = 10 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024  # 1 MB por lectura

_SAMPLE_REQUEST_BODY = {
    "required": True,
    "content": {
        "application/json": {"schema": AnalysisSampleRequest.model_json_schema()},
        # Texto tal cual (con saltos de línea), sin escaparlo dentro de un JSON.
        "text/plain": {
            "schema": {"type": "string"},
            "example": "Actividad 1:\n1. Leé el texto de la página 8.\n2. Respondé las preguntas.",
        },
    },
}


async def _read_sample_payload(request: Request) -> AnalysisSampleRequest:
    """
    Acepta `application/json` ({"text": "..."}) o `text/plain` (el texto crudo).

    El JSON se parsea con strict=False: tolera saltos de línea y tabulaciones
    literales dentro de los strings, que es lo que ocurre al pegar un material
    a mano en Swagger. Un JSON estricto los rechazaría con 422.
    """
    body = await request.body()
    content_type = request.headers.get("content-type", "")
    try:
        text = body.decode("utf-8")
        if content_type.startswith("text/plain"):
            return AnalysisSampleRequest(text=text)
        try:
            data = json.loads(text, strict=False)
        except json.JSONDecodeError as e:
            raise RequestValidationError(
                [{"type": "json_invalid", "loc": ("body", e.pos), "msg": f"JSON inválido: {e.msg}", "input": None}]
            )
        return AnalysisSampleRequest.model_validate(data)
    except UnicodeDecodeError:
        raise RequestValidationError(
            [{"type": "unicode_decode", "loc": ("body",), "msg": "El texto debe estar en UTF-8.", "input": None}]
        )
    except ValidationError as e:
        raise RequestValidationError(e.errors(include_url=False))


@router.post(
    "/sample",
    response_model=AccessibilityAnalysisResponse,
    summary="Diagnóstico de accesibilidad de un texto educativo",
    response_description="Diagnóstico estructurado con puntaje, dimensiones y barreras detectadas",
    openapi_extra={"requestBody": _SAMPLE_REQUEST_BODY},
    dependencies=[Depends(limit_ai_usage)],
)
async def analyze_sample(
    request: Request,
    background_tasks: BackgroundTasks,
    mock: bool = Query(
        default=False,
        description="Si es True, simula la IA (0 tokens) y ejecuta las reglas automáticas reales (ideal para desarrollo de Frontend).",
    ),
):
    """
    ## Escáner de Accesibilidad con IA + Reglas (Texto Pegado)

    Analiza un texto educativo pegado directamente y devuelve un diagnóstico
    tipado generado con **Salidas Estructuradas**, evaluando las dimensiones de
    **Comprensión**, **Estructura** y **Visual**. Usa las conexiones de IA configuradas en
    `/admin` (cualquier proveedor) en orden de prioridad.

    Además corre el **motor de reglas automáticas** sobre el texto completo (oraciones de más
    de 35 palabras, párrafos de más de 150 palabras). Sus barreras llegan con `source="rules"`.
    `estimated_score` combina el puntaje de la IA con el de reglas; el detalle del cálculo
    está en `score_breakdown` y las métricas en `metadata.rules_metrics`.

    Si se envía `?mock=true`, la IA se simula de forma instantánea (0 tokens) y las reglas
    se ejecutan igual, manteniendo el mismo contrato JSON para pruebas de UI en el Frontend.

    Cada barrera incluye un `id` único (`bar-1`, `bar-2`...) y `fragment_found`, que indica
    si el fragmento citado por la IA aparece textualmente en el material (control de alucinaciones).
    `metadata.provider` y `metadata.model` indican qué modelo respondió.
    """
    # Fuera del try: ValidationError es subclase de ValueError y terminaría como 400.
    payload = await _read_sample_payload(request)
    try:
        response = await analyze_document(document_service.process_text(payload.text), mock=mock)
        background_tasks.add_task(analysis_repository.delete_expired)
        return response
    except EmptyDocumentError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except AllKeysExhaustedError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except LLMInvalidResponseError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except LLMUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al comunicar con el proveedor de IA: {str(e)}",
        )


_ALLOWED_PDF_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/octet-stream",  # Algunos clientes HTTP genéricos envían octet-stream
}
_PDF_MAGIC_HEADER = b"%PDF-"


@router.post(
    "/pdf",
    response_model=AccessibilityAnalysisResponse,
    summary="Diagnóstico integral de un archivo PDF (Extracción + Reglas Visuales + IA)",
    response_description="Diagnóstico estructurado completo a partir de un archivo PDF",
    dependencies=[Depends(limit_ai_usage)],
)
async def analyze_pdf_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(
        ...,
        media_type="application/pdf",
        description="Archivo PDF educativo a diagnosticar (máximo 10 MB)",
    ),
    mock: bool = Query(
        default=False,
        description="Si es True, extrae el PDF y ejecuta las reglas reales, pero simula la respuesta de IA (0 tokens).",
    ),
):
    """
    ## Escáner Unificado de PDF (Semanas 2 y 3)

    Recibe un archivo `.pdf`, extrae su texto, metadatos, conteo de imágenes y heurísticas
    (como detección de PDF escaneado sin capa de texto) usando **PyMuPDF**, y ejecuta en un
    único paso el diagnóstico de accesibilidad combinando **reglas automáticas** + **IA**.

    - **Validación multicapa**: verifica extensión `.pdf`, `Content-Type` y firma binaria (*magic bytes* `%PDF-`).
    - **Lectura segura en chunks (1 MB)**: rechaza archivos mayores a 10 MB con `413` sin agotar la RAM.
    - **No bloqueante**: la extracción con PyMuPDF corre en un hilo separado (`asyncio.to_thread`).
    - **Párrafos reales**: el texto se extrae por bloques, así las reglas miden párrafos y oraciones
      aunque el PDF corte los renglones.
    - **Puntaje combinado**: `estimated_score` pondera IA y reglas; ver `score_breakdown`.
    - **Modo Mock (`?mock=true`)**: extrae las métricas reales del PDF subido (`page_count`, `image_count`),
      ejecuta las reglas automáticas y simula el análisis del LLM para diseñar pantallas de Frontend sin gastar cuota.
    """
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo subido debe tener extensión .pdf",
        )

    if file.content_type and file.content_type.lower() not in _ALLOWED_PDF_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Content-Type '{file.content_type}' no válido. Se esperaba 'application/pdf'.",
        )

    try:
        content = bytearray()
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            if not content and not chunk.lstrip().startswith(_PDF_MAGIC_HEADER):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El contenido del archivo no corresponde a un PDF válido (firma '%PDF-' ausente).",
                )
            content.extend(chunk)
            if len(content) > MAX_PDF_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="El archivo PDF supera el límite máximo permitido de 10 MB.",
                )

        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo PDF recibido está vacío (0 bytes).",
            )

        # Extracción con PyMuPDF en hilo separado para no bloquear el event loop
        doc = await asyncio.to_thread(document_service.process_pdf, bytes(content), filename)
        response = await analyze_document(doc, mock=mock)
        background_tasks.add_task(analysis_repository.delete_expired)
        return response
    except HTTPException:
        raise
    except EmptyDocumentError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except AllKeysExhaustedError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except LLMInvalidResponseError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except LLMUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error inesperado al analizar el archivo PDF: {str(e)}",
        )
    finally:
        await file.close()


@router.get(
    "/{analysis_id}",
    response_model=AccessibilityAnalysisResponse,
    summary="Recuperar un diagnóstico previo por ID",
    response_description="Diagnóstico estructurado previamente guardado",
)
async def get_analysis_by_id(analysis_id: str):
    """
    ## Recuperación de Diagnóstico por ID (Semana 4 - Issue #26)

    Permite consultar un diagnóstico generado previamente sin tener que volver a subir el material
    ni consumir tokens adicionales de IA. Si el diagnóstico ya superó su tiempo de vida (TTL),
    se elimina de la base de datos y se responde con 404 indicando su expiración.
    """
    record = analysis_repository.get(analysis_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnóstico no encontrado",
        )

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if record["expires_at"] < now_iso:
        analysis_repository.delete(analysis_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El diagnóstico ha expirado",
        )

    return AccessibilityAnalysisResponse.model_validate_json(record["diagnostic_json"])


