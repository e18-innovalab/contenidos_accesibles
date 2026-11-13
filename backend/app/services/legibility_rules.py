"""
Reglas de legibilidad visual del archivo (issue #79): letra chica (parte 1), contraste (parte 2) y
tipografía poco legible (parte 3).

Se aplican solo a archivos (PDF, Word y PowerPoint): el texto pegado no tiene tipografía.
Todo se calcula localmente con los datos de ExtractedDocument.legibility, sin IA.
Umbrales y limitaciones documentados en docs/motor_reglas.md.
"""

from dataclasses import dataclass, field

from app.schemas.analysis import ScorePenalty
from app.schemas.document import ExtractedDocument
from app.services.legibility_extractor import (
    LARGE_TEXT_MIN_RATIO,
    MIN_SMALL_PASSAGE_WORDS,
    SMALL_PASSAGE_PT,
)
from app.services.legibility_typography import (
    MIN_CAPS_WORDS,
    MIN_DECORATIVE_WORDS,
    MIN_ITALIC_WORDS,
    MIN_LAYOUT_PARAGRAPH_WORDS,
    MIN_LINE_SPACING,
    MIN_UNDERLINE_WORDS,
    format_spacing,
)

MIN_BODY_FONT_PT = 9.0  # cuerpo del texto por debajo de esto: barrera_detectada
RECOMMENDED_BODY_FONT_PT = 11  # lo que se recomienda en el mensaje
MAX_REPORTED_PASSAGES = 3  # pasajes listados como barrera; el total va al comentario

SMALL_BODY_POINTS = 15
SMALL_PASSAGE_POINTS = 5
MAX_SMALL_PASSAGES_PENALTY = 15  # tope, como referencias_visuales

# Contraste: debajo de 3:1 falla incluso para texto grande (barrera_detectada); entre 3:1 y 4.5:1
# en texto normal, para_revisar. Los umbrales de WCAG están en legibility_extractor.py.
SEVERE_CONTRAST_POINTS = 8
LOW_CONTRAST_POINTS = 4
MAX_CONTRAST_PENALTY = 16  # tope, como referencias_visuales

_SEVERITY_ORDER = {"correcta": 0, "para_revisar": 1, "barrera_detectada": 2}

_PLACE_LABELS = {"pdf": "página", "pptx": "diapositiva"}


@dataclass
class LegibilityResult:
    barriers: list[dict] = field(default_factory=list)
    penalties: list[ScorePenalty] = field(default_factory=list)
    status: str = "correcta"
    comments: list[str] = field(default_factory=list)
    body_font_size: float | None = None
    small_text_passages: int = 0
    low_contrast_passages: int = 0
    typography_issues: int = 0


def _worse(a: str, b: str) -> str:
    return a if _SEVERITY_ORDER[a] >= _SEVERITY_ORDER[b] else b


def _applies(doc: ExtractedDocument) -> bool:
    """El texto pegado no tiene tipografía y el PDF escaneado ya tiene su propia barrera."""
    return doc.source_type != "text" and not doc.is_scanned_pdf and bool(doc.raw_text.strip())


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
    if not _applies(doc):
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
            severe=True,
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


def _fmt_ratio(ratio: float) -> str:
    return f"{ratio:.1f}".replace(".", ",") + ":1"


