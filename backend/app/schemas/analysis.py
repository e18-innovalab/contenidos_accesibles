from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.document import TextInputRequest

# ---------------------------------------------------------------------------
# Esquemas que se envían al modelo de IA como salida estructurada (JSON Schema).
# Las `description` de cada Field viajan en el JSON Schema y guían al modelo,
# por eso están redactadas como instrucciones. No usar ge/le acá: no todos los
# proveedores los respetan; los rangos se validan en el servicio.
# ---------------------------------------------------------------------------

Category = Literal["comprension", "estructura", "accesibilidad_visual"]
DimensionStatus = Literal["correcta", "para_revisar", "barrera_detectada"]
Severity = Literal["para_revisar", "barrera_detectada"]


class DimensionAssessment(BaseModel):
    """Semáforo por dimensión: acá sí existe 'correcta'."""

    category: Category
    status: DimensionStatus = Field(
        description="Estado global de la dimensión en todo el material."
    )
    comment: str = Field(
        description="Una o dos oraciones que justifiquen el estado asignado."
    )


class BarrierDetected(BaseModel):
    category: Category
    severity: Severity = Field(
        description=(
            "'barrera_detectada' si impide o dificulta seriamente la comprensión o la "
            "realización de la tarea; 'para_revisar' si es una mejora recomendable."
        )
    )
    issue: str = Field(
        description="Nombre breve del problema. Ej: 'Consigna con múltiples acciones simultáneas'."
    )
    original_text: str = Field(
        description="Fragmento copiado TEXTUALMENTE del material, sin parafrasear ni resumir."
    )
    explanation: str = Field(description="Por qué este fragmento dificulta el acceso.")
    recommendation: str = Field(description="Acción concreta sugerida al docente.")
    suggested_rewrite: str | None = Field(
        default=None,
        description="Versión reescrita del fragmento aplicando la recomendación, si corresponde.",
    )


class AccessibilityDiagnostic(BaseModel):
    estimated_score: int = Field(
        description="Puntaje orientativo de accesibilidad entre 0 (muy inaccesible) y 100 (plenamente accesible)."
    )
    summary: str = Field(description="Resumen general del material en 2 a 4 oraciones.")
    dimensions: list[DimensionAssessment] = Field(
        description="Una evaluación por cada dimensión analizada (comprension y estructura)."
    )
    strengths: list[str] = Field(
        description="Aspectos del material que ya favorecen la accesibilidad."
    )
    barriers: list[BarrierDetected] = Field(
        description="Barreras concretas encontradas, ordenadas de mayor a menor impacto."
    )


# ---------------------------------------------------------------------------
# Esquemas de la API (lo que devuelve el backend, no lo que genera la IA).
# ---------------------------------------------------------------------------


MAX_SAMPLE_CHARS = 20_000


class AnalysisSampleRequest(TextInputRequest):
    text: str = Field(
        ...,
        min_length=10,
        max_length=MAX_SAMPLE_CHARS,
        description=f"Texto educativo a analizar (entre 10 y {MAX_SAMPLE_CHARS} caracteres).",
    )


class BarrierReport(BarrierDetected):
    id: str = Field(
        description="Identificador único de la barrera dentro del reporte (ej. 'bar-1', 'bar-2')."
    )
    fragment_found: bool | None = Field(
        description=(
            "True si original_text aparece en el material. False indica que el modelo "
            "parafraseó o inventó el fragmento (riesgo de alucinación). None si no aplica."
        )
    )
    source: Literal["ai", "rules"] = Field(
        description=(
            "'ai' si la detectó el modelo; 'rules' si la detectó el motor de reglas automáticas "
            "(oraciones y párrafos extensos, imágenes, PDF escaneado)."
        )
    )


class RulesMetrics(BaseModel):
    """Métricas objetivas que calcula el motor de reglas sobre el texto completo."""

    analyzed_word_count: int = Field(
        description="Palabras evaluadas por las reglas (el texto completo, aunque la IA lo reciba recortado)."
    )
    sentence_count: int
    long_sentences: int = Field(description="Oraciones que superan el umbral de palabras.")
    severe_long_sentences: int = Field(description="Oraciones que superan el umbral severo.")
    max_sentence_words: int
    paragraph_count: int
    long_paragraphs: int = Field(description="Párrafos que superan el umbral de palabras (muros de texto).")
    severe_long_paragraphs: int = Field(description="Párrafos que superan el umbral severo.")
    heading_count: int = Field(default=0, description="Cantidad de encabezados o títulos detectados.")
    hierarchy_levels: int = Field(default=0, description="Cantidad de niveles jerárquicos de títulos.")
    list_items_count: int = Field(default=0, description="Cantidad de ítems de listas detectados.")
    multi_action_prompts: int = Field(default=0, description="Consignas con múltiples acciones simultáneas.")
    readability_score_szigriszt: float | None = Field(
        default=None, description="Índice de legibilidad de Szigriszt-Pazos (IFSZ) para español."
    )
    visual_only_references: int = Field(
        default=0, description="Referencias exclusivas a elementos visuales o espaciales."
    )


