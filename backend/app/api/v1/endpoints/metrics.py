"""Endpoint de métricas personales del docente (sin exponer modelo ni proveedor de IA)."""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.core.owner import current_owner
from app.core.teacher_auth import require_permission
from app.schemas.metrics import UserActivityStats, UserMetricsResponse, UserRecentEvent
from app.services import user_metrics_service

router = APIRouter()

_RECENT_SAFE_KEYS = (
    "created_at",
    "action",
    "format",
    "detail",
    "adaptation_type",
    "mock",
    "size_bytes",
    "score",
    "barriers",
    "latency_ms",
    "tokens",
)


def _safe_stats(raw: dict | None) -> UserActivityStats:
    if not raw:
        return UserActivityStats()
    return UserActivityStats(**{k: raw[k] for k in UserActivityStats.model_fields if k in raw})


@router.get(
    "",
    response_model=UserMetricsResponse,
    dependencies=[Depends(require_permission("analysis:create"))],
    summary="Consultar métricas de uso del usuario autenticado",
)
def get_my_metrics(
    range: Literal["24h", "7d", "30d"] = Query(default="7d", description="Ventana de tiempo: 24h, 7d o 30d."),
    tz_offset: int = Query(default=0, ge=-720, le=840, description="Desfase horario en minutos respecto a UTC."),
    owner: str = Depends(current_owner),
) -> UserMetricsResponse:
    """
    Devuelve métricas de actividad, diagnósticos, adaptaciones, transformaciones,
    archivos y consumo de tokens del usuario actual. Nunca expone el proveedor
    ni el modelo de IA utilizado.
    """
    detail = user_metrics_service.build_user_detail(owner, range_key=range, tz_offset_minutes=tz_offset)
    if detail is None:
        starts, _step, _start, _end = user_metrics_service._window(range, tz_offset)
        n = len(starts)
        return UserMetricsResponse(
            range=range,
            unit=user_metrics_service.RANGES[range][1],
            buckets=[s.strftime("%Y-%m-%dT%H:%M:%SZ") for s in starts],
            tokens=[0] * n,
            activity={g: [0] * n for g in dict.fromkeys(user_metrics_service.ACTIVITY_GROUPS.values())},
            formats={"analysis": {}, "upload": {}, "export": {}},
        )

    user_summary = detail.get("user") or {}
    recent = [
        UserRecentEvent(**{k: ev.get(k) for k in _RECENT_SAFE_KEYS})
        for ev in detail.get("recent", [])
    ]
    return UserMetricsResponse(
        range=detail["range"],
        unit=detail["unit"],
        buckets=detail["buckets"],
        tokens=detail["tokens"],
        activity=detail["activity"],
        in_range=_safe_stats(user_summary.get("range")),
        all_time=_safe_stats(user_summary.get("all_time")),
        formats=detail.get("formats", {}),
        adaptations=detail.get("adaptations", {}),
        transformations=detail.get("transformations", {}),
        recent=recent,
    )