def contrast_assessment(doc: ExtractedDocument) -> LegibilityResult:
    """Contraste texto/fondo (WCAG 1.4.3): 4.5:1 para texto normal y 3:1 para texto grande."""
    result = LegibilityResult()
    stats = doc.legibility
    if not _applies(doc) or not stats or not stats.low_contrast_passages_total:
        return result

    total = stats.low_contrast_passages_total
    result.low_contrast_passages = total
    # Primero los de peor contraste.
    passages = sorted(stats.low_contrast_passages, key=lambda p: p.contrast_ratio)
    severe = [p for p in passages if p.contrast_ratio < LARGE_TEXT_MIN_RATIO]
    result.status = "barrera_detectada" if severe else "para_revisar"
    result.comments.append(
        f"{total} pasaje(s) no alcanzan el contraste mínimo con su fondo (WCAG 1.4.3); "
        f"el peor tiene {_fmt_ratio(passages[0].contrast_ratio)}."
    )
    for passage in passages[:MAX_REPORTED_PASSAGES]:
        is_severe = passage.contrast_ratio < LARGE_TEXT_MIN_RATIO
        kind = "texto grande" if passage.is_large_text else "texto normal"
        result.barriers.append({
            "category": "accesibilidad_visual",
            "severity": "barrera_detectada" if is_severe else "para_revisar",
            "issue": (
                f"Contraste insuficiente entre el texto y el fondo "
                f"({_fmt_ratio(passage.contrast_ratio)}){_place(doc, passage.page_number)}"
            ),
            "original_text": passage.text,
            "explanation": (
                f"El texto en {passage.text_color} sobre fondo {passage.background_color} tiene un contraste de "
                f"{_fmt_ratio(passage.contrast_ratio)}, y para {kind} se necesita al menos "
                f"{_fmt_ratio(passage.required_ratio)} (WCAG 1.4.3). Con poco contraste, a estudiantes con baja "
                "visión o daltonismo les cuesta distinguir las letras, y al imprimir en blanco y negro o "
                "proyectar el texto puede desaparecer."
            ),
            "recommendation": (
                "Usá texto oscuro sobre fondo claro (o claro sobre oscuro) con un contraste de al menos 4,5:1: "
                "por ejemplo, negro o gris oscuro sobre blanco. Podés verificarlo con un verificador de contraste."
            ),
            "suggested_rewrite": None,
            "fragment_found": _in_text(passage.text, doc.raw_text),
            "source": "rules",
        })
    stored_points = sum(
        SEVERE_CONTRAST_POINTS if p.contrast_ratio < LARGE_TEXT_MIN_RATIO else LOW_CONTRAST_POINTS
        for p in passages
    )
    # Los pasajes que no se guardaron (más allá de MAX_STORED_PASSAGES) suman como leves.
    stored_points += LOW_CONTRAST_POINTS * (total - len(passages))
    result.penalties.append(ScorePenalty(
        rule="contraste_insuficiente", category="accesibilidad_visual", count=total,
        points=min(MAX_CONTRAST_PENALTY, stored_points), severe=bool(severe),
    ))
    return result


# Tipografía: cada regla genera una sola barrera, con la cantidad de párrafos y dónde aparecen.
TYPOGRAPHY_POINTS = 4
DECORATIVE_BODY_POINTS = 8
MAX_TYPOGRAPHY_PENALTY = 12  # tope del conjunto de reglas de tipografía

_PLACES_PLURAL = {"pdf": "páginas", "pptx": "diapositivas"}


def _places(doc: ExtractedDocument, pages: list[int]) -> str:
    if not pages or doc.source_type not in _PLACE_LABELS:
        return ""
    if len(pages) == 1:
        return f" ({_PLACE_LABELS[doc.source_type]} {pages[0]})"
    return f" ({_PLACES_PLURAL[doc.source_type]} {', '.join(str(p) for p in pages)})"


