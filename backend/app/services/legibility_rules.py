"""
Reglas de legibilidad visual del archivo (issue #79, parte 1: letra chica).

Se aplican solo a archivos (PDF, Word y PowerPoint): el texto pegado no tiene tipografía.
Todo se calcula localmente con los datos de ExtractedDocument.legibility, sin IA.
Umbrales y limitaciones documentados en docs/motor_reglas.md.
"""

from dataclasses import dataclass, field

from app.schemas.analysis import ScorePenalty
from app.schemas.document import ExtractedDocument
from app.services.legibility_extractor import MIN_SMALL_PASSAGE_WORDS, SMALL_PASSAGE_PT

MIN_BODY_FONT_PT = 9.0  # cuerpo del texto por debajo de esto: barrera_detectada
RECOMMENDED_BODY_FONT_PT = 11  # lo que se recomienda en el mensaje
MAX_REPORTED_PASSAGES = 3  # pasajes listados como barrera; el total va al comentario

SMALL_BODY_POINTS = 15
SMALL_PASSAGE_POINTS = 5
MAX_SMALL_PASSAGES_PENALTY = 15  # tope, como referencias_visuales

_PLACE_LABELS = {"pdf": "página", "pptx": "diapositiva"}


@dataclass
class LegibilityResult:
    barriers: list[dict] = field(default_factory=list)
    penalties: list[ScorePenalty] = field(default_factory=list)
    status: str = "correcta"
    comments: list[str] = field(default_factory=list)
    body_font_size: float | None = None
    small_text_passages: int = 0


def _fmt_pt(size: float) -> str:
    return f"{size:g}".replace(".", ",")


def _place(doc: ExtractedDocument, page_number: int) -> str:
    label = _PLACE_LABELS.get(doc.source_type)
    return f" ({label} {page_number})" if label else ""


def _in_text(fragment: str, raw_text: str) -> bool:
    fragment = " ".join(fragment.rstrip("…").split())
    return bool(fragment) and fragment in " ".join(raw_text.split())


def _body_font_size(doc: ExtractedDocument) -> float | None:
    """Prefiere el tamaño medido run por run; si no hay, el que ya calculó la extracción de estructura."""
    if doc.legibility and doc.legibility.measured_chars:
        return doc.legibility.body_font_size
    return doc.structure.body_font_size


def small_text_assessment(doc: ExtractedDocument) -> LegibilityResult:
    """Letra chica: cuerpo de menos de 9 pt y pasajes largos de menos de 8 pt."""
    result = LegibilityResult()
    if doc.source_type == "text" or doc.is_scanned_pdf or not doc.raw_text.strip():
        return result

    body = _body_font_size(doc)
    result.body_font_size = body
    small_body = body is not None and body < MIN_BODY_FONT_PT
    if small_body:
        result.status = "barrera_detectada"
        result.comments.append(f"El cuerpo del texto está en {_fmt_pt(body)} pt (menos de {_fmt_pt(MIN_BODY_FONT_PT)} pt).")
        result.barriers.append({
            "category": "accesibilidad_visual",
            "severity": "barrera_detectada",
            "issue": f"Letra demasiado chica en el cuerpo del texto ({_fmt_pt(body)} pt)",
            "original_text": f"[Cuerpo del texto de {doc.filename or 'el documento'}: {_fmt_pt(body)} pt]",
            "explanation": (
                f"La mayor parte del texto está escrita en {_fmt_pt(body)} pt. Con una letra tan chica, "
                "a estudiantes con baja visión, dislexia o que leen en pantallas pequeñas les cuesta "
                "mucho leer, y al imprimir o proyectar el material se vuelve ilegible."
            ),
            "recommendation": (
                f"Usá al menos {RECOMMENDED_BODY_FONT_PT} pt en el cuerpo del texto "
                f"(nunca menos de {_fmt_pt(MIN_BODY_FONT_PT)} pt)."
            ),
            "suggested_rewrite": None,
            "fragment_found": None,
            "source": "rules",
        })
        result.penalties.append(ScorePenalty(
            rule="letra_chica_cuerpo", category="accesibilidad_visual", count=1, points=SMALL_BODY_POINTS,
        ))

    stats = doc.legibility
    # Si todo el cuerpo ya es chico, cada párrafo sería un "pasaje chico": basta con la barrera del cuerpo.
    if stats and stats.small_text_passages_total and not small_body:
        total = stats.small_text_passages_total
        result.small_text_passages = total
        result.status = "para_revisar" if result.status == "correcta" else result.status
        result.comments.append(
            f"{total} pasaje(s) de {MIN_SMALL_PASSAGE_WORDS} palabras o más están en menos de "
            f"{_fmt_pt(SMALL_PASSAGE_PT)} pt."
        )
        for passage in stats.small_text_passages[:MAX_REPORTED_PASSAGES]:
            result.barriers.append({
                "category": "accesibilidad_visual",
                "severity": "para_revisar",
                "issue": f"Pasaje con letra muy chica ({_fmt_pt(passage.font_size)} pt){_place(doc, passage.page_number)}",
                "original_text": passage.text,
                "explanation": (
                    f"Este pasaje de {passage.word_count} palabras está en {_fmt_pt(passage.font_size)} pt, "
                    "mucho más chico que el resto. Las notas, epígrafes o aclaraciones en letra tan chica "
                    "suelen saltearse o no poder leerse, sobre todo con baja visión o al imprimir."
                ),
                "recommendation": (
                    f"Si la información es importante, pasala al cuerpo del texto o usá al menos "
                    f"{_fmt_pt(MIN_BODY_FONT_PT)} pt; si no lo es, considerá quitarla."
                ),
                "suggested_rewrite": None,
                "fragment_found": _in_text(passage.text, doc.raw_text),
                "source": "rules",
            })
        result.penalties.append(ScorePenalty(
            rule="letra_chica_pasajes", category="accesibilidad_visual", count=total,
            points=min(MAX_SMALL_PASSAGES_PENALTY, SMALL_PASSAGE_POINTS * total),
        ))
    return result
