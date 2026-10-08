"""
Motor de reglas automáticas: detecciones determinísticas que no dependen de la IA.

Corre sobre el texto completo del material (sin costo de tokens), siempre da el
mismo resultado para el mismo documento y aporta la parte objetiva del puntaje.
Las reglas de texto asumen el formato de DocumentService: un párrafo por renglón
(los PDF se reacomodan por bloques) y los ítems de lista en renglones propios.

Los umbrales y pesos son un punto de partida: se calibran con
`python -m scripts.benchmark_analysis --rules-only` (ver docs/motor_reglas.md).
"""

import re
from dataclasses import dataclass, field

from app.schemas.analysis import (
    DimensionAssessment,
    RulesMetrics,
    ScoreBreakdown,
    ScorePenalty,
)
from app.schemas.document import ExtractedDocument

# --- Umbrales de las reglas -------------------------------------------------
LONG_SENTENCE_WORDS = 35  # más de 35 palabras: para_revisar
SEVERE_SENTENCE_WORDS = 50  # 50 o más: barrera_detectada
LONG_PARAGRAPH_WORDS = 150  # más de 150 palabras sin división: para_revisar
SEVERE_PARAGRAPH_WORDS = 250  # 250 o más: barrera_detectada
MIN_WORDS_FOR_HEADING_RULE = 150  # Un PDF de menos de 150 palabras no exige títulos complejos
LONG_SECTION_WORDS = 350  # Más de 350 palabras bajo un título sin subdivisiones: para_revisar
NO_HEADINGS_PENALTY = 15  # Penalización si falta total de títulos en PDF extenso
HIERARCHY_SKIP_PENALTY = 6  # Penalización por salto de nivel jerárquico (ej. H1 a H3)
LONG_SECTION_PENALTY = 5  # Penalización por sección extensa sin subdivisiones
MAX_REPORTED_PER_RULE = 3  # barreras listadas por regla; el total va al comentario
PARAGRAPH_EXCERPT_WORDS = 25  # palabras citadas de un párrafo extenso

# --- Tarea #25: Consignas multi-acción, Legibilidad y Referencias Visuales ---
MULTI_ACTION_WARN_THRESHOLD = 3  # 3 acciones: para_revisar
MULTI_ACTION_SEVERE_THRESHOLD = 4  # 4 o más acciones: barrera_detectada
MULTI_ACTION_PENALTY_POINTS = 5
MAX_MULTI_ACTION_PENALTY = 15

MIN_WORDS_FOR_READABILITY = 100  # Evaluar solo en documentos de >= 100 palabras
READABILITY_WARN_THRESHOLD = 50.0  # IFSZ < 50: algo difícil (para_revisar)
READABILITY_SEVERE_THRESHOLD = 40.0  # IFSZ < 40: muy difícil (barrera_detectada)
READABILITY_WARN_POINTS = 10
READABILITY_SEVERE_POINTS = 15

VISUAL_REF_PENALTY_POINTS = 8
MAX_VISUAL_REF_PENALTY = 16

# --- Puntaje ----------------------------------------------------------------
AI_WEIGHT = 0.7
RULES_WEIGHT = 0.3
MAX_SENTENCE_PENALTY = 30
SEVERE_SENTENCE_EXTRA_POINTS = 3
MAX_PARAGRAPH_PENALTY = 30
LONG_PARAGRAPH_POINTS = 6
SEVERE_PARAGRAPH_POINTS = 10
SCANNED_PDF_POINTS = 40
IMAGES_POINTS = 10
NO_TEXT_CAP = 15
SCANNED_CAP = 40
SEVERE_BARRIER_CAP = 89  # con una barrera grave objetiva no puede ser "muy accesible"

_WORD_RE = re.compile(r"\b\w+\b")  # mismo criterio que DocumentService
# Fin de oración: signos de cierre seguidos de espacio o fin de renglón.
_SENTENCE_END_RE = re.compile(r"(?:[.!?]+|…)[\"'»”’)\]]*(?=\s|$)")
_LIST_MARKER_RE = re.compile(r"^(?:\d{1,2}|[a-zA-Z])$")
_ABBREVIATIONS = {
    "pág", "págs", "p", "pp", "ej", "sr", "sra", "srta", "dr", "dra", "lic", "prof",
    "profa", "aprox", "cap", "caps", "vol", "núm", "nro", "nº", "art", "fig", "figs",
    "inc", "cf", "ud", "uds", "vs", "av", "máx", "mín", "min", "seg", "hs",
}
_SEVERITY_ORDER = {"correcta": 0, "para_revisar": 1, "barrera_detectada": 2}


@dataclass
class RuleFinding:
    """Barrera detectada por una regla. anchor es el texto completo que la originó."""

    barrier: dict
    anchor: str | None = None


