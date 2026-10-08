import logging
from pydantic import BaseModel, Field

from app.schemas.analysis import AltTextProposal
from app.schemas.document import ExtractedImage
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """Sos un especialista en accesibilidad educativa digital y pautas WCAG 1.1.1 (Contenido no textual).
Tu tarea es generar descripciones de texto alternativo pedagógicamente útiles para las imágenes extraídas de un material educativo.

Pautas obligatorias para cada propuesta:
1. Describí de forma concisa y clara la función y el contenido educativo de la imagen basándote en la imagen y en su contexto circundante.
2. Sé directo: NO comiences con "Imagen de", "Foto de", "Gráfico de" salvo que el formato sea imprescindible para comprender la información.
3. Si es un gráfico, esquema o mapa conceptual, incluí los datos y relaciones clave que el estudiante debe aprender.
4. Máximo 2 a 3 oraciones por propuesta.
5. Devolvé una propuesta por cada imagen recibida, manteniendo el image_index correspondiente.
"""


class AltTextItem(BaseModel):
    """Ítem individual retornado por el modelo multimodal para una imagen."""
    image_index: int = Field(description="Índice 1-based de la imagen correspondiente.")
    suggested_alt_text: str = Field(description="Texto alternativo pedagógico propuesto.")
    pedagogical_purpose: str | None = Field(
        default=None,
        description="Propósito educativo o justificación didáctica del contenido visual.",
    )


class AltTextBatchResponse(BaseModel):
    """Respuesta por lote del modelo multimodal que consolida todas las imágenes en una única llamada."""
    proposals: list[AltTextItem] = Field(
        default_factory=list,
        description="Lista de propuestas de texto alternativo.",
    )


class AltTextService:
    """
    Servicio de adaptación con IA multimodal para generación de texto alternativo
    en imágenes educativas (Tarea #28).
    
    Implementa procesamiento 100% en memoria (Privacy by Design) y llamada
    consolidada en un único lote para optimizar latencia y cuota (RPM).
    """

    @staticmethod
    def generate_mock_proposals(images: list[ExtractedImage]) -> list[AltTextProposal]:
        """Genera propuestas determinísticas simuladas sin consumir cuota de IA (0 tokens)."""
        proposals: list[AltTextProposal] = []
        for img in images:
            loc = img.location_description.lower()
            snippet = img.context_text[:120] + ("..." if len(img.context_text) > 120 else "")
            proposals.append(
                AltTextProposal(
                    image_index=img.image_index,
                    page_number=img.page_number,
                    location_description=img.location_description,
                    suggested_alt_text=(
                        f"[MOCK] Gráfico o ilustración pedagógica en {loc}. "
                        "Complementa el contenido conceptual de la sección."
                    ),
                    pedagogical_purpose="Facilitar la comprensión visual a estudiantes con discapacidad o lectores de pantalla.",
                    context_used=snippet,
                )
            )
        return proposals

    async def generate_proposals(self, images: list[ExtractedImage]) -> list[AltTextProposal]:
        """
        Envía las imágenes relevantes y su contexto cercano a un modelo multimodal
        usando una única llamada en lote con require_vision=True.
        """
        if not images:
            return []

        # Construir contenido multimodal en lote: texto explicativo + (imagen + contexto) por cada ítem
        contents: list[dict] = [
            {
                "type": "text",
                "text": (
                    f"Se extrajeron {len(images)} imágenes relevantes de este material educativo. "
                    "Analizá cada una y su contexto circundante para proponer un texto alternativo pedagógico."
                ),
            }
        ]

        for img in images:
            contents.append({
                "type": "image",
                "data": img.image_bytes,
                "mime_type": img.mime_type,
            })
            contents.append({
                "type": "text",
                "text": (
                    f"--- IMAGEN {img.image_index} ---\n"
                    f"Ubicación en documento: {img.location_description}\n"
                    f"Contexto textual cercano en la página:\n\"\"\"{img.context_text}\"\"\"\n"
                ),
            })

        logger.info(
            "Generando textos alternativos en lote para %d imágenes con IA multimodal (require_vision=True)",
            len(images),
        )

        result = await llm_service.generate_structured(
            system_instruction=SYSTEM_INSTRUCTION,
            contents=contents,
            schema=AltTextBatchResponse,
            temperature=0.2,
            require_vision=True,
        )

        # Mapear las propuestas del modelo a los esquemas de respuesta finales
        proposals_by_idx = {p.image_index: p for p in result.parsed.proposals}
        final_proposals: list[AltTextProposal] = []

        for img in images:
            item = proposals_by_idx.get(img.image_index)
            suggested = item.suggested_alt_text if item else f"Contenido visual ubicado en {img.location_description.lower()}."
            purpose = item.pedagogical_purpose if item else None
            snippet = img.context_text[:120] + ("..." if len(img.context_text) > 120 else "")

            final_proposals.append(
                AltTextProposal(
                    image_index=img.image_index,
                    page_number=img.page_number,
                    location_description=img.location_description,
                    suggested_alt_text=suggested,
                    pedagogical_purpose=purpose,
                    context_used=snippet,
                )
            )

        return final_proposals


alt_text_service = AltTextService()
