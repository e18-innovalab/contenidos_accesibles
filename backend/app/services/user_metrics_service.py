"""
Estadísticas de uso por usuario para el panel /admin (Issue #104).

Salen del historial permanente (tabla user_activity) y de api_users, no de los diagnósticos ni de
los archivos, que vencen: las estadísticas siguen aunque se borre el material. Nunca devuelven
el material, los textos propuestos ni nombres de archivo.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from app.db import user_activity_repository as user_activity
from app.services.admin_metrics_service import RANGES, _bucket_index, _bucket_starts, _parse_utc

# Lo que hace el docente en el producto: cuenta para "acciones" y para el ranking de más activos.
# Las llamadas a la IA, los 429 y las aperturas de sus enlaces (las hace otra persona) van aparte.
PRODUCT_ACTIONS = (
    "analysis", "proposal", "decision", "upload", "export", "download", "share_created", "share_revoked",
    "transformation", "transformation_decision",
)
DECISIONS = ("aceptada", "editada", "descartada", "deshacer")
TRANSFORMATION_DECISIONS = ("aceptada", "editada", "descartada")
SOURCES = user_activity.SOURCES
RANKING_SIZE = 10
RECENT_ACTIVITY = 50
_STAT_KEY = {
    "analysis": "analyses", "proposal": "proposals", "upload": "uploads", "upload_rejected": "uploads_rejected",
    "export": "exports", "download": "downloads", "share_created": "shares_created", "share_opened": "share_opens",
    "share_revoked": "shares_revoked", "ai_call": "ai_calls", "rate_limited": "rate_limited",
    "transformation": "transformations",
}
# Series del gráfico de actividad del detalle (4 colores validados de la paleta categórica)
ACTIVITY_GROUPS = {
    "analysis": "analyses", "proposal": "proposals", "decision": "decisions",
    "upload": "files", "export": "files", "download": "files", "share_created": "files", "share_revoked": "files",
}


def _empty_stats() -> dict:
    return {
        "actions": 0, "analyses": 0, "mock_analyses": 0, "proposals": 0, "mock_proposals": 0,
        "decisions": {d: 0 for d in DECISIONS},
        "uploads": 0, "uploads_rejected": 0, "exports": 0, "downloads": 0,
        "shares_created": 0, "share_opens": 0, "shares_revoked": 0,
        "ai_calls": 0, "ai_errors": 0, "tokens": 0, "rate_limited": 0,
        # Transformar material (Issue #116): pedidas, en modo mock, fallidas y decisiones del docente
        "transformations": 0, "mock_transformations": 0, "transformations_failed": 0,
        "transformation_decisions": {d: 0 for d in TRANSFORMATION_DECISIONS},
    }


def _add(stats: dict, action: str, detail: str | None, n: int = 1, mock: int = 0, tokens: int = 0) -> None:
    """Suma una fila (n=1) o un total agrupado por acción y detalle."""
    if action == "decision":
        if detail in stats["decisions"]:
            stats["decisions"][detail] += n
    elif action == "transformation_decision":
        if detail in stats["transformation_decisions"]:
            stats["transformation_decisions"][detail] += n
    elif action in _STAT_KEY:
        stats[_STAT_KEY[action]] += n
    if action == "analysis":
        stats["mock_analyses"] += mock
    elif action == "proposal":
        stats["mock_proposals"] += mock
    elif action == "transformation":
        stats["mock_transformations"] += mock
        if detail == "failed":
            stats["transformations_failed"] += n
    elif action == "ai_call":
        stats["tokens"] += tokens
        if detail != "ok":
            stats["ai_errors"] += n
    if action in PRODUCT_ACTIONS:
        stats["actions"] += n


def _is_actor(row: dict) -> bool:
    """La fila la generó el propio usuario (una apertura de su enlace la hace otra persona)."""
    return row["action"] != "share_opened"


def _identity(user_id: str, profile: dict | None) -> dict:
    """Nombre para mostrar y origen. En la web de pruebas el usuario va en el id: test-web_<tipo>_<usuario>."""
    source = profile["source"] if profile else user_activity.source_of(user_id)
    name = profile.get("name") if profile else None
    login = None
    if source == "test_web":
        kind, _, username = user_id[len(user_activity.TEST_WEB_PREFIX):].partition("_")
        login = kind or None
        name = name or username or user_id
    elif source == "anon":
        name = "Usuario anónimo"
    return {"name": name, "source": source, "login": login}


def _user_entry(user_id: str, profile: dict | None, all_time: dict, in_range: dict, seen: dict) -> dict:
    first_at, last_at = seen.get(user_id, (None, None))
    return {
        "user_id": user_id,
        **_identity(user_id, profile),
        "email": profile.get("email") if profile else None,
        "avatar_url": profile.get("avatar_url") if profile else None,
        "role": profile["role"] if profile else None,
        "first_seen_at": profile["first_seen_at"] if profile else first_at,
        "last_seen_at": profile["last_seen_at"] if profile else last_at,
        "profile_fetched_at": profile.get("profile_fetched_at") if profile else None,
        "range": in_range,
        "all_time": all_time,
    }


def _window(range_key: str, tz_offset_minutes: int, now: datetime | None = None):
    if range_key not in RANGES:
        raise ValueError(f"Rango inválido. Opciones: {', '.join(RANGES)}.")
    span, unit = RANGES[range_key]
    step = timedelta(hours=1) if unit == "hour" else timedelta(days=1)
    now = now or datetime.now(timezone.utc)
    starts = _bucket_starts(now, span, unit, timedelta(minutes=tz_offset_minutes))
    return starts, step, starts[0], starts[-1] + step


def _stats_by_user(rows: list[dict]) -> dict[str, dict]:
    stats: dict[str, dict] = defaultdict(_empty_stats)
    for r in rows:
        _add(stats[r["user_id"]], r["action"], r["detail"], 1, r["mock"], r["tokens"])
    return stats


def _all_time(totals: list[dict]) -> tuple[dict[str, dict], dict[str, tuple[str, str]]]:
    stats: dict[str, dict] = defaultdict(_empty_stats)
    seen: dict[str, tuple[str, str]] = {}
    for t in totals:
        _add(stats[t["user_id"]], t["action"], t["detail"], t["n"], t["mock"] or 0, t["tokens"] or 0)
        first, last = seen.get(t["user_id"], (t["first_at"], t["last_at"]))
        seen[t["user_id"]] = (min(first, t["first_at"]), max(last, t["last_at"]))
    return stats, seen


def _ranking(users: list[dict], key: str) -> list[dict]:
    ranked = sorted((u for u in users if u["range"][key] > 0), key=lambda u: (-u["range"][key], u["user_id"]))
    return [
        {"user_id": u["user_id"], "name": u["name"], "source": u["source"], "value": u["range"][key]}
        for u in ranked[:RANKING_SIZE]
    ]


def build_users(range_key: str = "24h", tz_offset_minutes: int = 0, now: datetime | None = None) -> dict:
    """Lista de usuarios con sus estadísticas del período e históricas, rankings y actividad."""
    starts, step, start, end = _window(range_key, tz_offset_minutes, now)
    rows = user_activity.list_between(start, end)
    previous = user_activity.list_between(start - (end - start), start)
    profiles = {u["user_id"]: u for u in user_activity.list_users()}
    all_time, seen = _all_time(user_activity.totals_by_user())
    in_range = _stats_by_user(rows)

    users = [
        _user_entry(uid, profiles.get(uid), all_time[uid], in_range[uid], seen)
        for uid in sorted(set(profiles) | set(all_time))
    ]
    users.sort(key=lambda u: u["last_seen_at"] or "", reverse=True)

    n = len(starts)
    active_by_bucket: list[set] = [set() for _ in range(n)]
    actions_by_source = {s: [0] * n for s in SOURCES}
    tokens = [0] * n
    for r in rows:
        i = _bucket_index(_parse_utc(r["created_at"]), starts, step)
        if i is None:
            continue
        if _is_actor(r):
            active_by_bucket[i].add(r["user_id"])
        if r["action"] in PRODUCT_ACTIONS:
            actions_by_source[user_activity.source_of(r["user_id"])][i] += 1
        tokens[i] += r["tokens"]

    def active(rs: list[dict]) -> set:
        return {r["user_id"] for r in rs if _is_actor(r)}

    def count(rs: list[dict], actions=PRODUCT_ACTIONS) -> int:
        return sum(1 for r in rs if r["action"] in actions)

    def new_between(a: datetime, b: datetime) -> int:
        lo, hi = user_activity.to_timestamp(a), user_activity.to_timestamp(b)
        return sum(1 for u in users if u["first_seen_at"] and lo <= u["first_seen_at"] < hi)

    active_now = active(rows)
    return {
        "kpis": {
            "total_users": len(users),
            "active_users": {"value": len(active_now), "previous": len(active(previous)),
                             "spark": [len(b) for b in active_by_bucket]},
            "new_users": {"value": new_between(start, end), "previous": new_between(start - (end - start), start)},
            "actions": {"value": count(rows), "previous": count(previous),
                        "spark": [sum(v[i] for v in actions_by_source.values()) for i in range(n)]},
            "tokens": {"value": sum(r["tokens"] for r in rows), "previous": sum(r["tokens"] for r in previous),
                       "spark": tokens},
            "rate_limited": {"value": count(rows, ("rate_limited",)), "previous": count(previous, ("rate_limited",))},
        },
        "by_source": {
            s: {"users": sum(1 for u in active_now if user_activity.source_of(u) == s),
                "actions": sum(actions_by_source[s])}
            for s in SOURCES
        },
        "activity": {"active_users": [len(b) for b in active_by_bucket], "actions_by_source": actions_by_source},
        "rankings": {"actions": _ranking(users, "actions"), "tokens": _ranking(users, "tokens")},
        "users": users,
    }


def build_user_detail(user_id: str, range_key: str = "24h", tz_offset_minutes: int = 0,
                      now: datetime | None = None) -> dict | None:
    """Detalle de un usuario: actividad, formatos, adaptaciones, transformaciones y últimas acciones. None si no existe."""
    profile = user_activity.get_user(user_id)
    totals = user_activity.totals_by_user(user_id)
    if profile is None and not totals:
        return None
    starts, step, start, end = _window(range_key, tz_offset_minutes, now)
    rows = user_activity.list_between(start, end, user_id)
    all_time, seen = _all_time(totals)

    n = len(starts)
    activity = {g: [0] * n for g in dict.fromkeys(ACTIVITY_GROUPS.values())}
    tokens = [0] * n
    formats = {k: Counter() for k in ("analysis", "upload", "export")}
    adaptations: dict[str, Counter] = defaultdict(Counter)
    transformations: dict[str, Counter] = defaultdict(Counter)
    models: dict[tuple[str, str], dict] = {}
    for r in rows:
        i = _bucket_index(_parse_utc(r["created_at"]), starts, step)
        if i is not None:
            if r["action"] in ACTIVITY_GROUPS:
                activity[ACTIVITY_GROUPS[r["action"]]][i] += 1
            tokens[i] += r["tokens"]
        if r["action"] in formats and r["format"]:
            formats[r["action"]][r["format"]] += 1
        if r["action"] in ("proposal", "decision") and r["adaptation_type"]:
            adaptations[r["adaptation_type"]]["propuestas" if r["action"] == "proposal" else r["detail"]] += 1
        if r["action"] in ("transformation", "transformation_decision") and r["format"]:
            if r["action"] == "transformation":
                transformations[r["format"]]["pedidas"] += 1
                transformations[r["format"]]["fallidas"] += r["detail"] == "failed"
            else:
                transformations[r["format"]][r["detail"]] += 1
        if r["action"] == "ai_call":
            m = models.setdefault((r["provider"], r["model"]), {"provider": r["provider"], "model": r["model"],
                                                               "calls": 0, "errors": 0, "tokens": 0})
            m["calls"] += 1
            m["tokens"] += r["tokens"]
            m["errors"] += r["detail"] != "ok"

    recent = [
        {k: r[k] for k in ("created_at", "action", "format", "detail", "adaptation_type", "mock", "size_bytes",
                           "score", "barriers", "provider", "model", "latency_ms", "tokens")}
        for r in user_activity.list_recent(user_id, RECENT_ACTIVITY)
    ]
    return {
        "user": _user_entry(user_id, profile, all_time[user_id], _stats_by_user(rows)[user_id], seen),
        "range": range_key,
        "buckets": [s.strftime("%Y-%m-%dT%H:%M:%SZ") for s in starts],
        "unit": RANGES[range_key][1],
        "activity": activity,
        "tokens": tokens,
        "formats": {k: dict(v.most_common()) for k, v in formats.items()},
        "adaptations": {t: dict(c) for t, c in sorted(adaptations.items())},
        "transformations": {f: dict(c) for f, c in sorted(transformations.items())},
        "models": sorted(models.values(), key=lambda m: -m["tokens"]),
        "recent": recent,
    }
