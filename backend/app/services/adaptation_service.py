"""
Propuestas de adaptación con IA (Issue #27).

Después del diagnóstico, el docente elige una barrera y un tipo de adaptación; el
servicio devuelve original + propuesta + explicación. Las propuestas nunca se
aplican solas: se guardan como 'pendiente' hasta que el docente decide.
"""

import logging
import re
import uuid
from datetime import datetime, timezone

from app.db import adaptation_repository, analysis_repository
from app.schemas.adaptation import (
    AdaptationAIOutput,
    AdaptationMetadata,
    AdaptationProposal,
    AdaptationRequest,
    AdaptationType,
    DecisionLogEntry,
    DecisionRequest,
)
from app.schemas.analysis import AccessibilityAnalysisResponse, BarrierReport
from app.services.accessibility_service import _fragment_parts, _normalize
from app.services.llm.base import LLMInvalidResponseError
from app.services.llm_service import llm_service
from app.services.rules_service import split_paragraphs, split_sentences

logger = logging.getLogger(__name__)

CONTEXT_CHARS = 600  # caracteres de cada párrafo vecino que se envían como contexto

_TYPE_INSTRUCTIONS: dict[str, str] = {
    "lenguaje_claro": (
        "Reescribí el fragmento en lenguaje claro: oraciones breves (idealmente menos de 20 palabras), "
        "una idea por oración, voz activa, verbos en lugar de nominalizaciones, vocabulario frecuente y "
        "referencias explícitas en lugar de 'esto' o 'lo anterior'. Desarrollá las siglas la primera vez."
    ),
    "consigna_en_pasos": (
        "Dividí la consigna en pasos numerados ('1.', '2.', ...), con una sola acción por paso, empezando "
        "por el verbo y en el orden en que el estudiante debe hacerlas. Si el original indica el producto "
        "esperado, la forma o el plazo de entrega, dejalo en un paso final explícito."
    ),
    "reorganizar": (
        "Reorganizá el contenido extenso en bloques breves de 2 a 4 oraciones separados por una línea en "
        "blanco, cada uno con una idea central. Ordená las ideas de lo general a lo particular y pasá a "
        "lista con '- ' las enumeraciones que estén dentro de una oración. No resumas: conservá toda la información."
    ),
    "mejorar_estructura": (
        "Mejorá la estructura del fragmento: agregá un título breve en un renglón propio por cada bloque "
        "temático, convertí enumeraciones en listas ('- ' o '1.') y separá los bloques con una línea en "
        "blanco. Mantené la redacción original salvo los cambios mínimos que pida la nueva estructura."
    ),
}

SYSTEM_PROMPT = """
Sos un especialista en accesibilidad de materiales educativos, Diseño Universal para el
Aprendizaje (DUA) y lenguaje claro. Un docente de nivel secundario o superior te pide adaptar
un fragmento de su material para reducir una barrera de acceso ya diagnosticada.

## Reglas obligatorias
- Conservá el objetivo pedagógico: la misma tarea, el mismo contenido disciplinar y el mismo
  nivel de exigencia. No agregues ni quites actividades, preguntas, datos ni criterios de
  evaluación. No resuelvas la consigna ni des pistas de la respuesta.
- Mantené la terminología técnica propia de la disciplina. Si un término puede trabar la
  lectura, agregá una aclaración breve entre paréntesis la primera vez que aparece.
- Respetá el registro del original: si usa voseo ("leé", "resolvé"), mantené el voseo.
- No inventes referencias (páginas, autores, fechas, materiales) que no estén en el original.
- Adaptá solo el fragmento. El contexto sirve para entenderlo y no se reescribe.
- Formato de `proposed_text`: texto plano con saltos de línea. Numerá con "1.", viñetas con
  "- " y títulos en un renglón propio. No uses Markdown (#, **, _).
- Redactá `explanation` y `preserved_objective` en español claro y respetuoso hacia el docente.
""".strip()


class AdaptationNotFoundError(LookupError):
    """No existe (o venció) el diagnóstico, la barrera o la propuesta pedida."""


