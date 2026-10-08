import asyncio

import pymupdf
import pytest

from app.schemas.document import ExtractedDocument
from app.services import rules_service as rs
from app.services.accessibility_service import (
    _AIPart,
    _ai_covers,
    _build_response,
    analyze_document,
)
from app.services.document_service import document_service


def _words(n: int, word: str = "palabra") -> str:
    return " ".join([word] * n)


def _doc(text: str, **kwargs) -> ExtractedDocument:
    return ExtractedDocument(
        source_type=kwargs.pop("source_type", "text"),
        raw_text=text,
        text_for_analysis=text,
        word_count=rs.count_words(text),
        character_count=len(text),
        **kwargs,
    )


# --- Separación de oraciones ------------------------------------------------


@pytest.mark.parametrize(
    "paragraph, expected",
    [
        ("Leé el texto. Respondé las preguntas.", ["Leé el texto.", "Respondé las preguntas."]),
        ("¿Qué es un ecosistema? Explicalo.", ["¿Qué es un ecosistema?", "Explicalo."]),
        ("Ver pág. 8 y el ej. 3 del libro.", ["Ver pág. 8 y el ej. 3 del libro."]),
        ("El pH es 3.5 en la muestra. Anotalo.", ["El pH es 3.5 en la muestra.", "Anotalo."]),
        ("Lo escribió J. Pérez en 1990. Leelo.", ["Lo escribió J. Pérez en 1990.", "Leelo."]),
        ("Traé lápices, gomas, etc. y una regla.", ["Traé lápices, gomas, etc. y una regla."]),
        ("1. Leé el texto.\n2. Respondé.", ["1. Leé el texto.", "2. Respondé."]),
        ("Parte 1: Introducción\nEn esta unidad vamos a estudiar.", ["Parte 1: Introducción", "En esta unidad vamos a estudiar."]),
        ("Esperá… Ahora sí.", ["Esperá…", "Ahora sí."]),
        ('Dijo "vení." Después se fue.', ['Dijo "vení."', "Después se fue."]),
    ],
)
def test_split_sentences(paragraph, expected):
    assert rs.split_sentences(paragraph) == expected


def test_split_paragraphs_ignores_blank_lines():
    assert rs.split_paragraphs("Título\n\n  Primer párrafo.  \n\n\nSegundo.") == [
        "Título", "Primer párrafo.", "Segundo."
    ]


# --- Umbrales ---------------------------------------------------------------


def test_sentence_threshold_boundaries():
    text = "\n".join([
        _words(rs.LONG_SENTENCE_WORDS) + ".",          # 35: no es extensa
        _words(rs.LONG_SENTENCE_WORDS + 1) + ".",      # 36: para_revisar
        _words(rs.SEVERE_SENTENCE_WORDS) + ".",        # 50: barrera_detectada
    ])
    result = rs.run_rules(_doc(text))
    assert result.metrics.long_sentences == 2
    assert result.metrics.severe_long_sentences == 1
    sentence_findings = [f for f in result.findings if "Oración extensa" in f.barrier["issue"]]
    severities = sorted(f.barrier["severity"] for f in sentence_findings)
    assert severities == ["barrera_detectada", "para_revisar"]
    assert result.dimensions[0].status == "barrera_detectada"


