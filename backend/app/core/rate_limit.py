"""
Rate limit en memoria para los endpoints que consumen IA real.

El repo es público y la API no tiene autenticación: sin este límite, cualquiera
podría agotar la cuota diaria de los proveedores llamando en loop. Se aplican
ventanas deslizantes de 1 minuto y 24 horas, por IP y globales:

- Por IP: reparte la cuota entre quienes usan la API.
- Global: protege la cuota aunque se falsee la IP (detrás del proxy de Railway
  la IP sale de X-Forwarded-For, que el cliente puede manipular).

Las llamadas con ?mock=true no consumen IA y no cuentan. El estado vive en
memoria: alcanza con una sola réplica (railway.json) y se reinicia con el
proceso. La dependencia es async, así que corre en el event loop y no necesita
locks.
"""
import math
import time
from collections import deque

from fastapi import HTTPException, Request, status

from app.core.config import settings

_MINUTE = 60
_DAY = 24 * 60 * 60
_GLOBAL_KEY = "*"
# Mismos valores verdaderos que acepta Pydantic al parsear el query param `mock`
_TRUTHY = {"1", "true", "t", "yes", "y", "on"}

# Marcas de tiempo de las llamadas aceptadas en las últimas 24 h, por clave (IP o global)
_hits: dict[str, deque[float]] = {}


def _now() -> float:
    return time.monotonic()


def reset() -> None:
    """Vacía los contadores (para tests)."""
    _hits.clear()


def _retry_after(key: str, per_minute: int, per_day: int, now: float) -> float | None:
    """Segundos a esperar si `key` superó algún límite; None si puede pasar. 0 = sin límite."""
    hits = _hits.get(key)
    if hits is None:
        return None
    while hits and hits[0] <= now - _DAY:
        hits.popleft()
    if not hits:
        del _hits[key]
        return None

    waits = []
    if per_day > 0 and len(hits) >= per_day:
        waits.append(hits[-per_day] + _DAY - now)
    if per_minute > 0:
        recent = [t for t in hits if t > now - _MINUTE]
        if len(recent) >= per_minute:
            waits.append(recent[-per_minute] + _MINUTE - now)
    return max(waits) if waits else None


def _reject(detail: str, wait: float) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(max(1, math.ceil(wait)))},
    )


async def limit_ai_usage(request: Request) -> None:
    """Dependencia para los endpoints de IA: responde 429 con Retry-After al superar el límite."""
    if request.query_params.get("mock", "").lower() in _TRUTHY:
        return

    now = _now()
    ip = request.client.host if request.client else "desconocida"

    wait = _retry_after(
        ip, settings.AI_RATE_LIMIT_PER_IP_MINUTE, settings.AI_RATE_LIMIT_PER_IP_DAY, now
    )
    if wait is not None:
        raise _reject(
            f"Demasiadas solicitudes de IA desde esta IP. Probá de nuevo en "
            f"{max(1, math.ceil(wait))} s (o usá ?mock=true para probar sin IA).",
            wait,
        )

    wait = _retry_after(
        _GLOBAL_KEY, settings.AI_RATE_LIMIT_GLOBAL_MINUTE, settings.AI_RATE_LIMIT_GLOBAL_DAY, now
    )
    if wait is not None:
        raise _reject(
            f"El servicio alcanzó su límite de uso de IA. Probá de nuevo en "
            f"{max(1, math.ceil(wait))} s (o usá ?mock=true para probar sin IA).",
            wait,
        )

    for key in (ip, _GLOBAL_KEY):
        _hits.setdefault(key, deque()).append(now)