class FragmentRequiredError(ValueError):
    """La barrera no cita un fragmento textual y el docente no envió uno."""


class ProposalStateError(ValueError):
    """La operación no corresponde al estado actual de la propuesta (ej. decidir dos veces)."""


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_analysis(analysis_id: str) -> tuple[AccessibilityAnalysisResponse, str]:
    """Devuelve el diagnóstico vigente y su texto extraído. Uno vencido se borra al consultarlo."""
    record = analysis_repository.get(analysis_id)
    if not record:
        raise AdaptationNotFoundError("Diagnóstico no encontrado")
    if record["expires_at"] < _now_utc_iso():
        analysis_repository.delete(analysis_id)
        raise AdaptationNotFoundError("El diagnóstico ha expirado")
    analysis = AccessibilityAnalysisResponse.model_validate_json(record["diagnostic_json"])
    return analysis, record["extracted_text"]


def _is_placeholder(fragment: str) -> bool:
    """Las reglas globales citan '[...]' en vez de un fragmento (ej. '[Documento completo: x.pdf]')."""
    fragment = fragment.strip()
    return fragment.startswith("[") and fragment.endswith("]")


def resolve_fragment(
    barrier: BarrierReport, extracted_text: str, adaptation_type: AdaptationType
) -> tuple[str, list[str]]:
    """
    Devuelve el texto completo a adaptar a partir de la cita de la barrera.

    Las reglas citan los párrafos y consignas largas recortados con '…', y la IA a veces
    abrevia con '...': se recupera del material el párrafo completo que contiene la cita
    (o la oración, si se pide dividir una consigna en pasos).
    """
    original = barrier.original_text.strip()
    if _is_placeholder(original):
        raise FragmentRequiredError(
            f"La barrera '{barrier.id}' es una evaluación global y no cita un fragmento del material: "
            "enviá en 'fragment' el texto que querés adaptar."
        )

    warnings: list[str] = []
    if barrier.fragment_found is False:
        warnings.append(
            "El fragmento citado por la barrera no coincide textualmente con el material: "
            "revisá que la propuesta corresponda al texto que querés adaptar."
        )

    if not re.search(r"\.{3}|…", original):
        return original, warnings

    parts = _fragment_parts(original)
    for paragraph in split_paragraphs(extracted_text):
        if all(p in _normalize(paragraph) for p in parts):
            if adaptation_type == "consigna_en_pasos":
                for sentence in split_sentences(paragraph):
                    if all(p in _normalize(sentence) for p in parts):
                        return sentence, warnings
            return paragraph.strip(), warnings

    warnings.append(
        "No se encontró en el material el texto completo de la cita recortada: se adaptó la cita tal como figura."
    )
    return original, warnings


def _context_around(fragment: str, extracted_text: str) -> str:
    """Párrafos anterior y siguiente al fragmento, recortados, para que la IA entienda el sentido."""
    paragraphs = [p.strip() for p in split_paragraphs(extracted_text) if p.strip()]
    parts = _fragment_parts(fragment)
    if not parts:
        return ""
    for idx, paragraph in enumerate(paragraphs):
        if parts[0] in _normalize(paragraph):
            neighbors = []
            if idx > 0:
                neighbors.append(paragraphs[idx - 1][-CONTEXT_CHARS:])
            if idx + 1 < len(paragraphs):
                neighbors.append(paragraphs[idx + 1][:CONTEXT_CHARS])
            return "\n[...]\n".join(neighbors)
    return ""


def _build_user_prompt(
    barrier: BarrierReport, fragment: str, context: str, adaptation_type: AdaptationType
) -> str:
    context_block = f"Contexto cercano (no lo adaptes):\n<<<\n{context}\n>>>\n\n" if context else ""
    return (
        f"Tipo de adaptación: {adaptation_type}\n"
        f"Instrucciones: {_TYPE_INSTRUCTIONS[adaptation_type]}\n\n"
        f"Barrera detectada: {barrier.issue}\n"
        f"Por qué es una barrera: {barrier.explanation}\n"
        f"Recomendación del diagnóstico: {barrier.recommendation}\n\n"
        f"{context_block}"
        f"Fragmento a adaptar:\n<<<\n{fragment}\n>>>"
    )


