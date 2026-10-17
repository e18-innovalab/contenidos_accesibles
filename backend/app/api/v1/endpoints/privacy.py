"""
Endpoint de política de datos y privacidad (Issue #41).

Expone la política activa del backend para que el Frontend pueda renderizar el aviso
de procesamiento con IA externa y las garantías de almacenamiento/privacidad.
"""

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.privacy import (
    ExternalAIProcessingPolicy,
    PrivacyPolicyResponse,
    StoragePolicy,
)
from app.services.document_service import MAX_ANALYSIS_WORDS

router = APIRouter()


@router.get(
    "/policy",
    response_model=PrivacyPolicyResponse,
    summary="Consultar política de privacidad y tratamiento de datos (Issue #41)",
    description=(
        "Devuelve las condiciones de privacidad activas en el backend: proveedor y modelo de IA en uso, "
        "qué datos se envían a la IA externa, filtros de datos personales (PII), garantía de no persistencia "
        "en disco local y política de retención en almacenamiento temporal (Cloudflare R2 o local)."
    ),
)
def get_privacy_policy() -> PrivacyPolicyResponse:
    storage_provider = (
        "Cloudflare R2 (bucket privado cifrado en reposo)"
        if settings.STORAGE_BACKEND == "r2"
        else "Almacenamiento local (desarrollo)"
    )

    return PrivacyPolicyResponse(
        external_ai_processing=ExternalAIProcessingPolicy(
            enabled=True,
            provider=settings.AI_PROVIDER,
            model=settings.AI_MODEL,
            max_words_per_analysis=MAX_ANALYSIS_WORDS,
            data_sent_description=(
                f"Únicamente el texto extraído del documento educativo (hasta {MAX_ANALYSIS_WORDS} palabras). "
                "Los archivos binarios originales nunca se envían al proveedor de IA."
            ),
            pii_protection=(
                "Detección preventiva local con expresiones regulares: se buscan DNI, CUIL/CUIT, nombres rotulados "
                "('alumno/estudiante: ...') y calificaciones antes de llamar a la IA. Si se detectan datos personales, "
                "el material se rechaza inmediatamente sin enviarse a la IA ni guardarse."
            ),
        ),
        storage_policy=StoragePolicy(
            local_disk_storage="Cero persistencia en disco local. Todos los documentos se procesan en memoria volátil (RAM).",
            storage_backend=settings.STORAGE_BACKEND,
            storage_provider_name=storage_provider,
            retention_period_hours=settings.FILE_TTL_HOURS,
            auto_deletion_enabled=True,
            object_folders={
                "uploads": "Archivos originales subidos por el docente",
                "results": "Diagnósticos e informes de accesibilidad",
                "adapted": "Versiones adaptadas generadas",
            },
        ),
        user_rights=(
            "El docente mantiene el control pedagógico total de su material. Los datos se eliminan "
            f"automáticamente al transcurrir el período de retención de {settings.FILE_TTL_HOURS} horas."
        ),
    )
