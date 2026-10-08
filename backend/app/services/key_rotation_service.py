from datetime import datetime, timezone

from app.core.config import settings
from app.db import api_key_repository as repo
from app.services.llm.base import AIConnection, Usage
from app.services.llm.providers import PRESETS_BY_ID, supports_vision

NEAR_LIMIT_RATIO = 0.8

# Cooldowns en memoria por id de conexión, fijados cuando el proveedor responde
# 429 real (o sigue fallando tras los reintentos). Cubren lo que los contadores
# locales no ven (requests fallidas que el proveedor igual contabiliza, o varias
# keys del mismo proyecto compartiendo cuota). Se pierden al reiniciar: en ese
# caso basta un 429 más para volver a fijarlos.
_cooldowns: dict[int, datetime] = {}


class AIConnectionError(Exception):
    pass


class NoApiKeyConfiguredError(AIConnectionError, ValueError):
    """Sin ninguna conexión habilitada. Subclase de ValueError para no romper
    el manejo de errores ya existente en los endpoints (400)."""


class NoVisionConnectionError(AIConnectionError):
    """No hay ninguna conexión habilitada que soporte visión/multimodalidad."""


class AllKeysExhaustedError(AIConnectionError):
    """Todas las conexiones alcanzaron su umbral o están en cooldown (429)."""



def _threshold_pairs(row: dict) -> list[tuple[int | None, int]]:
    """(umbral, contador_actual) para cada una de las 4 dimensiones:
    RPM/TPM (ventana de minuto) y RPD/TPD (ventana diaria)."""
    return [
        (row["rpm_threshold"], row["minute_request_count"]),
        (row["tpm_threshold"], row["minute_token_count"]),
        (row["rpd_threshold"], row["request_count"]),
        (row["tpd_threshold"], row["total_token_count"]),
    ]


def _in_cooldown(key_id: int) -> bool:
    until = _cooldowns.get(key_id)
    if until is None:
        return False
    if datetime.now(timezone.utc) >= until:
        del _cooldowns[key_id]
        return False
    return True


def _is_exhausted(row: dict) -> bool:
    return _in_cooldown(row["id"]) or any(
        threshold is not None and count >= threshold
        for threshold, count in _threshold_pairs(row)
    )


def _usage_ratio(row: dict) -> float:
    ratios = [count / threshold for threshold, count in _threshold_pairs(row) if threshold]
    return max(ratios) if ratios else 0.0


def get_status_label(row: dict) -> str:
    if not row["enabled"]:
        return "disabled"
    if _is_exhausted(row):
        return "exhausted"
    near = _usage_ratio(row) >= NEAR_LIMIT_RATIO
    if row["is_current"]:
        return "near-limit" if near else "active"
    return "near-limit" if near else "standby"


def _to_connection(row: dict) -> AIConnection:
    extra = repo.parse_extra_params(row)
    return AIConnection(
        id=row["id"],
        label=row["label"],
        provider=row["provider"],
        base_url=row["base_url"] or None,
        model=row["model"],
        api_key=repo.decrypt_raw_key(row),
        extra_params=extra,
        supports_vision=supports_vision(row["provider"], row["model"], extra),
    )


def get_active_connection(require_vision: bool = False) -> AIConnection:
    """
    Devuelve la conexión de mayor prioridad (menor número) que no esté agotada
    ni en cooldown. Así, cuando la principal se recupera, se vuelve a usar.
    Si require_vision=True, filtra sólo aquellas con capacidades multimodales.
    """
    rows = [repo.apply_resets_if_needed(r) for r in repo.list_all_enabled_ordered_by_priority()]
    if not rows:
        raise NoApiKeyConfiguredError(
            "No hay ninguna conexión de IA habilitada. Agregá una desde /admin."
        )

    if require_vision:
        rows = [
            r for r in rows
            if supports_vision(r["provider"], r["model"], repo.parse_extra_params(r))
        ]
        if not rows:
            raise NoVisionConnectionError(
                "No hay ninguna conexión de IA con soporte de visión/multimodalidad configurada y habilitada."
            )

    chosen = next((r for r in rows if not _is_exhausted(r)), None)
    if chosen is None:
        raise AllKeysExhaustedError(
            "Todas las conexiones de IA alcanzaron su límite o están temporalmente "
            "bloqueadas por el proveedor. Los límites por minuto se liberan en el próximo "
            "minuto y los diarios al día siguiente. También podés agregar o ajustar una "
            "conexión desde /admin."
        )
    if not chosen["is_current"]:
        repo.set_current(chosen["id"])
    return _to_connection(chosen)



