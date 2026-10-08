import asyncio
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from app.schemas.document import ExtractedDocument, TextInputRequest
from app.services.document_service import document_service

router = APIRouter()

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 Megabytes


@router.post(
    "/process-text",
    response_model=ExtractedDocument,
    summary="Procesar texto plano directo",
    response_description="Contenido extraído y métricas del texto ingresado"
)
async def process_raw_text(payload: TextInputRequest):
    """
    ## Procesamiento de Texto Directo (Semana 1)

    Permite al docente ingresar o pegar texto directamente en la plataforma.
    Calcula cantidad de palabras, caracteres y prepara el contenido
    para el escáner de accesibilidad.
    """
    try:
        return document_service.process_text(raw_text=payload.text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al procesar el texto: {str(e)}"
        )


_ALLOWED_PDF_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/octet-stream",
}
_PDF_MAGIC_HEADER = b"%PDF-"


@router.post(
    "/upload-pdf",
    response_model=ExtractedDocument,
    summary="Cargar y extraer contenido de un archivo PDF",
    response_description="Contenido textual, métricas y detección de imágenes del PDF"
)
async def upload_pdf_document(
    file: UploadFile = File(
        ...,
        media_type="application/pdf",
        description="Archivo PDF educativo (máximo 10 MB)",
    )
):
    """
    ## Carga y Extracción de Documento PDF (Semana 1)

    Recibe un material educativo en formato PDF:
    - **Validación multicapa:** Extensión `.pdf`, `Content-Type` y firma binaria (`%PDF-`).
    - **No bloqueante (Threadpool):** Se ejecuta en un hilo separado con asyncio.to_thread para no congelar el bucle de eventos.
    - **Procesamiento en memoria:** No almacena archivos en disco (requisito de privacidad docente).
    - **Extracción de texto:** Extrae todo el contenido página por página mediante PyMuPDF.
    - **Detección de imágenes:** Cuenta cuántas imágenes contiene el documento para evaluar textos alternativos.
    - **Detección de escaneos:** Identifica si el PDF es una fotocopia/imagen sin texto seleccionable.
    - **Límite de tamaño:** Máximo 10 MB por archivo.
    """
    # 1. Validar extensión y Content-Type
    filename = file.filename or "documento.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato no admitido. El archivo debe tener extensión .pdf."
        )

    if file.content_type and file.content_type.lower() not in _ALLOWED_PDF_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Content-Type '{file.content_type}' no válido. Se esperaba 'application/pdf'."
        )

    # 2. Leer archivo en chunks con límite de tamaño y verificar magic header (%PDF-)
    content = bytearray()
    chunk_size = 1024 * 1024  # 1 MB

    while chunk := await file.read(chunk_size):
        if not content and not chunk.lstrip().startswith(_PDF_MAGIC_HEADER):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El contenido del archivo no corresponde a un PDF válido (firma '%PDF-' ausente)."
            )
        content.extend(chunk)
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="El archivo excede el tamaño máximo permitido de 10 MB."
            )

    # 3. Procesar en un hilo separado de CPU para no bloquear FastAPI
    try:
        return await asyncio.to_thread(
            document_service.process_pdf,
            bytes(content),
            filename
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al procesar el PDF: {str(e)}"
        )