# --- Modo mock ---------------------------------------------------------------

_ACTION_SPLIT_RE = re.compile(r",\s*(?:y\s+|e\s+)?|;\s*|\s+y\s+(?=\w+[éáí]\b)")


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _mock_output(fragment: str, adaptation_type: AdaptationType) -> AdaptationAIOutput:
    """Transformaciones determinísticas (0 tokens) que respetan el formato de cada tipo."""
    sentences = split_sentences(fragment) or [fragment]

    if adaptation_type == "consigna_en_pasos":
        actions = []
        for sentence in sentences:
            actions += [a.strip(" .") for a in _ACTION_SPLIT_RE.split(sentence) if a.strip(" .")]
        proposed = "\n".join(f"{i}. {_capitalize(a)}." for i, a in enumerate(actions, start=1))
    elif adaptation_type == "lenguaje_claro":
        clauses = [c.strip(" .") for s in sentences for c in re.split(r",\s+", s) if c.strip(" .")]
        proposed = " ".join(f"{_capitalize(c)}." for c in clauses)
    elif adaptation_type == "reorganizar":
        blocks = [" ".join(sentences[i:i + 3]) for i in range(0, len(sentences), 3)]
        proposed = "\n\n".join(blocks)
    else:  # mejorar_estructura
        proposed = "Título sugerido\n" + "\n".join(f"- {s}" for s in sentences)

    return AdaptationAIOutput(
        proposed_text=proposed,
        explanation=f"[MOCK] Propuesta simulada de tipo '{adaptation_type}' para pruebas de Frontend.",
        preserved_objective="[MOCK] Se conserva la misma tarea y el mismo contenido del fragmento original.",
    )


# --- Punto de entrada ----------------------------------------------------------


async def create_proposal(request: AdaptationRequest, *, mock: bool = False) -> AdaptationProposal:
    analysis, extracted_text = load_analysis(request.analysis_id)
    barrier = next((b for b in analysis.barriers if b.id == request.barrier_id), None)
    if barrier is None:
        raise AdaptationNotFoundError(
            f"La barrera '{request.barrier_id}' no existe en el diagnóstico '{request.analysis_id}'."
        )

    if request.fragment:
        fragment, warnings = request.fragment.strip(), []
    else:
        fragment, warnings = resolve_fragment(barrier, extracted_text, request.adaptation_type)

    if mock:
        output = _mock_output(fragment, request.adaptation_type)
        warnings.append("Propuesta generada en modo simulación (?mock=true). No se consumieron tokens de IA.")
        metadata = AdaptationMetadata(
            provider="mock",
            model="mock-adaptation-v1",
            connection="Simulador Frontend (?mock=true)",
            latency_ms=1,
            prompt_tokens=0,
            output_tokens=0,
            thinking_tokens=0,
            total_tokens=0,
        )
    else:
        result = await llm_service.generate_structured(
            system_instruction=SYSTEM_PROMPT,
            contents=_build_user_prompt(
                barrier, fragment, _context_around(fragment, extracted_text), request.adaptation_type
            ),
            schema=AdaptationAIOutput,
            temperature=0.3,
        )
        output = result.parsed
        if not output.proposed_text.strip():
            raise LLMInvalidResponseError("El modelo devolvió una propuesta vacía.")
        usage = result.usage
        metadata = AdaptationMetadata(
            provider=result.provider,
            model=result.model,
            connection=result.connection_label,
            latency_ms=result.latency_ms,
            prompt_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            thinking_tokens=usage.thinking_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
        )

    if _normalize(output.proposed_text) == _normalize(fragment):
        warnings.append("La propuesta es igual al fragmento original: probá con otro tipo de adaptación.")

    proposal = AdaptationProposal(
        proposal_id=str(uuid.uuid4()),
        analysis_id=request.analysis_id,
        barrier_id=barrier.id,
        adaptation_type=request.adaptation_type,
        original_text=fragment,
        fragment_source="request" if request.fragment else "barrier",
        proposed_text=output.proposed_text.strip(),
        explanation=output.explanation,
        preserved_objective=output.preserved_objective,
        warnings=warnings,
        created_at=_now_utc_iso(),
        # La propuesta no puede sobrevivir al diagnóstico ni al texto original que adapta.
        expires_at=analysis.expires_at or _now_utc_iso(),
        metadata=metadata,
    )
    adaptation_repository.save(
        proposal_id=proposal.proposal_id,
        analysis_id=proposal.analysis_id,
        barrier_id=proposal.barrier_id,
        status=proposal.status,
        proposal_json=proposal.model_dump_json(),
        created_at=proposal.created_at,
        expires_at=proposal.expires_at,
    )
    return proposal