def _typography_text(issue, doc: ExtractedDocument) -> tuple[str, str, str]:
    """(issue, explanation, recommendation) de cada regla."""
    n = issue.passages
    where = _places(doc, issue.pages)
    if issue.rule == "fuente_decorativa":
        main = doc.legibility.body_font_decorative and doc.legibility.body_font_name == issue.detail
        return (
            (f"La fuente principal del texto es decorativa o manuscrita ({issue.detail}){where}" if main
             else f"Pasajes en una fuente decorativa o manuscrita ({issue.detail}){where}"),
            f"{n} párrafo(s) tienen {MIN_DECORATIVE_WORDS} palabras o más en {issue.detail}. Las fuentes "
            "decorativas o de estilo manuscrito tienen formas de letras poco habituales que cuesta "
            "distinguir (por ejemplo, entre la b, la d y la p), sobre todo para estudiantes con dislexia "
            "o baja visión.",
            "Usá una fuente simple y sin adornos, como Arial, Verdana o Calibri, al menos en el cuerpo del "
            "texto. Si querés un toque decorativo, dejalo para un título corto.",
        )
    if issue.rule == "cursiva":
        return (
            f"Pasajes largos en cursiva{where}",
            f"{n} párrafo(s) tienen {MIN_ITALIC_WORDS} palabras o más en cursiva. La cursiva inclina y junta "
            "las letras: en pasajes largos el texto parece correrse y cuesta más leerlo, sobre todo con "
            "dislexia o baja visión.",
            "Usá cursiva solo en palabras puntuales (por ejemplo, nombres científicos o títulos de obras). "
            "Para destacar un pasaje, preferí la negrita.",
        )
    if issue.rule == "mayusculas":
        return (
            f"Texto largo en MAYÚSCULAS sostenidas{where}",
            f"{n} párrafo(s) tienen {MIN_CAPS_WORDS} palabras o más escritas en mayúsculas. Sin las formas de "
            "las minúsculas, las palabras pierden su contorno y se leen letra por letra; además, algunos "
            "lectores de pantalla las deletrean.",
            "Escribí el texto en minúsculas, con mayúscula inicial. Para destacar, usá negrita o un título.",
        )
    if issue.rule == "subrayado":
        return (
            f"Texto subrayado que no es un enlace{where}",
            f"{n} párrafo(s) tienen {MIN_UNDERLINE_WORDS} palabras o más subrayadas sin ser un enlace. El "
            "subrayado se asocia con los enlaces y corta los trazos de letras como la g, la p o la y, así "
            "que confunde y dificulta la lectura.",
            "Quitá el subrayado y, si querés destacar, usá negrita.",
        )
    if issue.rule == "justificado":
        return (
            f"Texto justificado{where}",
            f"{n} párrafo(s) de {MIN_LAYOUT_PARAGRAPH_WORDS} palabras o más están justificados. La "
            "justificación agrega espacios irregulares entre las palabras que dificultan seguir el renglón, "
            "sobre todo con dislexia (WCAG 1.4.8).",
            "Alineá el texto a la izquierda, con el borde derecho irregular.",
        )
    spacing = issue.detail or "menos de " + format_spacing(MIN_LINE_SPACING)
    return (
        f"Interlineado menor a {format_spacing(MIN_LINE_SPACING)}{where}",
        f"{n} párrafo(s) de {MIN_LAYOUT_PARAGRAPH_WORDS} palabras o más tienen un interlineado de {spacing}. "
        f"WCAG 1.4.8 y la guía de la British Dyslexia Association recomiendan al menos "
        f"{format_spacing(MIN_LINE_SPACING)}: con los renglones más juntos es fácil saltearse uno o leer "
        "dos veces el mismo.",
        f"Aplicá un interlineado de {format_spacing(MIN_LINE_SPACING)} líneas en el cuerpo del texto "
        "(en Word y PowerPoint: Inicio > Espaciado entre líneas).",
    )


def typography_assessment(doc: ExtractedDocument) -> LegibilityResult:
    """Cursiva, MAYÚSCULAS, subrayado, fuentes decorativas, justificado e interlineado (WCAG 1.4.8)."""
    result = LegibilityResult()
    stats = doc.legibility
    if not _applies(doc) or not stats or not stats.typography_issues:
        return result

    remaining = MAX_TYPOGRAPHY_PENALTY
    for issue in stats.typography_issues:
        severe = (
            issue.rule == "fuente_decorativa"
            and stats.body_font_decorative and stats.body_font_name == issue.detail
        )
        title, explanation, recommendation = _typography_text(issue, doc)
        result.barriers.append({
            "category": "accesibilidad_visual",
            "severity": "barrera_detectada" if severe else "para_revisar",
            "issue": title,
            "original_text": issue.example,
            "explanation": explanation,
            "recommendation": recommendation,
            "suggested_rewrite": None,
            "fragment_found": _in_text(issue.example, doc.raw_text),
            "source": "rules",
        })
        result.status = _worse(result.status, "barrera_detectada" if severe else "para_revisar")
        points = min(remaining, DECORATIVE_BODY_POINTS if severe else TYPOGRAPHY_POINTS)
        remaining -= points
        # Alcanzado el tope, la barrera se muestra igual pero no figura en el desglose con 0 puntos.
        if points:
            result.penalties.append(ScorePenalty(
                rule=f"tipografia_{issue.rule}", category="accesibilidad_visual", count=issue.passages,
                points=points, severe=severe,
            ))
    result.typography_issues = len(stats.typography_issues)
    names = {
        "fuente_decorativa": "fuente decorativa", "cursiva": "cursiva", "mayusculas": "mayúsculas sostenidas",
        "subrayado": "subrayado", "justificado": "texto justificado", "interlineado": "interlineado reducido",
    }
    result.comments.append(
        "Tipografía poco legible: " + ", ".join(names[i.rule] for i in stats.typography_issues) + "."
    )
    return result