def record_usage(key_id: int, usage: Usage | None) -> None:
    repo.record_usage(
        key_id,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        candidates_tokens=usage.output_tokens if usage else 0,
        total_tokens=usage.total_tokens if usage else 0,
    )
    try:
        # Re-chequeo proactivo: si esta llamada agotó la conexión, el puntero
        # "activa" ya queda actualizado sin esperar la próxima request real.
        get_active_connection()
    except (AllKeysExhaustedError, NoApiKeyConfiguredError):
        pass


def record_failed_request(key_id: int) -> None:
    """Request que el proveedor recibió pero falló (p. ej. 503): suele contar para
    su cuota aunque no devuelva uso de tokens, así que se registra con 0 tokens."""
    repo.record_usage(key_id, prompt_tokens=0, candidates_tokens=0, total_tokens=0)


def mark_rate_limited(key_id: int, until: datetime) -> None:
    """Deja la conexión fuera de rotación hasta `until` (UTC)."""
    _cooldowns[key_id] = until


def list_status_for_dashboard() -> list[dict]:
    rows = [repo.apply_resets_if_needed(r) for r in repo.list_all_ordered_by_priority()]
    return [
        {
            "id": r["id"],
            "label": r["label"],
            "provider": r["provider"],
            "base_url": r["base_url"] or "",
            "model": r["model"],
            "priority": r["priority"],
            "extra_params": r["extra_params"],
            "managed_by_env": bool(r["managed_by_env"]),
            "masked_key": repo.mask(r),
            "status": get_status_label(r),
            "enabled": bool(r["enabled"]),
            "minute_request_count": r["minute_request_count"],
            "rpm_threshold": r["rpm_threshold"],
            "minute_token_count": r["minute_token_count"],
            "tpm_threshold": r["tpm_threshold"],
            "request_count": r["request_count"],
            "rpd_threshold": r["rpd_threshold"],
            "total_token_count": r["total_token_count"],
            "tpd_threshold": r["tpd_threshold"],
            "usage_pct": round(_usage_ratio(r) * 100, 1),
        }
        for r in rows
    ]


# Prioridad de la conexión de .env: por delante de las creadas desde /admin (100 por defecto).
ENV_CONNECTION_PRIORITY = 0


def sync_env_connection() -> None:
    """
    Garantiza que la conexión principal definida en .env (AI_API_KEY, AI_PROVIDER,
    AI_MODEL, AI_CONNECTION_LABEL) exista, esté habilitada y tenga la prioridad más
    alta. Se ejecuta en cada arranque: cambios o borrados hechos desde /admin sobre
    esta conexión se revierten. Sin AI_API_KEY no hace nada.
    """
    key = settings.AI_API_KEY
    raw = key.get_secret_value().strip() if key else ""
    if not raw:
        return
    preset = PRESETS_BY_ID.get(settings.AI_PROVIDER)
    if preset is None:
        raise ValueError(
            f"AI_PROVIDER={settings.AI_PROVIDER!r} no existe. "
            f"Opciones: {', '.join(PRESETS_BY_ID)}."
        )
    fields = dict(
        label=settings.AI_CONNECTION_LABEL,
        raw_key=raw,
        provider=preset.id,
        base_url=preset.base_url,
        model=settings.AI_MODEL,
        priority=ENV_CONNECTION_PRIORITY,
    )
    existing = repo.get_env_managed()
    if existing is not None:
        repo.sync_env_managed(existing["id"], **fields)
        return
    repo.create(
        **fields,
        extra_params=dict(preset.extra_params),
        rpm_threshold=preset.rpm,
        tpm_threshold=preset.tpm,
        rpd_threshold=preset.rpd,
        tpd_threshold=preset.tpd,
        managed_by_env=True,
    )
