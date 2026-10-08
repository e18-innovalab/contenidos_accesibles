import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db import analysis_repository
from app.schemas.analysis import (
    AccessibilityAnalysisResponse,
    AccessibilityDiagnostic,
    AltTextProposal,
    AnalysisMetadata,
    BarrierReport,
    DimensionAssessment,
)
from app.schemas.document import ExtractedDocument
from app.services.alt_text_service import alt_text_service
from app.services.llm_service import llm_service

from app.services.rules_service import (
    LONG_SENTENCE_WORDS,
    RuleFinding,
    RulesResult,
    compute_score,
    run_rules,
    split_sentences,
    worst_status,
)

logger = logging.getLogger(__name__)

MAX_BARRIERS = 10

# Largo mínimo (normalizado) de un fragmento de la IA para considerarlo la misma cita que una regla.
MIN_OVERLAP_CHARS = 20

SYSTEM_PROMPT = f"""
Sos un especialista en accesibilidad de materiales educativos y en Diseño Universal
para el Aprendizaje (DUA). Tu tarea es diagnosticar barreras de acceso en materiales
que docentes de nivel secundario y superior entregan a sus estudiantes, y proponer
mejoras concretas y aplicables.

## Dimensiones a evaluar

### 1. comprension (complejidad del lenguaje)
- Oraciones muy largas (más de {LONG_SENTENCE_WORDS} palabras) o con muchas subordinadas encadenadas.
- Vocabulario rebuscado o poco frecuente cuando existe un equivalente más simple.
- Tecnicismos NO definidos la primera vez que aparecen.
- Voz pasiva, nominalizaciones excesivas o doble negación que oscurecen quién hace qué.
- Ambigüedades: referencias poco claras ("esto", "lo anterior"), siglas sin desarrollar.

### 2. estructura (organización de consignas e instrucciones)
- Consignas con múltiples acciones simultáneas en una misma oración
  (ej.: "leé, subrayá, resumí y respondé...") sin separarlas en pasos.
- Consignas extensas donde la acción principal queda enterrada en el texto.
- Falta de pasos numerados, criterios de entrega o producto esperado explícito.
- Bloques de texto densos sin títulos, párrafos ni jerarquía visual.

## Criterios para evitar falsos positivos
- La terminología técnica PROPIA de la disciplina (fórmulas, conceptos de matemática,
  química, biología, etc.) NO es una barrera en sí misma: solo marcala si se usa sin
  definir o si podría explicarse con apoyo adicional.
- El voseo y las expresiones del español rioplatense (ej.: "leé", "tenés", "resolvé")
  son registro válido y NO constituyen una barrera.
- Si el material es claro, decilo: no inventes barreras para completar la lista.
- No evalúes imágenes, gráficos ni formato visual que no puedas ver en el texto.

## Reglas de salida
- `original_text` debe ser una copia TEXTUAL y exacta de un fragmento del material
  (máximo 2 oraciones). Nunca parafrasees ni resumas en ese campo.
- Reportá como máximo {MAX_BARRIERS} barreras, ordenadas de mayor a menor impacto.
- No repitas el mismo fragmento en varias barreras: si un fragmento tiene problemas
  de comprensión y de estructura, reportalo una sola vez en la categoría de mayor
  impacto y mencioná el otro problema en `explanation`.
- Incluí en `dimensions` una evaluación para `comprension` y otra para `estructura`.
- `estimated_score` es orientativo: 90-100 material muy accesible, 70-89 con mejoras
  menores, 50-69 con barreras relevantes, menos de 50 con barreras graves.
- Redactá `summary`, `explanation`, `recommendation` y `suggested_rewrite` en español
  neutro, claro y respetuoso hacia el docente. Si el material usa voseo, mantené el
  voseo en `suggested_rewrite` para respetar su registro.
""".strip()


class EmptyDocumentError(ValueError):
    """El documento no tiene texto analizable (p. ej. PDF escaneado sin OCR)."""