@dataclass
class RulesResult:
    findings: list[RuleFinding]
    dimensions: list[DimensionAssessment]
    metrics: RulesMetrics
    is_scanned_pdf: bool = False
    has_images: bool = False
    image_count: int = 0
    has_text: bool = True
    penalties: list[ScorePenalty] = field(default_factory=list)


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def split_paragraphs(text: str) -> list[str]:
    """Un párrafo por renglón no vacío (títulos e ítems de lista cuentan como bloques propios)."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_sentence_end(line: str, start: int, match: re.Match) -> bool:
    following = line[match.end():].lstrip()
    # En español la oración siguiente empieza en mayúscula, número o ¿¡: "etc. y" no corta.
    if following[:1].islower():
        return False
    if match.group()[0] != "." or match.group().startswith(".."):
        return True
    before = line[start:match.start()].strip()
    if _LIST_MARKER_RE.match(before):  # "1. Leé..." o "a. Respondé..."
        return False
    last_token = before.split()[-1].lstrip("([¿¡\"'«") if before else ""
    if last_token.lower() in _ABBREVIATIONS:
        return False
    # Iniciales de nombres propios: "J. Pérez".
    return not (len(last_token) == 1 and last_token.isupper())


def split_sentences(paragraph: str) -> list[str]:
    """
    Separa un párrafo en oraciones. Los renglones siempre cortan (un título sin
    punto no se pega a la oración siguiente) y se protegen abreviaturas,
    iniciales, decimales ("3.5") y marcadores de lista ("1.").
    """
    sentences = []
    for line in paragraph.splitlines():
        line = line.strip()
        start = 0
        for match in _SENTENCE_END_RE.finditer(line):
            if _is_sentence_end(line, start, match):
                sentence = line[start:match.end()].strip()
                if sentence:
                    sentences.append(sentence)
                start = match.end()
        rest = line[start:].strip()
        if rest:
            sentences.append(rest)
    return sentences


def _excerpt(paragraph: str, max_words: int = PARAGRAPH_EXCERPT_WORDS) -> str:
    """Primeras palabras del párrafo. El '…' final lo entiende _fragment_in_text."""
    words = list(_WORD_RE.finditer(paragraph))
    if len(words) <= max_words:
        return paragraph
    return paragraph[:words[max_words - 1].end()] + " …"


def _worst_severity(counts_severe: int) -> str:
    return "barrera_detectada" if counts_severe else "para_revisar"


def _long_sentence_findings(sentences: list[tuple[str, int]]) -> list[RuleFinding]:
    long_ones = sorted(
        (s for s in sentences if s[1] > LONG_SENTENCE_WORDS), key=lambda s: s[1], reverse=True
    )
    return [
        RuleFinding(
            barrier={
                "category": "comprension",
                "severity": "barrera_detectada" if words >= SEVERE_SENTENCE_WORDS else "para_revisar",
                "issue": f"Oración extensa ({words} palabras)",
                "original_text": sentence,
                "explanation": (
                    f"Las oraciones de más de {LONG_SENTENCE_WORDS} palabras obligan a sostener "
                    "mucha información a la vez en la memoria de trabajo y dificultan la lectura, "
                    "en especial para estudiantes con dislexia, TDAH o que leen en una segunda lengua."
                ),
                "recommendation": (
                    "Dividí la oración en dos o tres más cortas, con una idea por oración, "
                    "y dejá la información principal al comienzo."
                ),
                "suggested_rewrite": None,
                "fragment_found": True,
                "source": "rules",
            },
            anchor=sentence,
        )
        for sentence, words in long_ones[:MAX_REPORTED_PER_RULE]
    ]


def _long_paragraph_findings(paragraphs: list[tuple[str, int]]) -> list[RuleFinding]:
    long_ones = sorted(
        (p for p in paragraphs if p[1] > LONG_PARAGRAPH_WORDS), key=lambda p: p[1], reverse=True
    )
    return [
        RuleFinding(
            barrier={
                "category": "estructura",
                "severity": "barrera_detectada" if words >= SEVERE_PARAGRAPH_WORDS else "para_revisar",
                "issue": f"Párrafo extenso sin divisiones ({words} palabras)",
                "original_text": _excerpt(paragraph),
                "explanation": (
                    f"Un bloque de más de {LONG_PARAGRAPH_WORDS} palabras sin cortes funciona como un "
                    "\"muro de texto\": cuesta encontrar las ideas principales, retomar la lectura "
                    "y seguir el hilo, sobre todo con lectores de pantalla o dificultades de atención."
                ),
                "recommendation": (
                    "Dividí el párrafo en bloques más cortos (una idea por párrafo) y usá subtítulos, "
                    "viñetas o pasos numerados si enumera varios elementos."
                ),
                "suggested_rewrite": None,
                "fragment_found": True,
                "source": "rules",
            },
            anchor=paragraph,
        )
        for paragraph, words in long_ones[:MAX_REPORTED_PER_RULE]
    ]


def _count_comment(count: int, noun: str, threshold: int, longest: int) -> str:
    comment = f"{count} {noun} superan las {threshold} palabras (la más extensa tiene {longest})."
    if count > MAX_REPORTED_PER_RULE:
        comment += f" Se listan las {MAX_REPORTED_PER_RULE} más extensas."
    return comment


# --- Tarea #25: Consignas Multi-Acción ---------------------------------------

_ACTION_VERBS = {
    # Infinitivos
    "leer", "escribir", "subrayar", "responder", "analizar", "dibujar", "calcular",
    "comparar", "sintetizar", "completar", "unir", "marcar", "explicar", "relacionar",
    "identificar", "caracterizar", "justificar", "clasificar", "ordenar", "confeccionar",
    "elaborar", "desarrollar", "buscar", "seleccionar", "copiar", "armar", "resolver",
    "realizar", "redactar", "preparar", "exponer", "resumir", "extraer", "indicar",
    "mencionar", "describir", "definir", "graficar", "enumerar", "diferenciar", "anotar",
    # Imperativo voseo
    "leé", "escribí", "subrayá", "respondé", "analizá", "dibujá", "calculá",
    "compará", "sintetizá", "completá", "uní", "marcá", "explicá", "relacioná",
    "identificá", "caracterizá", "justificá", "clasificá", "ordená", "confeccioná",
    "elaborá", "desarrollá", "buscá", "seleccioná", "copiá", "armá", "resolvé",
    "realizá", "redactá", "prepará", "exponé", "resumí", "extraé", "indicá",
    "mencioná", "describí", "definí", "graficá", "enumerá", "diferenciá", "anotá",
    # Imperativo tuteo
    "lee", "escribe", "subraya", "responde", "analiza", "dibuja", "calcula",
    "compara", "sintetiza", "completa", "une", "marca", "explica", "relaciona",
    "identifica", "caracteriza", "justifica", "clasifica", "ordena", "confecciona",
    "elabora", "desarrolla", "busca", "selecciona", "copia", "arma", "resuelve",
    "realiza", "redacta", "prepara", "resume", "extrae", "indica",
    "menciona", "describe", "define", "grafica", "enumera", "diferencia", "anota",
    # Subjuntivo plural / ustedes / ellos
    "lean", "escriban", "subrayen", "respondan", "analicen", "dibujen", "calculen",
    "comparen", "sinteticen", "completen", "unan", "marquen", "expliquen", "relacionen",
    "identifiquen", "caractericen", "justifiquen", "clasifiquen", "ordenen", "confeccionen",
    "elaboren", "desarrollen", "busquen", "seleccionen", "copien", "armen", "resuelvan",
    "realicen", "redacten", "preparen", "expongan", "resuman", "extraigan", "indiquen",
    "mencionen", "describan", "definan", "grafiquen", "enumeren", "diferencien", "anoten",
    # Subjuntivo usted
    "lea", "escriba", "subraye", "responda", "analice", "dibuje", "calcule",
    "compare", "sintetice", "complete", "una", "marque", "explique", "relacione",
    "identifique", "caracterice", "justifique", "clasifique", "ordene", "confeccione",
    "elabore", "desarrolle", "busque", "seleccione", "copie", "arme", "resuelva",
    "realice", "redacte", "prepare", "exponga", "resuma", "extraiga", "indique",
    "mencione", "describa", "defina", "grafique", "enumere", "diferencie", "anote",
}


def _multi_action_findings(sentences: list[tuple[str, int]]) -> list[RuleFinding]:
    """Identifica consignas que encadenan 3 o más verbos de acción en una misma oración."""
    findings = []
    for sentence, words in sentences:
        tokens = [w.lower() for w in _WORD_RE.findall(sentence)]
        action_verbs_found = [w for w in tokens if w in _ACTION_VERBS]
        count = len(action_verbs_found)
        if count >= MULTI_ACTION_WARN_THRESHOLD:
            severity = "barrera_detectada" if count >= MULTI_ACTION_SEVERE_THRESHOLD else "para_revisar"
            verbs_str = ", ".join(dict.fromkeys(action_verbs_found))
            findings.append(
                RuleFinding(
                    barrier={
                        "category": "comprension",
                        "severity": severity,
                        "issue": f"Consigna con múltiples acciones ({count} acciones simultáneas)",
                        "original_text": _excerpt(sentence, 30),
                        "explanation": (
                            f"La oración encadena {count} acciones ({verbs_str}). "
                            "Exigir varias tareas cognitivas en una misma instrucción sobrecarga la memoria de trabajo "
                            "y dificulta el seguimiento secuencial de la tarea."
                        ),
                        "recommendation": (
                            "Dividí la consigna en una lista numerada o con viñetas, "
                            "donde cada punto exprese una única acción concreta."
                        ),
                        "suggested_rewrite": None,
                        "fragment_found": True,
                        "source": "rules",
                    },
                    anchor=sentence,
                )
            )
    return findings[:MAX_REPORTED_PER_RULE]


# --- Tarea #25: Legibilidad Szigriszt-Pazos (IFSZ) --------------------------

def count_syllables_es(word: str) -> int:
    """
    Cuenta las sílabas de una palabra en español de forma determinista y sin dependencias externas.
    Modela núcleos vocálicos, diptongos, triptongos e hiatos con tilde.
    """
    w = word.lower().strip()
    w = re.sub(r"[^a-záéíóúüñ]", "", w)
    if not w:
        return 0
    if len(w) <= 2:
        return 1

    # 'y' al final de palabra actúa como vocal
    w = re.sub(r"y$", "i", w)
    # Triptongos (débil + fuerte + débil) -> 1 núcleo
    w = re.sub(r"[iuü][aáeéoó][iuü]", "a", w)
    # Diptongos (fuerte + débil átona, débil átona + fuerte, o dos débiles distintas) -> 1 núcleo
    w = re.sub(r"[aáeéoó][iuü]", "a", w)
    w = re.sub(r"[iuü][aáeéoó]", "a", w)
    w = re.sub(r"[iuü]{2}", "a", w)

    # Cada vocal restante representa un núcleo silábico
    vowels = re.findall(r"[aeiouáéíóúü]", w)
    return max(1, len(vowels))


def calculate_szigriszt_pazos(raw_text: str, sentences: list[tuple[str, int]]) -> float | None:
    """
    Calcula el Índice de Flesch-Szigriszt (IFSZ) adaptado al español:
    IFSZ = 206.835 - 62.3 * (sílabas / palabras) - (palabras / oraciones)
    Solo se calcula para textos de 100 o más palabras para evitar distorsiones.
    """
    words = [w for w in _WORD_RE.findall(raw_text) if not w.isdigit()]
    if len(words) < MIN_WORDS_FOR_READABILITY or not sentences:
        return None

    total_syllables = sum(count_syllables_es(w) for w in words)
    num_words = len(words)
    num_sentences = max(1, len(sentences))

    ifsz = 206.835 - 62.3 * (total_syllables / num_words) - (num_words / num_sentences)
    return round(ifsz, 1)


def _readability_findings(ifsz: float | None) -> list[RuleFinding]:
    """Genera una barrera de comprensión si el índice de legibilidad Szigriszt-Pazos es bajo (<50)."""
    if ifsz is None or ifsz >= READABILITY_WARN_THRESHOLD:
        return []

    is_severe = ifsz < READABILITY_SEVERE_THRESHOLD
    severity = "barrera_detectada" if is_severe else "para_revisar"
    nivel = "Muy difícil" if is_severe else "Algo difícil"

    return [
        RuleFinding(
            barrier={
                "category": "comprension",
                "severity": severity,
                "issue": f"Índice de legibilidad bajo (Szigriszt-Pazos: {ifsz:.1f} - {nivel})",
                "original_text": f"[Evaluación global de legibilidad: IFSZ {ifsz:.1f}]",
                "explanation": (
                    f"El material obtuvo un índice Szigriszt-Pazos de {ifsz:.1f} ({nivel}). "
                    "Una alta densidad de sílabas por palabra combinada con oraciones extensas "
                    "dificulta la lectura fluida y la comprensión global del texto."
                ),
                "recommendation": (
                    "Utilizá vocabulario más cotidiano, evitá términos excesivamente largos "
                    "y acortá la longitud promedio de las oraciones."
                ),
                "suggested_rewrite": None,
                "fragment_found": None,
                "source": "rules",
            },
            anchor=None,
        )
    ]


# --- Tarea #25: Referencias puramente visuales (WCAG 1.3.3) -----------------

_VISUAL_REF_PATTERNS = [
    re.compile(
        r"\b(?:ver|observar|observ[aá]|mirar|mir[aá]|como se (?:muestra|ve) en|en el|en la)\s+(?:(?:el|la|los|las)\s+)?(?:gr[aá]fico|imagen|figura|cuadro|tabla)?\s*(?:de la derecha|de la izquierda|de arriba|de abajo|a la derecha|a la izquierda|superior|inferior)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:a la derecha|a la izquierda|en la parte superior|en la parte inferior)\s+(?:se (?:muestra|ve|observa)|podemos ver)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:el|la|los|las)\s+(?:cuadro|bot[oó]n|bloque|caja|c[ií]rculo|recuadro|flecha|texto)\s+(?:rojo|verde|azul|amarillo|circular|destacad[oa]|resaltad[oa])\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:observa|observ[aá]|mira|mir[aá]|miren)\s+(?:la imagen|el gr[aá]fico|la figura|la foto)\s+(?:para|y)\s+(?:responder|resolver|completar|contestar)\b",
        re.IGNORECASE,
    ),
]


def _visual_reference_findings(raw_text: str) -> list[RuleFinding]:
    """Detecta referencias que dependen exclusivamente de la ubicación espacial o apariencia visual (WCAG 1.3.3)."""
    matches = []
    seen = set()
    for pattern in _VISUAL_REF_PATTERNS:
        for m in pattern.finditer(raw_text):
            frag = m.group().strip()
            if frag.lower() not in seen:
                seen.add(frag.lower())
                matches.append(frag)

    findings = []
    for frag in matches[:MAX_REPORTED_PER_RULE]:
        findings.append(
            RuleFinding(
                barrier={
                    "category": "accesibilidad_visual",
                    "severity": "para_revisar",
                    "issue": "Referencia basada únicamente en la posición o aspecto visual",
                    "original_text": frag,
                    "explanation": (
                        f"La expresión '{frag}' utiliza únicamente la ubicación espacial o una característica "
                        "visual para transmitir información. Esto genera una barrera para estudiantes que utilizan "
                        "lectores de pantalla o presentan discapacidad visual (WCAG 1.3.3)."
                    ),
                    "recommendation": (
                        "Acompañá la referencia con un título descriptivo, numeración (ej. 'Figura 2') "
                        "o una explicación textual del contenido al que se hace referencia."
                    ),
                    "suggested_rewrite": None,
                    "fragment_found": True,
                    "source": "rules",
                },
                anchor=frag,
            )
        )
    return findings


def visual_assessment(doc: ExtractedDocument) -> tuple[DimensionAssessment, list[dict]]:
    """Accesibilidad visual por reglas: la IA solo recibe texto y no ve las imágenes."""
    if doc.is_scanned_pdf:
        return (
            DimensionAssessment(
                category="accesibilidad_visual",
                status="barrera_detectada",
                comment="El PDF parece escaneado: el texto no es seleccionable ni legible por lectores de pantalla.",
            ),
            [
                {
                    "category": "accesibilidad_visual",
                    "severity": "barrera_detectada",
                    "issue": "PDF escaneado sin capa de texto",
                    "original_text": f"[Documento completo: {doc.filename or 'PDF'}]",
                    "explanation": (
                        "Las páginas son imágenes: los lectores de pantalla no pueden leerlas "
                        "y el estudiante no puede ampliar, copiar ni buscar el texto."
                    ),
                    "recommendation": "Compartí el material original digital o aplicale OCR antes de distribuirlo.",
                    "suggested_rewrite": None,
                    "fragment_found": None,
                    "source": "rules",
                }
            ],
        )
    if doc.has_images:
        return (
            DimensionAssessment(
                category="accesibilidad_visual",
                status="para_revisar",
                comment=f"Se detectaron {doc.image_count} imagen(es); su accesibilidad no puede verificarse automáticamente.",
            ),
            [
                {
                    "category": "accesibilidad_visual",
                    "severity": "para_revisar",
                    "issue": "Imágenes sin descripción verificable",
                    "original_text": f"[{doc.image_count} imagen(es) en el documento]",
                    "explanation": (
                        "Si las imágenes transmiten información necesaria para la tarea, un estudiante "
                        "con discapacidad visual no podrá acceder a ella sin texto alternativo."
                    ),
                    "recommendation": (
                        "Agregá una descripción breve (texto alternativo) a cada imagen que aporte "
                        "información, o explicá su contenido en el texto."
                    ),
                    "suggested_rewrite": None,
                    "fragment_found": None,
                    "source": "rules",
                }
            ],
        )
    return (
        DimensionAssessment(
            category="accesibilidad_visual",
            status="correcta",
            comment="No se detectaron imágenes en el material.",
        ),
        [],
    )


def _structure_findings(
    doc: ExtractedDocument,
) -> tuple[list[RuleFinding], list[ScorePenalty], list[str]]:
    """
    Evalúa la estructura tipográfica de títulos y secciones en documentos PDF.
    El texto pegado (source_type == "text") no se penaliza por falta de fuentes.
    """
    findings: list[RuleFinding] = []
    penalties: list[ScorePenalty] = []
    comments: list[str] = []

    if doc.source_type != "pdf" or doc.is_scanned_pdf:
        return findings, penalties, comments

    structure = getattr(doc, "structure", None)
    if not structure:
        return findings, penalties, comments

    # Regla 1: Falta total de títulos en documentos extensos (>= 150 palabras)
    if doc.word_count >= MIN_WORDS_FOR_HEADING_RULE and not structure.has_headings:
        findings.append(
            RuleFinding(
                barrier={
                    "category": "estructura",
                    "severity": "barrera_detectada",
                    "issue": "Documento extenso sin títulos ni estructura definida",
                    "original_text": f"[{doc.filename or 'Documento PDF'}: {doc.page_count} página(s), {doc.word_count} palabras]",
                    "explanation": (
                        "El documento no presenta encabezados ni títulos diferenciados por tamaño o estilo tipográfico. "
                        "Sin una jerarquía visual y estructural, los estudiantes se enfrentan a un bloque continuo "
                        "de texto y las tecnologías de asistencia (como lectores de pantalla) no pueden navegar por secciones."
                    ),
                    "recommendation": (
                        "Incorporá títulos principales (H1) y subtítulos de sección (H2) utilizando fuentes de mayor "
                        "tamaño y en negrita para organizar los temas y actividades."
                    ),
                    "suggested_rewrite": None,
                    "fragment_found": None,
                    "source": "rules",
                },
                anchor=None,
            )
        )
        penalties.append(
            ScorePenalty(
                rule="pdf_sin_titulos",
                category="estructura",
                count=1,
                points=NO_HEADINGS_PENALTY,
            )
        )
        comments.append("El documento no contiene títulos ni subtítulos estructurados.")

    # Regla 2: Salto de jerarquía en títulos (ej. H1 a H3 sin H2)
    if structure.has_headings and len(structure.headings) >= 2:
        skips = []
        for i in range(len(structure.headings) - 1):
            h_curr = structure.headings[i]
            h_next = structure.headings[i + 1]
            if h_next.level > h_curr.level + 1:
                skips.append((h_curr, h_next))

        for h_curr, h_next in skips[:2]:
            findings.append(
                RuleFinding(
                    barrier={
                        "category": "estructura",
                        "severity": "para_revisar",
                        "issue": f"Salto de jerarquía en títulos (de H{h_curr.level} a H{h_next.level})",
                        "original_text": h_next.text,
                        "explanation": (
                            f"Se detectó un salto jerárquico pasando del nivel H{h_curr.level} directamente al "
                            f"nivel H{h_next.level} sin incluir un nivel intermedio (H{h_curr.level + 1}). "
                            "Las pautas de accesibilidad establecen que los encabezados deben anidarse en secuencia lógica "
                            "para facilitar la orientación en el material."
                        ),
                        "recommendation": (
                            f"Ajustá el nivel del encabezado '{h_next.text}' para que sea H{h_curr.level + 1} "
                            "o agregá la sección intermedia correspondiente."
                        ),
                        "suggested_rewrite": None,
                        "fragment_found": True,
                        "source": "rules",
                    },
                    anchor=h_next.text,
                )
            )

        if skips:
            penalties.append(
                ScorePenalty(
                    rule="salto_jerarquia_titulos",
                    category="estructura",
                    count=len(skips),
                    points=min(12, HIERARCHY_SKIP_PENALTY * len(skips)),
                )
            )
            comments.append(f"Se detectaron {len(skips)} salto(s) en la jerarquía de títulos.")

    # Regla 3: Bloques o secciones extensas sin divisiones entre títulos
    if structure.has_headings:
        heading_texts = {h.text.strip().lower() for h in structure.headings}
        current_section_words = 0
        current_heading_text = structure.headings[0].text if structure.headings else None
        long_sections = []

        for p in split_paragraphs(doc.raw_text):
            p_clean = p.strip().lower()
            if any(h in p_clean or p_clean in h for h in heading_texts):
                if current_section_words > LONG_SECTION_WORDS and current_heading_text:
                    long_sections.append((current_heading_text, current_section_words))
                current_section_words = 0
                current_heading_text = p.strip()
            else:
                current_section_words += count_words(p)

        if current_section_words > LONG_SECTION_WORDS and current_heading_text:
            long_sections.append((current_heading_text, current_section_words))

        for sec_head, sec_w in long_sections[:MAX_REPORTED_PER_RULE]:
            findings.append(
                RuleFinding(
                    barrier={
                        "category": "estructura",
                        "severity": "para_revisar",
                        "issue": f"Sección extensa sin subdivisiones ({sec_w} palabras)",
                        "original_text": _excerpt(sec_head, 15),
                        "explanation": (
                            f"La sección '{sec_head}' concentra {sec_w} palabras consecutivas sin títulos o "
                            f"subdivisiones intermedias. Mantener más de {LONG_SECTION_WORDS} palabras bajo un mismo "
                            "encabezado dificulta la lectura focalizada y la retención."
                        ),
                        "recommendation": "Dividí la sección en subapartados temáticos o incorporá listas para estructurar el contenido.",
                        "suggested_rewrite": None,
                        "fragment_found": True,
                        "source": "rules",
                    },
                    anchor=sec_head,
                )
            )

        if long_sections:
            penalties.append(
                ScorePenalty(
                    rule="secciones_extensas",
                    category="estructura",
                    count=len(long_sections),
                    points=min(10, LONG_SECTION_PENALTY * len(long_sections)),
                )
            )
            comments.append(f"{len(long_sections)} sección(es) superan las {LONG_SECTION_WORDS} palabras sin subdivisiones.")

    return findings, penalties, comments


def _penalties(
    metrics: RulesMetrics,
    doc: ExtractedDocument,
    structure_penalties: list[ScorePenalty],
    multi_action_count: int,
    ifsz: float | None,
    visual_ref_count: int,
) -> list[ScorePenalty]:
    penalties = []
    if metrics.long_sentences:
        ratio_points = round(100 * metrics.long_sentences / metrics.sentence_count)
        points = ratio_points + SEVERE_SENTENCE_EXTRA_POINTS * metrics.severe_long_sentences
        penalties.append(ScorePenalty(
            rule="oraciones_extensas", category="comprension",
            count=metrics.long_sentences, points=min(MAX_SENTENCE_PENALTY, points),
        ))
    if metrics.long_paragraphs:
        moderate = metrics.long_paragraphs - metrics.severe_long_paragraphs
        points = LONG_PARAGRAPH_POINTS * moderate + SEVERE_PARAGRAPH_POINTS * metrics.severe_long_paragraphs
        penalties.append(ScorePenalty(
            rule="parrafos_extensos", category="estructura",
            count=metrics.long_paragraphs, points=min(MAX_PARAGRAPH_PENALTY, points),
        ))
    if doc.is_scanned_pdf:
        penalties.append(ScorePenalty(
            rule="pdf_escaneado", category="accesibilidad_visual", count=1, points=SCANNED_PDF_POINTS,
        ))
    elif doc.has_images:
        penalties.append(ScorePenalty(
            rule="imagenes_sin_verificar", category="accesibilidad_visual",
            count=doc.image_count, points=IMAGES_POINTS,
        ))
    penalties.extend(structure_penalties)

    # Tarea #25: Consignas multi-acción
    if multi_action_count > 0:
        penalties.append(ScorePenalty(
            rule="consignas_multiaccion",
            category="comprension",
            count=multi_action_count,
            points=min(MAX_MULTI_ACTION_PENALTY, MULTI_ACTION_PENALTY_POINTS * multi_action_count),
        ))

    # Tarea #25: Legibilidad baja (Szigriszt-Pazos)
    if ifsz is not None and ifsz < READABILITY_WARN_THRESHOLD:
        pts = READABILITY_SEVERE_POINTS if ifsz < READABILITY_SEVERE_THRESHOLD else READABILITY_WARN_POINTS
        penalties.append(ScorePenalty(
            rule="legibilidad_baja",
            category="comprension",
            count=1,
            points=pts,
        ))

    # Tarea #25: Referencias puramente visuales
    if visual_ref_count > 0:
        penalties.append(ScorePenalty(
            rule="referencias_visuales",
            category="accesibilidad_visual",
            count=visual_ref_count,
            points=min(MAX_VISUAL_REF_PENALTY, VISUAL_REF_PENALTY_POINTS * visual_ref_count),
        ))

    return penalties


def run_rules(doc: ExtractedDocument) -> RulesResult:
    """Aplica todas las reglas al texto completo del documento (raw_text, no el recortado)."""
    paragraphs = [(p, count_words(p)) for p in split_paragraphs(doc.raw_text)]
    sentences = [(s, count_words(s)) for p, _ in paragraphs for s in split_sentences(p)]
    sentences = [s for s in sentences if s[1] > 0]

    long_sentences = [w for _, w in sentences if w > LONG_SENTENCE_WORDS]
    severe_sentences = [w for w in long_sentences if w >= SEVERE_SENTENCE_WORDS]
    long_paragraphs = [w for _, w in paragraphs if w > LONG_PARAGRAPH_WORDS]
    severe_paragraphs = [w for w in long_paragraphs if w >= SEVERE_PARAGRAPH_WORDS]

    struct_findings, struct_penalties, struct_comments = _structure_findings(doc)

    # Tarea #25: Consignas multi-acción
    multi_action_findings = _multi_action_findings(sentences)

    # Tarea #25: Legibilidad Szigriszt-Pazos
    ifsz = calculate_szigriszt_pazos(doc.raw_text, sentences)
    readability_findings = _readability_findings(ifsz)

    # Tarea #25: Referencias puramente visuales
    visual_ref_findings = _visual_reference_findings(doc.raw_text)

    metrics = RulesMetrics(
        analyzed_word_count=count_words(doc.raw_text),
        sentence_count=len(sentences),
        long_sentences=len(long_sentences),
        severe_long_sentences=len(severe_sentences),
        max_sentence_words=max((w for _, w in sentences), default=0),
        paragraph_count=len(paragraphs),
        long_paragraphs=len(long_paragraphs),
        severe_long_paragraphs=len(severe_paragraphs),
        heading_count=len(doc.structure.headings) if hasattr(doc, "structure") else 0,
        hierarchy_levels=doc.structure.hierarchy_levels if hasattr(doc, "structure") else 0,
        list_items_count=doc.structure.list_items_count if hasattr(doc, "structure") else 0,
        multi_action_prompts=len(multi_action_findings),
        readability_score_szigriszt=ifsz,
        visual_only_references=len(visual_ref_findings),
    )

    # Dimensión Comprensión
    comp_severe = (
        len(severe_sentences)
        + sum(1 for f in multi_action_findings if f.barrier["severity"] == "barrera_detectada")
        + sum(1 for f in readability_findings if f.barrier["severity"] == "barrera_detectada")
    )
    comp_moderate = len(long_sentences) + len(multi_action_findings) + len(readability_findings)

    if comp_moderate > 0:
        comp_comments = []
        if long_sentences:
            comp_comments.append(_count_comment(len(long_sentences), "oración(es)", LONG_SENTENCE_WORDS, max(long_sentences)))
        if multi_action_findings:
            comp_comments.append(f"{len(multi_action_findings)} consigna(s) encadenan múltiples acciones simultáneas.")
        if readability_findings:
            comp_comments.append(f"Índice de legibilidad Szigriszt-Pazos: {ifsz:.1f}.")
        comprension = DimensionAssessment(
            category="comprension",
            status=_worst_severity(comp_severe),
            comment=" ".join(comp_comments),
        )
    else:
        comprension = DimensionAssessment(
            category="comprension",
            status="correcta",
            comment=f"No se detectaron oraciones de más de {LONG_SENTENCE_WORDS} palabras ni consignas complejas.",
        )

    # Dimensión Estructura
    struct_severe = len(severe_paragraphs) + sum(
        1 for f in struct_findings if f.barrier["severity"] == "barrera_detectada"
    )
    struct_moderate = len(long_paragraphs) + len(struct_findings)

    if struct_moderate > 0:
        struct_comment_parts = []
        if long_paragraphs:
            struct_comment_parts.append(_count_comment(len(long_paragraphs), "párrafo(s)", LONG_PARAGRAPH_WORDS, max(long_paragraphs)))
        if struct_comments:
            struct_comment_parts.extend(struct_comments)
        estructura = DimensionAssessment(
            category="estructura",
            status=_worst_severity(struct_severe),
            comment=" ".join(struct_comment_parts),
        )
    elif doc.source_type == "pdf" and getattr(doc, "structure", None) and doc.structure.has_headings:
        estructura = DimensionAssessment(
            category="estructura",
            status="correcta",
            comment=f"Estructura organizada con {len(doc.structure.headings)} encabezados y {doc.structure.hierarchy_levels} nivel(es) de jerarquía.",
        )
    else:
        estructura = DimensionAssessment(
            category="estructura",
            status="correcta",
            comment=f"No se detectaron párrafos de más de {LONG_PARAGRAPH_WORDS} palabras sin división.",
        )

    # Dimensión Visual
    visual, visual_barriers = visual_assessment(doc)
    if visual_ref_findings:
        visual_barriers.extend(f.barrier for f in visual_ref_findings)
        worst_vis = worst_status(
            visual.status,
            "barrera_detectada" if len(visual_ref_findings) >= 3 else "para_revisar",
        )
        visual = DimensionAssessment(
            category="accesibilidad_visual",
            status=worst_vis,
            comment=f"{visual.comment} Se detectaron {len(visual_ref_findings)} referencia(s) que dependen de la posición o aspecto visual.",
        )

    findings = (
        _long_sentence_findings(sentences)
        + multi_action_findings
        + readability_findings
        + _long_paragraph_findings(paragraphs)
        + struct_findings
        + [RuleFinding(barrier=b) for b in visual_barriers]
    )
    return RulesResult(
        findings=findings,
        dimensions=[comprension, estructura, visual],
        metrics=metrics,
        is_scanned_pdf=doc.is_scanned_pdf,
        has_images=doc.has_images,
        image_count=doc.image_count,
        has_text=bool(doc.raw_text.strip()),
        penalties=_penalties(
            metrics,
            doc,
            struct_penalties,
            len(multi_action_findings),
            ifsz,
            len(visual_ref_findings),
        ),
    )


def worst_status(a: str, b: str) -> str:
    return a if _SEVERITY_ORDER[a] >= _SEVERITY_ORDER[b] else b


def compute_score(ai_score: int | None, rules: RulesResult) -> ScoreBreakdown:
    """
    Pondera el puntaje de la IA con el de reglas en lugar de restarle penalizaciones:
    la IA ya considera la longitud de las oraciones, y restar contaría dos veces lo mismo.
    Sin IA (p. ej. PDF sin texto), el puntaje final es el de reglas.
    """
    rules_score = max(0, 100 - sum(p.points for p in rules.penalties))
    if ai_score is None:
        combined = rules_score
    else:
        combined = round(AI_WEIGHT * max(0, min(100, ai_score)) + RULES_WEIGHT * rules_score)

    cap, cap_reason = None, None
    if not rules.has_text:
        cap, cap_reason = NO_TEXT_CAP, "El material no tiene texto digital analizable."
    elif rules.is_scanned_pdf:
        cap, cap_reason = SCANNED_CAP, "El PDF parece escaneado: su texto no es accesible."
    elif any(f.barrier["severity"] == "barrera_detectada" for f in rules.findings):
        cap, cap_reason = SEVERE_BARRIER_CAP, "Las reglas automáticas detectaron al menos una barrera grave."
    if cap is not None and combined <= cap:
        cap, cap_reason = None, None  # solo se informa el tope que efectivamente recortó

    return ScoreBreakdown(
        ai_score=ai_score,
        rules_score=rules_score,
        ai_weight=AI_WEIGHT if ai_score is not None else 0.0,
        rules_weight=RULES_WEIGHT if ai_score is not None else 1.0,
        penalties=rules.penalties,
        cap=cap,
        cap_reason=cap_reason,
        final_score=min(combined, cap) if cap is not None else combined,
    )