class ScorePenalty(BaseModel):
    rule: str = Field(description="Regla que generó la penalización (ej. 'oraciones_extensas').")
    category: Category
    count: int = Field(description="Cantidad de casos detectados por la regla.")
    points: int = Field(description="Puntos que la regla le resta al puntaje de reglas.")


class ScoreBreakdown(BaseModel):
    """Cómo se llegó a estimated_score, para que el docente pueda entenderlo."""

    ai_score: int | None = Field(description="Puntaje propuesto por la IA. None si no se consultó a la IA.")
    rules_score: int = Field(description="100 menos la suma de penalizaciones de las reglas.")
    ai_weight: float
    rules_weight: float
    penalties: list[ScorePenalty]
    cap: int | None = Field(default=None, description="Tope aplicado al puntaje final, si corresponde.")
    cap_reason: str | None = None
    final_score: int = Field(ge=0, le=100)


class AnalysisMetadata(BaseModel):
    provider: str = Field(description="Proveedor de IA que generó el diagnóstico (ej. gemini, groq, mock).")
    model: str
    connection: str = Field(description="Nombre de la conexión de /admin que se usó.")
    latency_ms: int
    source_type: Literal["pdf", "text"] = Field(
        default="text", description="Formato de origen del material analizado ('pdf' o 'text')."
    )
    filename: str | None = Field(
        default=None, description="Nombre del archivo original (cuando source_type es 'pdf')."
    )
    page_count: int = Field(default=1, ge=1, description="Cantidad de páginas del documento.")
    image_count: int = Field(default=0, ge=0, description="Cantidad de imágenes detectadas en el documento.")
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    total_tokens: int | None = None
    analyzed_word_count: int
    is_truncated: bool
    unverified_fragments: int = Field(
        description="Cantidad de barreras cuyo fragmento no se encontró en el material."
    )
    rules_metrics: RulesMetrics | None = Field(
        default=None, description="Métricas calculadas por el motor de reglas automáticas."
    )


class AltTextProposal(BaseModel):
    """Propuesta de texto alternativo pedagógico para una imagen relevante del documento."""
    image_index: int = Field(
        ..., description="Índice secuencial de la imagen en el documento (1-based)."
    )
    page_number: int = Field(
        ..., description="Número de página donde se encuentra la imagen (1-based)."
    )
    location_description: str = Field(
        ..., description="Ubicación relativa en la página (ej. 'Página 1, sector superior')."
    )
    suggested_alt_text: str = Field(
        ..., description="Propuesta de texto alternativo pedagógico para la imagen."
    )
    pedagogical_purpose: str | None = Field(
        default=None, description="Propósito educativo o función didáctica de la imagen en el material."
    )
    context_used: str = Field(
        default="", description="Fragmento del texto circundante tomado como contexto."
    )


class AccessibilityAnalysisResponse(BaseModel):
    analysis_id: str | None = Field(
        default=None,
        description="Identificador único del diagnóstico (UUIDv4) para su recuperación posterior.",
    )
    expires_at: str | None = Field(
        default=None,
        description="Fecha y hora de expiración (UTC, formato ISO 8601) del diagnóstico.",
    )
    estimated_score: int = Field(
        ge=0,
        le=100,
        description="Puntaje orientativo final (0-100) que combina IA y reglas; ver score_breakdown.",
    )
    summary: str
    dimensions: list[DimensionAssessment]
    strengths: list[str]
    barriers: list[BarrierReport]
    alt_text_proposals: list[AltTextProposal] = Field(
        default_factory=list,
        description="Propuestas de texto alternativo generadas con IA multimodal para las imágenes del PDF.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Advertencias del procesamiento del documento y del análisis.",
    )
    score_breakdown: ScoreBreakdown | None = Field(
        default=None, description="Detalle del cálculo de estimated_score (IA + reglas)."
    )
    metadata: AnalysisMetadata

