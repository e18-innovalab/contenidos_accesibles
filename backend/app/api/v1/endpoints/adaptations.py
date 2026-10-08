from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.core.rate_limit import limit_ai_usage
from app.db import adaptation_repository
from app.schemas.adaptation import (
    AdaptationProposal,
    AdaptationRequest,
    DecisionLogEntry,
    DecisionRequest,
)
from app.services import adaptation_service
from app.services.adaptation_service import (
    AdaptationNotFoundError,
    FragmentRequiredError,
    ProposalStateError,
)
from app.services.key_rotation_service import AllKeysExhaustedError
from app.services.llm.base import LLMInvalidResponseError, LLMUnavailableError

router = APIRouter()


@router.post(
    "",
    response_model=AdaptationProposal,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer una adaptación con IA para una barrera del diagnóstico",
    response_description="Original + propuesta + explicación del cambio, en estado 'pendiente'",
    dependencies=[Depends(limit_ai_usage)],
)
async def create_adaptation(
    payload: AdaptationRequest,
    background_tasks: BackgroundTasks,
    mock: bool = Query(
        default=False,
        description="Si es True, genera una propuesta simulada determinística (0 tokens), ideal para Frontend.",
    ),
):
    """
    ## Adaptaciones con IA (Issue #27)

    Después del diagnóstico, el docente elige una barrera (`barrier_id` del diagnóstico
    `analysis_id`) y un tipo de adaptación:

    | `adaptation_type` | Qué hace |
    |---|---|
    | `lenguaje_claro` | Oraciones breves, voz activa y vocabulario frecuente |
    | `consigna_en_pasos` | Pasos numerados con una acción cada uno |
    | `reorganizar` | Contenido extenso en bloques breves de una idea |
    | `mejorar_estructura` | Títulos, listas y jerarquía |

    - **Fragmento**: por defecto se adapta el texto que cita la barrera. Si la regla lo citó
      recortado (`…`), se recupera del material el párrafo completo (o la oración, para
      `consigna_en_pasos`). Con `fragment` el docente puede enviar el texto exacto; es
      obligatorio para barreras globales que no citan texto (responde `422` si falta).
    - **Objetivo pedagógico**: el prompt prohíbe cambiar la tarea, el contenido o la exigencia;
      la IA informa en `preserved_objective` qué objetivo conserva.
    - **Nunca se aplica sola**: la propuesta se guarda en estado `pendiente` y vence junto con
      su diagnóstico (`expires_at`).
    - **Modo Mock (`?mock=true`)**: misma respuesta y mismos errores, sin consumir IA.
    """
    try:
        proposal = await adaptation_service.create_proposal(payload, mock=mock)
        background_tasks.add_task(adaptation_repository.delete_expired)
        return proposal
    except AdaptationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FragmentRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except AllKeysExhaustedError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except LLMInvalidResponseError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except LLMUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al comunicar con el proveedor de IA: {str(e)}",
        )


@router.get(
    "",
    response_model=list[AdaptationProposal],
    summary="Listar las propuestas de adaptación de un diagnóstico",
)
async def list_adaptations(
    analysis_id: str = Query(description="ID del diagnóstico cuyas propuestas se quieren listar."),
):
    """Propuestas generadas para un diagnóstico, de la más antigua a la más reciente."""
    try:
        return adaptation_service.list_proposals(analysis_id)
    except AdaptationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/decisions",
    response_model=list[DecisionLogEntry],
    summary="Registro de decisiones docentes de un diagnóstico (para el informe)",
)
async def list_decisions(
    analysis_id: str = Query(description="ID del diagnóstico cuyo registro de modificaciones se quiere obtener."),
):
    """
    Historial cronológico de decisiones y deshaceres sobre las propuestas del diagnóstico.
    Cada entrada indica el estado anterior y el nuevo, y el texto del docente cuando editó.
    """
    try:
        return adaptation_service.list_decisions(analysis_id)
    except AdaptationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{proposal_id}",
    response_model=AdaptationProposal,
    summary="Recuperar una propuesta de adaptación por ID",
)
async def get_adaptation(proposal_id: str):
    try:
        return adaptation_service.get_proposal(proposal_id)
    except AdaptationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{proposal_id}/decision",
    response_model=AdaptationProposal,
    summary="Aceptar, editar o descartar una propuesta",
)
async def decide_adaptation(proposal_id: str, payload: DecisionRequest):
    """
    ## Revisión docente (Issue #29)

    El docente decide cada propuesta `pendiente` por separado; ninguna se aplica sola.

    - `aceptada`: `final_text` pasa a ser la propuesta de la IA.
    - `editada`: requiere `edited_text`, que pasa a ser `final_text`.
    - `descartada`: `final_text` queda en `null`.

    `original_text` nunca se modifica. Una propuesta ya decidida responde `409`:
    para cambiar de opinión, primero hay que deshacer la decisión.
    """
    try:
        return adaptation_service.decide(proposal_id, payload)
    except AdaptationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ProposalStateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/{proposal_id}/undo",
    response_model=AdaptationProposal,
    summary="Deshacer la decisión sobre una propuesta",
)
async def undo_adaptation(proposal_id: str):
    """Revierte la decisión vigente: la propuesta vuelve a `pendiente`. Si ya estaba pendiente, `409`."""
    try:
        return adaptation_service.undo(proposal_id)
    except AdaptationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ProposalStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