def test_paragraph_threshold_boundaries():
    short_sentences = lambda n: " ".join(["Una oración corta de cinco."] * (n // 5))
    text = "\n\n".join([
        short_sentences(rs.LONG_PARAGRAPH_WORDS),          # 150: no es muro
        short_sentences(rs.LONG_PARAGRAPH_WORDS + 5),      # 155: para_revisar
    ])
    result = rs.run_rules(_doc(text))
    assert result.metrics.long_paragraphs == 1
    assert result.metrics.long_sentences == 0
    (finding,) = result.findings
    assert finding.barrier["category"] == "estructura"
    assert finding.barrier["severity"] == "para_revisar"
    assert finding.barrier["original_text"].endswith(" …")
    assert finding.anchor.startswith(finding.barrier["original_text"][:-2])
    assert result.dimensions[1].status == "para_revisar"


def test_reported_barriers_are_capped_and_longest_first():
    text = "\n".join(_words(40 + i) + "." for i in range(6))
    result = rs.run_rules(_doc(text))
    assert result.metrics.long_sentences == 6
    sentence_findings = [f for f in result.findings if "Oración extensa" in f.barrier["issue"]]
    assert len(sentence_findings) == rs.MAX_REPORTED_PER_RULE
    assert sentence_findings[0].barrier["issue"] == "Oración extensa (45 palabras)"
    assert "Se listan las 3 más extensas" in result.dimensions[0].comment


def test_clear_text_has_no_findings():
    result = rs.run_rules(_doc("Leé el texto.\nRespondé las preguntas.\nEntregá el viernes."))
    assert result.findings == []
    assert [d.status for d in result.dimensions] == ["correcta"] * 3
    assert result.penalties == []


# --- Puntaje ----------------------------------------------------------------


def test_score_combines_ai_and_rules():
    result = rs.run_rules(_doc(_words(40) + ".\nFrase corta."))  # 1 de 2 oraciones: 50 pts -> tope 30
    breakdown = rs.compute_score(80, result)
    assert breakdown.rules_score == 70
    assert breakdown.final_score == round(0.7 * 80 + 0.3 * 70)
    assert breakdown.cap is None


def test_score_caps_with_severe_barrier():
    result = rs.run_rules(_doc(_words(60) + ".\n" + "\n".join(["Frase corta."] * 30)))
    breakdown = rs.compute_score(100, result)
    assert breakdown.final_score == rs.SEVERE_BARRIER_CAP
    assert breakdown.cap == rs.SEVERE_BARRIER_CAP


def test_score_scanned_pdf_without_text():
    doc = _doc("", source_type="pdf", is_scanned_pdf=True)
    breakdown = rs.compute_score(None, rs.run_rules(doc))
    assert breakdown.ai_score is None
    assert breakdown.rules_weight == 1.0
    assert breakdown.final_score == rs.NO_TEXT_CAP


def test_score_images_penalty():
    doc = _doc("Observá la imagen.", source_type="pdf", has_images=True, image_count=2)
    breakdown = rs.compute_score(90, rs.run_rules(doc))
    assert [(p.rule, p.points) for p in breakdown.penalties] == [("imagenes_sin_verificar", rs.IMAGES_POINTS)]


# --- Unión con la IA --------------------------------------------------------

LONG_SENTENCE = (
    "Luego de haber realizado la lectura completa del cuento que trabajamos en clase durante "
    "la semana pasada deberán identificar a los personajes principales y secundarios, describir "
    "el espacio donde transcurre la historia y explicar con sus propias palabras cuál es el conflicto."
)


def _ai_barrier(fragment: str, category: str = "comprension", found: bool = True) -> dict:
    return {
        "category": category, "severity": "para_revisar", "issue": "x", "original_text": fragment,
        "explanation": "x", "recommendation": "x", "suggested_rewrite": "Reescritura.",
        "fragment_found": found, "source": "ai",
    }


def _ai_part(barriers: list[dict]) -> _AIPart:
    return _AIPart(score=80, summary="Resumen.", dimensions=[], strengths=[], barriers=barriers)


def test_ai_barrier_on_same_sentence_replaces_rule_barrier():
    doc = _doc(LONG_SENTENCE)
    rules = rs.run_rules(doc)
    ai = _ai_part([_ai_barrier("deberán identificar a los personajes principales y secundarios")])
    response = _build_response(doc, ai, rules, warnings=[], **_meta())
    assert [b.source for b in response.barriers] == ["ai"]
    # La regla sigue pesando en el puntaje aunque su barrera no se liste.
    assert response.score_breakdown.penalties[0].rule == "oraciones_extensas"


def test_unverified_or_unrelated_ai_barrier_does_not_replace_rule():
    rules = rs.run_rules(_doc(LONG_SENTENCE))
    finding = next(f for f in rules.findings if "Oración extensa" in f.barrier["issue"])
    assert not _ai_covers(_ai_barrier("deberán identificar a los personajes", found=False), finding)
    assert not _ai_covers(_ai_barrier("un fragmento que no está en la oración larga"), finding)


def test_paragraph_rule_only_covered_by_structure_barrier_on_its_opening():
    paragraph = "Al comienzo del bloque se presenta el tema. " + " ".join(["Una oración corta de cinco."] * 32)
    (finding,) = rs.run_rules(_doc(paragraph)).findings
    opening = "Al comienzo del bloque se presenta el tema."
    middle = "Una oración corta de cinco. Una oración corta de cinco."
    assert not _ai_covers(_ai_barrier(opening, category="comprension"), finding)
    assert not _ai_covers(_ai_barrier(middle, category="estructura"), finding)
    assert _ai_covers(_ai_barrier(opening, category="estructura"), finding)


def test_dimensions_take_worst_status_and_ids_are_sequential():
    doc = _doc(_words(rs.SEVERE_SENTENCE_WORDS) + ".\nOtra frase corta.")
    rules = rs.run_rules(doc)
    ai = _AIPart(
        score=90, summary="Resumen.", strengths=[],
        dimensions=[
            rs.DimensionAssessment(category="comprension", status="correcta", comment="Claro."),
            rs.DimensionAssessment(category="estructura", status="correcta", comment="Ordenado."),
        ],
        barriers=[_ai_barrier("Otra frase corta del todo inexistente")],
    )
    response = _build_response(doc, ai, rules, warnings=[], **_meta())
    status = {d.category: d.status for d in response.dimensions}
    assert status == {"comprension": "barrera_detectada", "estructura": "correcta", "accesibilidad_visual": "correcta"}
    assert "Reglas automáticas:" in response.dimensions[0].comment
    # La barrera grave de reglas va antes que la de IA para_revisar.
    assert [(b.id, b.source) for b in response.barriers] == [("bar-1", "rules"), ("bar-2", "ai")]


def _meta() -> dict:
    return dict(
        provider="test", model="test", connection="test", latency_ms=0,
        analyzed_word_count=0, is_truncated=False, unverified_fragments=0,
    )


def test_mock_runs_real_rules():
    # La oración larga no va primera: el mock cita la primera y cubriría la barrera de reglas.
    doc = document_service.process_text("Leé el texto.\n" + LONG_SENTENCE)
    response = asyncio.run(analyze_document(doc, mock=True))
    assert response.metadata.provider == "mock"
    assert response.metadata.rules_metrics.long_sentences == 1
    assert response.score_breakdown.ai_score == 68
    assert response.estimated_score == response.score_breakdown.final_score
    assert any(b.source == "rules" for b in response.barriers)


# --- Párrafos de PDF --------------------------------------------------------


def test_pdf_paragraphs_are_reflowed_by_block():
    pdf = pymupdf.open()
    page = pdf.new_page()
    long_paragraph = "Primer párrafo con varias oraciones que ocupan más de un renglón al imprimirse. " * 3
    page.insert_textbox(pymupdf.Rect(50, 50, 400, 250), long_paragraph, fontsize=11)
    page.insert_textbox(
        pymupdf.Rect(50, 270, 400, 400),
        "Actividad:\n1. Leé el texto.\n2. Respondé el cuestionario bio-\nlógico.",
        fontsize=11,
    )
    doc = document_service.process_pdf(pdf.tobytes(), "prueba.pdf")
    paragraphs = rs.split_paragraphs(doc.raw_text)
    assert paragraphs[0] == long_paragraph.strip()
    assert paragraphs[1:] == ["Actividad:", "1. Leé el texto.", "2. Respondé el cuestionario biológico."]


# --- Estructura del PDF: Títulos, Jerarquías y Reglas (Issue #24) ------------


def test_extracted_document_default_structure():
    doc = _doc("Texto plano de prueba para verificar compatibilidad hacia atrás.")
    assert hasattr(doc, "structure")
    assert doc.structure.has_headings is False
    assert doc.structure.headings == []
    assert doc.structure.hierarchy_levels == 0


def test_process_pdf_detects_headings_and_hierarchy():
    pdf = pymupdf.open()
    page = pdf.new_page()
    # H1: Título principal en 18pt
    page.insert_textbox(pymupdf.Rect(50, 50, 400, 100), "Guía de Ciencias Naturales", fontsize=18)
    # Cuerpo en 11pt
    page.insert_textbox(
        pymupdf.Rect(50, 110, 400, 180),
        "En esta unidad estudiaremos la biodiversidad y el funcionamiento de los ecosistemas en nuestra región.",
        fontsize=11,
    )
    # H2: Subtítulo en 14pt
    page.insert_textbox(pymupdf.Rect(50, 190, 400, 240), "1. Los Ecosistemas Acuáticos", fontsize=14)
    # Cuerpo en 11pt
    page.insert_textbox(
        pymupdf.Rect(50, 250, 400, 320),
        "Los ambientes de agua dulce albergan múltiples comunidades biológicas interdependientes.",
        fontsize=11,
    )
    doc = document_service.process_pdf(pdf.tobytes(), "ciencias.pdf")

    assert doc.structure.has_headings is True
    assert doc.structure.hierarchy_levels == 2
    assert len(doc.structure.headings) == 2
    assert doc.structure.headings[0].text == "Guía de Ciencias Naturales"
    assert doc.structure.headings[0].level == 1
    assert doc.structure.headings[1].text == "1. Los Ecosistemas Acuáticos"
    assert doc.structure.headings[1].level == 2


def test_pdf_without_titles_triggers_rule():
    pdf = pymupdf.open()
    page = pdf.new_page()
    # 200 palabras continuas sin títulos (todo en 11pt)
    text = "Este es un texto continuo de doscientas palabras pensado para verificar que la regla de falta de títulos se active cuando un documento es extenso. " * 8
    page.insert_textbox(pymupdf.Rect(50, 50, 500, 700), text, fontsize=11)
    doc = document_service.process_pdf(pdf.tobytes(), "sin_titulos.pdf")

    assert doc.word_count >= rs.MIN_WORDS_FOR_HEADING_RULE
    assert doc.structure.has_headings is False

    rules = rs.run_rules(doc)
    assert any(f.barrier["issue"] == "Documento extenso sin títulos ni estructura definida" for f in rules.findings)
    assert any(p.rule == "pdf_sin_titulos" for p in rules.penalties)
    assert any(f.barrier["severity"] == "barrera_detectada" for f in rules.findings)

    # El tope SEVERE_BARRIER_CAP (89) aplica al no tener títulos en documento extenso
    breakdown = rs.compute_score(95, rules)
    assert breakdown.final_score <= rs.SEVERE_BARRIER_CAP


def test_pdf_short_without_titles_does_not_trigger_false_positive():
    pdf = pymupdf.open()
    page = pdf.new_page()
    # Documento breve (50 palabras): una consigna rápida no debe exigir H1/H2
    text = "Actividad corta: responder las preguntas del práctico 1. " * 5
    page.insert_textbox(pymupdf.Rect(50, 50, 400, 200), text, fontsize=11)
    doc = document_service.process_pdf(pdf.tobytes(), "consigna_corta.pdf")

    assert doc.word_count < rs.MIN_WORDS_FOR_HEADING_RULE
    rules = rs.run_rules(doc)
    assert not any(p.rule == "pdf_sin_titulos" for p in rules.penalties)


def test_text_source_type_does_not_trigger_pdf_heading_rule():
    # El texto pegado no tiene información de fuentes de PyMuPDF
    text = "Texto largo pegado directamente por el docente en la plataforma sin encabezados. " * 15
    doc = document_service.process_text(text)

    assert doc.source_type == "text"
    rules = rs.run_rules(doc)
    assert not any(p.rule == "pdf_sin_titulos" for p in rules.penalties)


def test_pdf_with_hierarchy_skip_triggers_review_barrier():
    pdf = pymupdf.open()
    page = pdf.new_page()
    # H1: 22pt
    page.insert_textbox(pymupdf.Rect(50, 50, 400, 110), "Título General de la Materia", fontsize=22)
    page.insert_textbox(pymupdf.Rect(50, 120, 400, 160), "Introducción general al programa de estudio.", fontsize=11)
    # H2: 16pt
    page.insert_textbox(pymupdf.Rect(50, 170, 400, 210), "Módulo 1: Fundamentos", fontsize=16)
    page.insert_textbox(pymupdf.Rect(50, 220, 400, 260), "Contenido conceptual básico.", fontsize=11)
    # H3: 13pt
    page.insert_textbox(pymupdf.Rect(50, 270, 400, 310), "Apartado 1.1: Definiciones", fontsize=13)
    page.insert_textbox(pymupdf.Rect(50, 320, 400, 360), "Definiciones iniciales del módulo.", fontsize=11)
    # Salto de H1 a H3 en una nueva sección: H1 (22pt) seguido inmediatamente por H3 (13pt)
    page.insert_textbox(pymupdf.Rect(50, 370, 400, 430), "Capítulo 2: Casos Prácticos", fontsize=22)
    page.insert_textbox(pymupdf.Rect(50, 440, 400, 480), "Subapartado 2.1.1: Ejercicio de campo", fontsize=13)
    page.insert_textbox(pymupdf.Rect(50, 490, 400, 530), "Desarrollo del ejercicio.", fontsize=11)

    doc = document_service.process_pdf(pdf.tobytes(), "salto_jerarquia.pdf")
    assert doc.structure.hierarchy_levels >= 3

    rules = rs.run_rules(doc)
    assert any("Salto de jerarquía en títulos" in f.barrier["issue"] for f in rules.findings)
    assert any(p.rule == "salto_jerarquia_titulos" for p in rules.penalties)


def test_pdf_well_structured_has_clean_dimensions():
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 400, 100), "Trabajo Práctico de Historia", fontsize=18)
    page.insert_textbox(pymupdf.Rect(50, 110, 400, 170), "Texto ordenado con oraciones claras y párrafos breves sobre la Revolución de Mayo.", fontsize=11)
    page.insert_textbox(pymupdf.Rect(50, 180, 400, 220), "Actividad Principal", fontsize=14)
    page.insert_textbox(pymupdf.Rect(50, 230, 400, 290), "1. Leé la proclama histórica.\n2. Explicá su importancia.", fontsize=11)

    doc = document_service.process_pdf(pdf.tobytes(), "historia.pdf")
    rules = rs.run_rules(doc)

    dim_estructura = next(d for d in rules.dimensions if d.category == "estructura")
    assert dim_estructura.status == "correcta"
    assert "Estructura organizada con 2 encabezados" in dim_estructura.comment