COLORBLIND_PAIR_POINTS = 4
MAX_COLORBLIND_PENALTY = 8
_CVD_LABELS = {
    "protanopia": "protanopía",
    "deuteranopia": "deuteranopía",
    "tritanopia": "tritanopía",
}


def colorblind_assessment(doc: ExtractedDocument) -> LegibilityResult:
    """Detecta pares de colores usados en el texto que pueden confundirse con daltonismo (WCAG 1.4.1)."""
    result = LegibilityResult()
    stats = doc.legibility
    if not _applies(doc) or not stats or not stats.colorblind_confusion_pairs:
        return result

    pairs = stats.colorblind_confusion_pairs
    result.status = "para_revisar"
    result.comments.append(
        f"Se detectaron {len(pairs)} par(es) de colores en el texto que pueden confundirse con daltonismo."
    )
    for pair in pairs[:3]:
        cvds = ", ".join(_CVD_LABELS.get(d, d) for d in pair.deficiencies)
        original = pair.sample_a or f"{pair.color_a} / {pair.color_b}"
        result.barriers.append({
            "category": "accesibilidad_visual",
            "severity": "para_revisar",
            "issue": f"Combinación de colores problemática para daltonismo ({pair.color_a} y {pair.color_b}){_place(doc, pair.page_number)}",
            "original_text": original,
            "explanation": (
                f"El documento utiliza los colores {pair.color_a} (ej. '{pair.sample_a}') y "
                f"{pair.color_b} (ej. '{pair.sample_b}'), que pierden diferenciación bajo {cvds}. "
                "Si se usan para distinguir categorías o respuestas, estudiantes con daltonismo pueden confundirlos (WCAG 1.4.1)."
            ),
            "recommendation": (
                "No dependas solo de estos colores para diferenciar contenido: agregá etiquetas de texto, "
                "símbolos, negrita, subrayado o patrones, o elegí pares con contraste tonal claro (ej. azul oscuro y naranja)."
            ),
            "suggested_rewrite": None,
            "fragment_found": bool(pair.sample_a and _in_text(pair.sample_a, doc.raw_text)),
            "source": "rules",
        })

    result.penalties.append(ScorePenalty(
        rule="colores_daltonismo",
        category="accesibilidad_visual",
        count=len(pairs),
        points=min(MAX_COLORBLIND_PENALTY, COLORBLIND_PAIR_POINTS * len(pairs)),
        severe=False,
    ))
    return result


def legibility_assessment(doc: ExtractedDocument) -> LegibilityResult:
    """Todas las reglas de legibilidad visual del archivo, unidas en un solo resultado."""
    combined = LegibilityResult()
    for part in (
        small_text_assessment(doc),
        contrast_assessment(doc),
        typography_assessment(doc),
        colorblind_assessment(doc),
    ):
        combined.barriers.extend(part.barriers)
        combined.penalties.extend(part.penalties)
        combined.comments.extend(part.comments)
        combined.status = _worse(combined.status, part.status)
        combined.body_font_size = combined.body_font_size or part.body_font_size
        combined.small_text_passages += part.small_text_passages
        combined.low_contrast_passages += part.low_contrast_passages
        combined.typography_issues += part.typography_issues
    return combined
