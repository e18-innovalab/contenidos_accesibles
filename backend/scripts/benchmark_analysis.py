"""
Benchmark del motor de accesibilidad: latencia, consumo de tokens y
variabilidad de las respuestas del modelo de IA.

Corre cada texto de tests/fixtures/analysis/ N veces por cada variante de
parámetros y guarda los resultados crudos (JSON) y un resumen (Markdown) en
docs/benchmarks/. Usa las conexiones de /admin en orden de prioridad: para
comparar proveedores, dejá habilitada solo la conexión que quieras medir.

Una variante es un JSON de parámetros que pisa los extra_params de la conexión
(ej. '{"thinking_budget": 0}' en Gemini o '{"reasoning_effort": "high"}' en Groq).
'{}' usa la configuración de la conexión tal cual.

Uso (desde la raíz del repo, con el venv activo):
    python -m scripts.benchmark_analysis --dry-run
    python -m scripts.benchmark_analysis --runs 3
    python -m scripts.benchmark_analysis --runs 3 --variants '{}' '{"thinking_budget": 0}'
    python -m scripts.benchmark_analysis --samples 01,03 --runs 1
    python -m scripts.benchmark_analysis --rules-only

Cada llamada consume cuota real de las conexiones cargadas en /admin, salvo
--rules-only: corre solo el motor de reglas (sin IA) para calibrar umbrales y pesos.
"""

import argparse
import asyncio
import json
import statistics
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from app.db.database import init_db
from app.schemas.document import ExtractedDocument
from app.services.accessibility_service import _normalize, analyze_document
from app.services.key_rotation_service import AllKeysExhaustedError
from app.services.rules_service import compute_score, run_rules

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "analysis"
OUTPUT_DIR = ROOT / "docs" / "benchmarks"
MINUTE_WINDOW_WAIT_S = 65


def _load_samples(filters: list[str] | None) -> dict[str, str]:
    files = sorted(FIXTURES_DIR.glob("*.txt"))
    if filters:
        files = [f for f in files if any(f.stem.startswith(p) for p in filters)]
    return {f.stem: f.read_text(encoding="utf-8") for f in files}


def _document(text: str) -> ExtractedDocument:
    return ExtractedDocument(
        source_type="text",
        raw_text=text,
        text_for_analysis=text,
        word_count=len(text.split()),
        character_count=len(text),
    )


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 1) if values else None