# --- Reglas de Comprensión e Información Visual (Tarea #25) -----------------


def test_detect_multi_action_prompts():
    # 2 verbos de acción: no dispara
    text_2 = "Leé el texto y respondé las preguntas del cuestionario."
    result_2 = rs.run_rules(_doc(text_2))
    assert result_2.metrics.multi_action_prompts == 0
    assert not any("múltiples acciones" in f.barrier["issue"] for f in result_2.findings)

    # 3 verbos de acción: para_revisar
    text_3 = "Leé el texto atentamente, subrayá las ideas clave y explicá tus conclusiones con claridad."
    result_3 = rs.run_rules(_doc(text_3))
    assert result_3.metrics.multi_action_prompts == 1
    multi_findings_3 = [f for f in result_3.findings if "múltiples acciones" in f.barrier["issue"]]
    assert len(multi_findings_3) == 1
    assert multi_findings_3[0].barrier["severity"] == "para_revisar"
    assert any(p.rule == "consignas_multiaccion" for p in result_3.penalties)

    # 4 o más verbos de acción: barrera_detectada
    text_4 = "Leé el fragmento, analizá las causas, compará con la unidad previa y redactá una síntesis."
    result_4 = rs.run_rules(_doc(text_4))
    multi_findings_4 = [f for f in result_4.findings if "múltiples acciones" in f.barrier["issue"]]
    assert len(multi_findings_4) == 1
    assert multi_findings_4[0].barrier["severity"] == "barrera_detectada"