@dataclass
class _AIPart:
    """Lo que aporta la IA (real o simulada) al diagnóstico, antes de unirlo con las reglas."""

    score: int | None
    summary: str
    dimensions: list[DimensionAssessment]
    strengths: list[str]
    barriers: list[dict]


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[\"'“”‘’«»]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _fragment_parts(fragment: str) -> list[str]:
    """El modelo a veces abrevia con '...': cada tramo se compara por separado."""
    parts = [_normalize(p) for p in re.split(r"\.{3}|…", fragment)]
    return [p for p in parts if p]


def _fragment_in_text(fragment: str, normalized_text: str) -> bool:
    parts = _fragment_parts(fragment)
    return bool(parts) and all(p in normalized_text for p in parts)


def _ai_covers(ai_barrier: dict, finding: RuleFinding) -> bool:
    """
    True si una barrera de la IA ya señala el texto que marcó una regla. Se prefiere
    la de la IA porque trae suggested_rewrite. Las citas no verificadas no cuentan.

    Un párrafo extenso solo se da por cubierto con una barrera de estructura que cite
    su comienzo (así señala la IA un bloque denso): una barrera sobre una oración
    del medio del párrafo habla de otro problema y no resuelve el muro de texto.
    """
    if not finding.anchor or not ai_barrier["fragment_found"]:
        return False
    anchor = _normalize(finding.anchor)
    parts = [p for p in _fragment_parts(ai_barrier["original_text"]) if len(p) >= MIN_OVERLAP_CHARS]
    if finding.barrier["category"] == "estructura":
        return ai_barrier["category"] == "estructura" and bool(parts) and anchor.startswith(parts[0])
    return any(p in anchor or anchor in p for p in parts)


def _merge_dimensions(
    ai_dimensions: list[DimensionAssessment], rule_dimensions: list[DimensionAssessment]
) -> list[DimensionAssessment]:
    """
    Cada dimensión toma el peor estado entre IA y reglas, para que el semáforo no diga
    'correcta' mientras se lista una barrera de esa categoría. La visual es solo de reglas.
    """
    by_category = {d.category: d for d in ai_dimensions if d.category != "accesibilidad_visual"}
    merged = []
    for rule_dim in rule_dimensions:
        ai_dim = by_category.get(rule_dim.category)
        if ai_dim is None:
            merged.append(rule_dim)
        elif rule_dim.status == "correcta":
            merged.append(ai_dim)
        else:
            merged.append(DimensionAssessment(
                category=rule_dim.category,
                status=worst_status(ai_dim.status, rule_dim.status),
                comment=f"{ai_dim.comment} Reglas automáticas: {rule_dim.comment}",
            ))
    return merged


def _assign_barrier_ids(raw_barriers: list[dict]) -> list[BarrierReport]:
    """Asigna identificadores secuenciales ('bar-1', 'bar-2', ...) a cada barrera del reporte."""
    return [
        BarrierReport(id=f"bar-{idx}", **item)
        for idx, item in enumerate(raw_barriers, start=1)
    ]


def _build_response(
    doc: ExtractedDocument,
    ai: _AIPart,
    rules: RulesResult,
    *,
    warnings: list[str],
    analysis_id: str | None = None,
    expires_at: str | None = None,
    alt_text_proposals: list[AltTextProposal] | None = None,
    **metadata_fields,
) -> AccessibilityAnalysisResponse:
    """Une el aporte de la IA con el del motor de reglas en un único diagnóstico."""
    if analysis_id is None:
        analysis_id = str(uuid.uuid4())
    if expires_at is None:
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=settings.ANALYSIS_TTL_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")

    rule_barriers = [
        f.barrier for f in rules.findings if not any(_ai_covers(b, f) for b in ai.barriers)
    ]
    # Graves primero; dentro de cada severidad se respeta el orden de impacto de la IA.
    barriers = sorted(ai.barriers + rule_barriers, key=lambda b: b["severity"] != "barrera_detectada")
    breakdown = compute_score(ai.score, rules)

    if doc.is_truncated:
        warnings = warnings + ["Las reglas automáticas evaluaron el material completo."]

    return AccessibilityAnalysisResponse(
        analysis_id=analysis_id,
        expires_at=expires_at,
        estimated_score=breakdown.final_score,
        summary=ai.summary,
        dimensions=_merge_dimensions(ai.dimensions, rules.dimensions),
        strengths=ai.strengths,
        barriers=_assign_barrier_ids(barriers),
        alt_text_proposals=alt_text_proposals or [],
        warnings=warnings,
        score_breakdown=breakdown,
        metadata=AnalysisMetadata(
            source_type=doc.source_type,
            filename=doc.filename,
            page_count=doc.page_count,
            image_count=doc.image_count,
            rules_metrics=rules.metrics,
            **metadata_fields,
        ),
    )



def _mock_ai_part(doc: ExtractedDocument) -> _AIPart:
    text = doc.text_for_analysis.strip()
    sentences = split_sentences(text)
    first_sentence = sentences[0] if sentences else "Fragmento de ejemplo del documento."
    if len(first_sentence) > 160:
        first_sentence = first_sentence[:160] + "..."

    return _AIPart(
        score=68,
        summary=(
            "[MODO MOCK] El material presenta objetivos pedagógicos claros, pero se identificaron "
            "oportunidades de mejora en la segmentación de consignas en pasos y en la simplificación "
            "de algunas estructuras sintácticas."
        ),
        dimensions=[
            DimensionAssessment(
                category="comprension",
                status="para_revisar",
                comment="El registro general es adecuado, aunque contiene oraciones extensas que podrían simplificarse.",
            ),
            DimensionAssessment(
                category="estructura",
                status="barrera_detectada",
                comment="Se observan instrucciones encadenadas que conviene desglosar en listas numeradas.",
            ),
        ],
        strengths=[
            "Propósito pedagógico identificable en el material.",
            "Temática pertinente para el nivel educativo objetivo.",
        ],
        barriers=[
            {
                "category": "estructura",
                "severity": "barrera_detectada",
                "issue": "Consigna con múltiples acciones simultáneas",
                "original_text": first_sentence,
                "explanation": (
                    "Concentrar varias instrucciones dentro de una misma oración sobrecarga la memoria "
                    "de trabajo y dificulta que el estudiante identifique el orden de resolución."
                ),
                "recommendation": "Dividí la consigna en una lista numerada donde cada paso indique una única acción.",
                "suggested_rewrite": (
                    "1. Leé el texto completo.\n"
                    "2. Subrayá las ideas principales de cada párrafo.\n"
                    "3. Completá el cuadro sinóptico.\n"
                    "4. Respondé las preguntas de la guía."
                ),
                "fragment_found": bool(text),
                "source": "ai",
            },
            {
                "category": "comprension",
                "severity": "para_revisar",
                "issue": "Oración extensa con vocabulario complejo",
                "original_text": first_sentence,
                "explanation": (
                    "Las formulaciones abstractas o de longitud excesiva pueden dificultar la comprensión "
                    "autónoma de qué se espera como entrega final."
                ),
                "recommendation": "Reemplazá las nominalizaciones por verbos directos y oraciones breves en lenguaje claro.",
                "suggested_rewrite": "Explicá con tus palabras los temas principales que vimos en clase.",
                "fragment_found": bool(text),
                "source": "ai",
            },
        ],
    )


def build_mock_analysis_response(doc: ExtractedDocument) -> AccessibilityAnalysisResponse:
    """
    Genera un diagnóstico simulado instantáneo (0 tokens, ~1ms) para facilitar
    el desarrollo e integración de Frontend sin consumir cuota de los proveedores de IA.
    Solo se simula la IA: las reglas automáticas y el puntaje combinado son reales.
    """
    alt_proposals = (
        alt_text_service.generate_mock_proposals(doc.extracted_images)
        if doc.extracted_images
        else []
    )
    return _build_response(
        doc,
        _mock_ai_part(doc),
        run_rules(doc),
        warnings=list(doc.warnings) + [
            "Diagnóstico generado en modo simulación (?mock=true). No se consumieron tokens de IA."
        ],
        alt_text_proposals=alt_proposals,
        provider="mock",
        model="mock-accessibility-v1",
        connection="Simulador Frontend (?mock=true)",
        latency_ms=1,
        prompt_tokens=0,
        output_tokens=0,
        thinking_tokens=0,
        total_tokens=0,
        analyzed_word_count=doc.word_count,
        is_truncated=doc.is_truncated,
        unverified_fragments=0,
    )


async def analyze_document(
    doc: ExtractedDocument,
    *,
    overrides: dict | None = None,
    mock: bool = False,
    persist: bool = True,
) -> AccessibilityAnalysisResponse:
    """
    Punto de entrada del motor: recibe el contrato ExtractedDocument (generado por
    DocumentService) y devuelve el diagnóstico combinando IA + reglas.
    - mock: si es True, simula la IA (sin llamarla); las reglas corren igual.
    - overrides: parámetros del proveedor que pisan los de la conexión (benchmarks).
    - persist: si es True, almacena el diagnóstico y texto extraído en SQLite con TTL.
    """
    if mock:
        response = build_mock_analysis_response(doc)
    else:
        # Generar propuestas de texto alternativo con IA multimodal si hay imágenes relevantes
        alt_text_proposals: list[AltTextProposal] = []
        alt_text_warnings: list[str] = []
        if doc.extracted_images:
            try:
                alt_text_proposals = await alt_text_service.generate_proposals(doc.extracted_images)
            except Exception as e:
                logger.warning("No se pudieron generar textos alternativos con IA multimodal: %s", e)
                alt_text_warnings.append(
                    f"No se pudieron generar propuestas de texto alternativo para las imágenes: {e}"
                )

        text = doc.text_for_analysis.strip()

        # Caso especial: PDF escaneado sin texto digital seleccionable (solo reglas, sin IA).
        if not text and doc.is_scanned_pdf:
            no_text_part = _AIPart(
                score=None,
                summary=(
                    "No fue posible analizar el contenido textual porque el archivo PDF parece ser un "
                    "escaneo o fotografía sin capa de texto digital seleccionable."
                ),
                dimensions=[
                    DimensionAssessment(
                        category="comprension",
                        status="para_revisar",
                        comment="Sin texto digital seleccionable para evaluar comprensión lectora.",
                    ),
                    DimensionAssessment(
                        category="estructura",
                        status="para_revisar",
                        comment="Sin texto digital seleccionable para evaluar jerarquía y consignas.",
                    ),
                ],
                strengths=[],
                barriers=[],
            )
            response = _build_response(
                doc,
                no_text_part,
                run_rules(doc),
                warnings=list(doc.warnings) + alt_text_warnings,
                alt_text_proposals=alt_text_proposals,
                provider="rules",
                model="static-rules",
                connection="Motor de reglas (sin llamada a IA)",
                latency_ms=0,
                analyzed_word_count=0,
                is_truncated=False,
                unverified_fragments=0,
            )
        elif not text:
            raise EmptyDocumentError(
                "El material no contiene texto analizable. Si es un PDF escaneado, "
                "subí una versión con texto seleccionable."
            )
        else:
            # Las reglas no dependen de la IA: si fallan, falla el análisis antes de gastar tokens.
            rules = run_rules(doc)

            result = await llm_service.generate_structured(
                system_instruction=SYSTEM_PROMPT,
                contents=f"Material educativo a analizar:\n\n<<<\n{text}\n>>>",
                schema=AccessibilityDiagnostic,
                overrides=overrides,
            )
            diagnostic = result.parsed

            normalized_text = _normalize(text)
            ai_barriers = [
                {
                    **b.model_dump(),
                    "fragment_found": _fragment_in_text(b.original_text, normalized_text),
                    "source": "ai",
                }
                for b in diagnostic.barriers[:MAX_BARRIERS]
            ]
            unverified = sum(1 for b in ai_barriers if not b["fragment_found"])

            # El aviso de truncado ya lo genera DocumentService en doc.warnings.
            warnings = list(doc.warnings) + alt_text_warnings
            if unverified:
                warnings.append(
                    f"{unverified} fragmento(s) citados por la IA no coinciden textualmente con el "
                    "material: revisalos antes de aplicar la recomendación."
                )

            usage = result.usage
            response = _build_response(
                doc,
                _AIPart(
                    score=diagnostic.estimated_score,
                    summary=diagnostic.summary,
                    dimensions=diagnostic.dimensions,
                    strengths=diagnostic.strengths,
                    barriers=ai_barriers,
                ),
                rules,
                warnings=warnings,
                alt_text_proposals=alt_text_proposals,
                provider=result.provider,
                model=result.model,
                connection=result.connection_label,
                latency_ms=result.latency_ms,
                prompt_tokens=usage.prompt_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                thinking_tokens=usage.thinking_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
                analyzed_word_count=len(text.split()),
                is_truncated=doc.is_truncated,
                unverified_fragments=unverified,
            )


    if persist and response.analysis_id and response.expires_at:
        analysis_repository.save(
            analysis_id=response.analysis_id,
            source_type=doc.source_type,
            filename=doc.filename,
            extracted_text=doc.raw_text,
            diagnostic_json=response.model_dump_json(),
            expires_at=response.expires_at,
        )

    return response