def get_proposal(proposal_id: str) -> AdaptationProposal:
    record = adaptation_repository.get(proposal_id)
    if not record or record["expires_at"] < _now_utc_iso():
        raise AdaptationNotFoundError("Propuesta no encontrada o vencida")
    return AdaptationProposal.model_validate_json(record["proposal_json"])


def list_proposals(analysis_id: str) -> list[AdaptationProposal]:
    load_analysis(analysis_id)  # 404 si el diagnóstico no existe o venció
    return [
        AdaptationProposal.model_validate_json(r["proposal_json"])
        for r in adaptation_repository.list_by_analysis(analysis_id)
    ]


# --- Revisión docente (Issue #29) ---------------------------------------------------


def _apply_transition(
    proposal: AdaptationProposal,
    *,
    action: str,
    to_status: str,
    edited_text: str | None,
    final_text: str | None,
) -> AdaptationProposal:
    """Persiste el nuevo estado y su entrada en el registro. original_text nunca se toca."""
    now = _now_utc_iso()
    updated = proposal.model_copy(update={
        "status": to_status,
        "edited_text": edited_text,
        "final_text": final_text,
        "decided_at": now if to_status != "pendiente" else None,
    })
    applied = adaptation_repository.transition(
        proposal.proposal_id,
        from_status=proposal.status,
        to_status=to_status,
        proposal_json=updated.model_dump_json(),
        log_entry={
            "proposal_id": proposal.proposal_id,
            "analysis_id": proposal.analysis_id,
            "barrier_id": proposal.barrier_id,
            "adaptation_type": proposal.adaptation_type,
            "action": action,
            "from_status": proposal.status,
            "to_status": to_status,
            "edited_text": edited_text,
            "created_at": now,
            "expires_at": proposal.expires_at,
        },
    )
    if not applied:
        raise ProposalStateError("La propuesta cambió de estado mientras se procesaba la decisión: volvé a consultarla.")
    return updated


def decide(proposal_id: str, request: DecisionRequest) -> AdaptationProposal:
    """Registra la decisión del docente sobre una propuesta pendiente."""
    proposal = get_proposal(proposal_id)
    if proposal.status != "pendiente":
        raise ProposalStateError(
            f"La propuesta ya fue {proposal.status}: deshacé esa decisión antes de tomar otra."
        )
    final_text = {
        "aceptada": proposal.proposed_text,
        "editada": request.edited_text.strip() if request.edited_text else None,
        "descartada": None,
    }[request.decision]
    return _apply_transition(
        proposal,
        action="decision",
        to_status=request.decision,
        edited_text=final_text if request.decision == "editada" else None,
        final_text=final_text,
    )


def undo(proposal_id: str) -> AdaptationProposal:
    """Revierte la decisión vigente: la propuesta vuelve a 'pendiente'."""
    proposal = get_proposal(proposal_id)
    if proposal.status == "pendiente":
        raise ProposalStateError("La propuesta está pendiente: no hay ninguna decisión para deshacer.")
    return _apply_transition(proposal, action="deshacer", to_status="pendiente", edited_text=None, final_text=None)


def list_decisions(analysis_id: str) -> list[DecisionLogEntry]:
    load_analysis(analysis_id)  # 404 si el diagnóstico no existe o venció
    return [DecisionLogEntry(**r) for r in adaptation_repository.list_decisions(analysis_id)]