def test_calculate_spanish_readability_szigriszt():
    # Texto corto (<100 palabras): no evalúa legibilidad (None)
    short_text = "Este es un texto breve de prueba para verificar que no calcule legibilidad."
    result_short = rs.run_rules(_doc(short_text))
    assert result_short.metrics.readability_score_szigriszt is None
    assert not any("legibilidad" in f.barrier["issue"] for f in result_short.findings)

    # Texto accesible/sencillo con más de 100 palabras (oraciones cortas y palabras de pocas sílabas)
    easy_sentences = [
        "El sol da luz y calor a la tierra.",
        "Las plantas usan el sol para crecer.",
        "El agua cae en forma de lluvia.",
        "Los ríos llevan agua hacia el mar.",
        "Los animales beben agua en los ríos.",
        "El ciclo del agua se repite siempre.",
        "El viento mueve las nubes en el cielo.",
        "Las aves vuelan alto con el viento.",
        "Los peces nadan en el agua fría.",
        "El pasto crece verde en el campo.",
        "Los niños juegan en el parque verde.",
        "La luna brilla de noche en el cielo.",
        "Las estrellas iluminan todo el sendero.",
        "El bosque tiene árboles muy altos.",
        "La naturaleza nos da mucha vida.",
    ]
    easy_text = " ".join(easy_sentences)
    assert rs.count_words(easy_text) >= 100
    result_easy = rs.run_rules(_doc(easy_text))
    assert result_easy.metrics.readability_score_szigriszt is not None
    assert result_easy.metrics.readability_score_szigriszt >= 60.0
    assert not any("legibilidad" in f.barrier["issue"] for f in result_easy.findings)

    # Texto con legibilidad baja (oraciones largas y vocabulario polisilábico)
    difficult_text = (
        "La desconcentración administrativa descentralizada e interdisciplinaria constituye una manifestación "
        "institucionalizada extraordinariamente compleja de reorganización gubernamental contemporánea. "
        "Consecuentemente, los establecimientos educacionales experimentan transformaciones metodológicas sustanciales "
        "caracterizadas por conceptualizaciones psicopedagógicas profundamente estructuradas y multidimensionales. "
        "Paralelamente, las descontextualizaciones socioeconómicas obstaculizan sistemáticamente la implementación "
        "integral de normativas jurisprudenciales relativas a la accesibilidad cognitiva y comunicacional docente. "
        "Indiscutiblemente, las interrelaciones multidisciplinarias requieren investigaciones epistemológicas constantes. "
        "Asimismo, la fundamentación teórica contemporánea demanda aproximaciones analíticas rigurosas y exhaustivas, "
        "propiciando debates hermenéuticos indispensables sobre la diversificación curricular institucionalizada. "
        "Finalmente, resulta imprescindible reconsiderar las metodologías pedagógicas tradicionales para garantizar "
        "una verdadera inclusión educativa transformadora y participativa en todos los niveles académicos."
    )
    assert rs.count_words(difficult_text) >= 100
    result_diff = rs.run_rules(_doc(difficult_text))
    assert result_diff.metrics.readability_score_szigriszt is not None
    assert result_diff.metrics.readability_score_szigriszt < 50.0
    readability_findings = [f for f in result_diff.findings if "legibilidad" in f.barrier["issue"]]
    assert len(readability_findings) == 1
    assert any(p.rule == "legibilidad_baja" for p in result_diff.penalties)


def test_detect_visual_only_references():
    text = (
        "Para realizar la actividad, observá el gráfico de la derecha. "
        "Luego seleccioná el botón azul para enviar tu respuesta."
    )
    result = rs.run_rules(_doc(text))
    assert result.metrics.visual_only_references == 2
    vis_findings = [f for f in result.findings if f.barrier["category"] == "accesibilidad_visual" and "visual" in f.barrier["issue"]]
    assert len(vis_findings) == 2
    assert any(p.rule == "referencias_visuales" for p in result.penalties)

    dim_visual = next(d for d in result.dimensions if d.category == "accesibilidad_visual")
    assert dim_visual.status == "para_revisar"
    assert "referencia(s) que dependen de la posición o aspecto visual" in dim_visual.comment


def test_rules_metrics_task25():
    text = (
        "Leé el texto, subrayá lo principal y anotá tus dudas. "
        "Revisá el recuadro rojo para más datos."
    )
    result = rs.run_rules(_doc(text))
    assert result.metrics.multi_action_prompts == 1
    assert result.metrics.visual_only_references == 1
    assert result.metrics.readability_score_szigriszt is None  # < 100 palabras