def _jaccard(a: set[str], b: set[str]) -> float:
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def summarize(runs: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in runs:
        groups.setdefault((r["sample"], r["mode"]), []).append(r)

    rows = []
    for (sample, mode), items in sorted(groups.items()):
        ok = [r for r in items if r["response"] is not None]
        latencies = [r["response"]["metadata"]["latency_ms"] / 1000 for r in ok]
        scores = [r["response"]["estimated_score"] for r in ok]
        # Los crudos anteriores al motor de reglas no traen score_breakdown.
        breakdowns = [r["response"].get("score_breakdown") for r in ok]
        ai_scores = [b["ai_score"] for b in breakdowns if b and b["ai_score"] is not None]
        rules_scores = [b["rules_score"] for b in breakdowns if b]
        # != "rules" (y no == "ai") para poder resumir también crudos viejos con source="gemini".
        barrier_counts = [
            sum(1 for b in r["response"]["barriers"] if b["source"] != "rules") for r in ok
        ]
        rules_barrier_counts = [
            sum(1 for b in r["response"]["barriers"] if b["source"] == "rules") for r in ok
        ]
        fragment_sets = [
            {_normalize(b["original_text"]) for b in r["response"]["barriers"] if b["source"] != "rules"}
            for r in ok
        ]
        models = sorted({
            f"{r['response']['metadata'].get('provider', 'gemini')}/{r['response']['metadata']['model']}"
            for r in ok
        })
        pair_scores = [_jaccard(a, b) for a, b in combinations(fragment_sets, 2)]
        dim_status = {}
        for cat in ("comprension", "estructura"):
            statuses = [
                next((d["status"] for d in r["response"]["dimensions"] if d["category"] == cat), "-")
                for r in ok
            ]
            dim_status[cat] = "/".join(sorted(set(statuses))) if statuses else "-"

        def meta(key: str) -> list[int]:
            return [r["response"]["metadata"][key] or 0 for r in ok]

        rows.append({
            "sample": sample,
            "mode": mode,
            "models": ", ".join(models) or "-",
            "words": items[0]["word_count"],
            "runs_ok": len(ok),
            "runs_error": len(items) - len(ok),
            "latency_s_mean": _mean(latencies),
            "latency_s_min": round(min(latencies), 1) if latencies else None,
            "latency_s_max": round(max(latencies), 1) if latencies else None,
            "prompt_tokens_mean": _mean(meta("prompt_tokens")),
            "output_tokens_mean": _mean(meta("output_tokens")),
            "thinking_tokens_mean": _mean(meta("thinking_tokens")),
            "score_mean": _mean(scores),
            "score_range": f"{min(scores)}-{max(scores)}" if scores else "-",
            "score_stdev": round(statistics.stdev(scores), 1) if len(scores) > 1 else None,
            "ai_score_mean": _mean(ai_scores),
            "rules_score": "/".join(str(s) for s in sorted(set(rules_scores))) or "-",
            "barriers_range": f"{min(barrier_counts)}-{max(barrier_counts)}" if barrier_counts else "-",
            "rules_barriers_range": (
                f"{min(rules_barrier_counts)}-{max(rules_barrier_counts)}" if rules_barrier_counts else "-"
            ),
            "fragment_jaccard_mean": round(statistics.mean(pair_scores), 2) if pair_scores else None,
            "unverified_fragments": sum(meta("unverified_fragments")),
            "status_comprension": dim_status["comprension"],
            "status_estructura": dim_status["estructura"],
        })
    return rows


def render_markdown(rows: list[dict], started_at: str) -> str:
    lines = [
        "# Benchmark del motor de accesibilidad",
        "",
        f"- Fecha (UTC): {started_at}",
        "- `Variante`: parámetros que pisan los extra_params de la conexión (`{}` = configuración de la conexión).",
        "- `Modelo`: proveedor/modelo que respondió (puede variar si hubo rotación entre conexiones).",
        "- `Jaccard frag.`: similitud promedio (0 a 1) entre corridas de los fragmentos señalados como barrera.",
        "",
        "## Latencia y tokens",
        "",
        "| Texto | Palabras | Variante | Modelo | OK/Err | Latencia media (s) | Mín-Máx (s) | Tokens entrada | Tokens salida | Tokens thinking |",
        "|---|---:|---|---|---|---:|---|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['sample']} | {r['words']} | `{r['mode']}` | {r['models']} | {r['runs_ok']}/{r['runs_error']} "
            f"| {r['latency_s_mean']} | {r['latency_s_min']}-{r['latency_s_max']} "
            f"| {r['prompt_tokens_mean']} | {r['output_tokens_mean']} | {r['thinking_tokens_mean']} |"
        )
    lines += [
        "",
        "## Variabilidad",
        "",
        "| Texto | Variante | Score medio | Rango | Desvío | Score IA | Score reglas | Barreras IA (rango) "
        "| Barreras reglas (rango) | Jaccard frag. | Frag. no verificados | Comprensión | Estructura |",
        "|---|---|---:|---|---:|---:|---:|---|---|---:|---:|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['sample']} | `{r['mode']}` | {r['score_mean']} | {r['score_range']} | {r['score_stdev']} "
            f"| {r['ai_score_mean']} | {r['rules_score']} | {r['barriers_range']} | {r['rules_barriers_range']} "
            f"| {r['fragment_jaccard_mean']} | {r['unverified_fragments']} "
            f"| {r['status_comprension']} | {r['status_estructura']} |"
        )
    return "\n".join(lines) + "\n"


def render_rules_markdown(samples: dict[str, str], started_at: str) -> str:
    """Métricas y puntaje del motor de reglas por texto, sin llamar a la IA."""
    lines = [
        "# Calibración del motor de reglas",
        "",
        f"- Fecha (UTC): {started_at}",
        "- Solo reglas: no se consultó a la IA, así que no hay puntaje combinado.",
        "",
        "| Texto | Palabras | Oraciones | Extensas (graves) | Máx. palabras | Párrafos | Extensos (graves) "
        "| Penalizaciones | Score reglas |",
        "|---|---:|---:|---|---:|---:|---|---|---:|",
    ]
    for name, text in samples.items():
        rules = run_rules(_document(text))
        m = rules.metrics
        penalties = ", ".join(f"{p.rule} -{p.points}" for p in rules.penalties) or "-"
        lines.append(
            f"| {name} | {m.analyzed_word_count} | {m.sentence_count} "
            f"| {m.long_sentences} ({m.severe_long_sentences}) | {m.max_sentence_words} "
            f"| {m.paragraph_count} | {m.long_paragraphs} ({m.severe_long_paragraphs}) "
            f"| {penalties} | {compute_score(None, rules).rules_score} |"
        )
    return "\n".join(lines) + "\n"


async def _run_once(text: str, overrides: dict) -> dict:
    response = await analyze_document(_document(text), overrides=overrides)
    return response.model_dump()


def _parse_variant(raw: str) -> dict:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise SystemExit(f"Variante inválida (debe ser un objeto JSON): {raw}")
    return value


async def main(args: argparse.Namespace) -> None:
    samples = _load_samples(args.samples.split(",") if args.samples else None)
    if args.rules_only:
        print(render_rules_markdown(samples, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")))
        return

    # Se normaliza el texto de cada variante para usarlo como etiqueta estable.
    modes = [json.dumps(_parse_variant(v), ensure_ascii=False) for v in args.variants]
    plan = [(i, name, mode) for i in range(args.runs) for name in samples for mode in modes]

    print(f"Textos: {', '.join(samples)} | variantes: {modes} | corridas: {args.runs}")
    print(f"Total de llamadas a la IA: {len(plan)}")
    if args.dry_run:
        return

    init_db()
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = OUTPUT_DIR / f"analysis_raw_{stamp}.json"
    md_path = OUTPUT_DIR / f"analysis_summary_{stamp}.md"

    runs: list[dict] = []
    for n, (i, name, mode) in enumerate(plan, 1):
        text = samples[name]
        entry = {"sample": name, "mode": mode, "run": i + 1, "word_count": len(text.split()),
                 "response": None, "error": None}
        for attempt in (1, 2):
            try:
                entry["response"] = await _run_once(text, json.loads(mode))
                break
            except AllKeysExhaustedError as e:
                if attempt == 1:
                    print(f"  conexiones agotadas; espero {MINUTE_WINDOW_WAIT_S}s por si es el límite por minuto...")
                    await asyncio.sleep(MINUTE_WINDOW_WAIT_S)
                    continue
                entry["error"] = f"AllKeysExhaustedError: {e}"
            except Exception as e:  # proveedores caídos, JSON inválido, red, etc.
                entry["error"] = f"{type(e).__name__}: {e}"
                break

        runs.append(entry)
        status = (
            f"{entry['response']['metadata']['latency_ms'] / 1000:.1f}s "
            f"score={entry['response']['estimated_score']}"
            if entry["response"] else f"ERROR {entry['error'][:120]}"
        )
        print(f"[{n}/{len(plan)}] {name} variante={mode} run={i + 1}: {status}")

        raw_path.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(render_markdown(summarize(runs), started_at), encoding="utf-8")

        if entry["error"] and entry["error"].startswith("AllKeysExhaustedError"):
            print("Cuota agotada en todas las conexiones: corto el benchmark (resultados parciales guardados).")
            break
        if n < len(plan):
            await asyncio.sleep(args.delay)

    print(f"\nCrudos: {raw_path.relative_to(ROOT)}\nResumen: {md_path.relative_to(ROOT)}\n")
    print(md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=3, help="Corridas por texto y variante (default: 3).")
    parser.add_argument("--variants", nargs="+", default=["{}"],
                        help="Variantes de parámetros en JSON, ej: '{}' '{\"thinking_budget\": 0}' (default: '{}').")
    parser.add_argument("--samples", default=None, help="Prefijos de fixtures a incluir, ej: '01,03'.")
    parser.add_argument("--delay", type=float, default=5.0, help="Segundos de espera entre llamadas.")
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra cuántas llamadas haría.")
    parser.add_argument("--rules-only", action="store_true",
                        help="Corre solo el motor de reglas (sin IA ni cuota) e imprime sus métricas.")
    asyncio.run(main(parser.parse_args()))
