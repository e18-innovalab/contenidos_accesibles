"""
Exportación del material adaptado e informe ejecutivo en memoria (Issue #40).

Genera archivos en formato MD, TXT o DOCX a partir del texto adaptado (#38)
y del informe de accesibilidad (#39). Todo se construye en io.BytesIO (cero
escritura en disco) para garantizar privacidad y no saturar el almacenamiento
del servidor.

Con `?delivery=link` (Issue #62) el endpoint guarda el archivo generado en el
almacenamiento (R2 en producción) y devuelve una URL firmada de descarga en lugar
de los bytes (app/api/v1/delivery.py).
"""

import io
import re
from datetime import datetime, timezone
from pathlib import Path
from fpdf import FPDF
from fpdf.prefs import ViewerPreferences

from app.schemas.adaptation import AdaptedDocumentResponse, FinalReportResponse

_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_PDF_FONT_FAMILY = "DejaVu"

# ---------------------------------------------------------------------------
# Constantes de formato
# ---------------------------------------------------------------------------

_CONTENT_TYPES = {
    "pdf":  "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "md":   "text/markdown; charset=utf-8",
    "txt":  "text/plain; charset=utf-8",
}

_REPORT_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "md":  "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
}

_SEVERITY_LABELS = {
    "barrera_detectada": "🔴 Barrera detectada",
    "para_revisar":      "🟡 Para revisar",
}

_SEVERITY_LABELS_CLEAN = {
    "barrera_detectada": "Barrera detectada",
    "para_revisar":      "Para revisar",
}

_STATUS_LABELS = {
    "aceptada":   "✅ Aceptada",
    "editada":    "✏️ Editada por el docente",
    "descartada": "❌ Descartada",
    "pendiente":  "⏳ Pendiente",
}

_STATUS_LABELS_CLEAN = {
    "aceptada":   "Aceptada",
    "editada":    "Editada por docente",
    "descartada": "Descartada",
    "pendiente":  "Pendiente",
}

_CATEGORY_LABELS = {
    "comprension":        "Comprensión",
    "estructura":         "Estructura",
    "accesibilidad_visual": "Accesibilidad visual",
}


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_filename(text: str, max_len: int = 40) -> str:
    """Convierte texto libre a un nombre de archivo seguro."""
    import re
    cleaned = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    cleaned = re.sub(r"[\s]+", "_", cleaned.strip())
    return cleaned[:max_len] or "material"


# ---------------------------------------------------------------------------
# Exportación del material adaptado
# ---------------------------------------------------------------------------

def _content_as_markdown(adapted: AdaptedDocumentResponse) -> bytes:
    """
    Genera el material adaptado en formato Markdown.
    Preserva saltos de línea del texto adaptado y añade metadatos al inicio.
    """
    lines = [
        f"# Material Adaptado",
        f"",
        f"**ID de análisis:** `{adapted.analysis_id}`  ",
        f"**Propuestas aplicadas:** {adapted.applied_count} de {adapted.total_proposals}",
        f"",
        "---",
        "",
    ]
    if adapted.warnings:
        lines += ["> **Advertencias:**"]
        for w in adapted.warnings:
            lines.append(f"> - {w}")
        lines.append("")

    lines.append(adapted.adapted_text)
    return "\n".join(lines).encode("utf-8")


def _content_as_txt(adapted: AdaptedDocumentResponse) -> bytes:
    """
    Genera el material adaptado en texto plano UTF-8.
    Separa el encabezado del contenido con una línea de guiones.
    """
    header = (
        f"MATERIAL ADAPTADO\n"
        f"ID de análisis: {adapted.analysis_id}\n"
        f"Propuestas aplicadas: {adapted.applied_count} de {adapted.total_proposals}\n"
        f"{'=' * 60}\n\n"
    )
    if adapted.warnings:
        header += "ADVERTENCIAS:\n"
        for w in adapted.warnings:
            header += f"  - {w}\n"
        header += "\n"
    return (header + adapted.adapted_text).encode("utf-8")


def _content_as_docx(adapted: AdaptedDocumentResponse) -> bytes:
    """
    Genera el material adaptado como documento Word (.docx) con tipografía
    accesible (Arial, interlineado 1.5, jerarquía de títulos clara).

    Devuelve los bytes del .docx listos para ser enviados o subidos a R2 (#62).
    """
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.oxml.ns import qn
    from docx.enum.text import WD_LINE_SPACING

    doc = Document()

    # --- Estilos base accesibles ---
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Arial"
    font.size = Pt(12)
    pf = style.paragraph_format
    pf.space_after = Pt(8)

    # --- Título del documento ---
    title = doc.add_heading("Material Adaptado", level=1)
    title.runs[0].font.color.rgb = RGBColor(0x1F, 0x49, 0x7D)

    # --- Metadatos ---
    meta = doc.add_paragraph()
    meta.add_run("ID de análisis: ").bold = True
    meta.add_run(adapted.analysis_id)
    doc.add_paragraph(
        f"Propuestas aplicadas: {adapted.applied_count} de {adapted.total_proposals}"
    )

    if adapted.warnings:
        doc.add_heading("Advertencias", level=2)
        for w in adapted.warnings:
            doc.add_paragraph(w, style="List Bullet")

    doc.add_paragraph("─" * 50)

    # --- Contenido adaptado (párrafo por línea no vacía) ---
    doc.add_heading("Contenido", level=2)
    for line in adapted.adapted_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        p = doc.add_paragraph(stripped)
        pf2 = p.paragraph_format
        pf2.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE

    # --- Guardar en buffer de memoria ---
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.read()


def _clean_pdf_text(text: str) -> str:
    """Normaliza texto Unicode para renderizado PDF sin pérdida por codificación latin-1."""
    return text or ""


class AccessiblePDF(FPDF):
    """
    Clase base de PDF accesible con fuente Unicode (DejaVu Sans), metadatos
    de documento (título, idioma, autor y asunto) y pie de página institucional.

    Nota sobre etiquetado (Tagged PDF / PDF/UA): fpdf2 2.8.x no expone una API
    pública para generar un árbol de estructura completo (etiquetas semánticas
    de encabezados, párrafos, tablas y orden de lectura para lectores de pantalla).
    Para máxima accesibilidad estructural con lectores de pantalla, se recomienda
    exportar en formato DOCX.
    """

    def __init__(
        self,
        *,
        title: str = "Documento Accesible",
        subject: str = "",
        lang: str = "es",
        author: str = "Innova Lab - Asistente de Accesibilidad",
    ) -> None:
        super().__init__()
        self.add_font(_PDF_FONT_FAMILY, "", str(_FONTS_DIR / "DejaVuSans.ttf"))
        self.add_font(_PDF_FONT_FAMILY, "B", str(_FONTS_DIR / "DejaVuSans-Bold.ttf"))
        self.add_font(_PDF_FONT_FAMILY, "I", str(_FONTS_DIR / "DejaVuSans-Oblique.ttf"))
        self.add_font(_PDF_FONT_FAMILY, "BI", str(_FONTS_DIR / "DejaVuSans-BoldOblique.ttf"))
        self.set_title(title)
        self.set_lang(lang)
        self.set_author(author)
        if subject:
            self.set_subject(subject)
        self.viewer_preferences = ViewerPreferences(display_doc_title=True)

    def footer(self):
        self.set_y(-15)
        self.set_font(_PDF_FONT_FAMILY, "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(
            0,
            10,
            f"Página {self.page_no()}/{{nb}} | Innova Lab - Asistente de Accesibilidad",
            align="C",
        )


def _content_as_pdf(adapted: AdaptedDocumentResponse) -> bytes:
    """
    Genera el material adaptado en PDF en memoria (fpdf2) con fuente Unicode (DejaVu Sans),
    metadatos de idioma/título, márgenes cómodos (20mm) e interlineado legible.
    """
    pdf = AccessiblePDF(
        title="Material Adaptado",
        subject=f"Material educativo adaptado - Análisis {adapted.analysis_id}",
    )
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Título del documento
    pdf.set_font(_PDF_FONT_FAMILY, "B", 18)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(text="Material Adaptado")
    pdf.ln(10)

    # Metadatos del análisis
    pdf.set_font(_PDF_FONT_FAMILY, "B", 10)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(text=f"ID de análisis: {adapted.analysis_id}")
    pdf.ln(6)
    pdf.set_font(_PDF_FONT_FAMILY, "", 10)
    pdf.cell(text=f"Propuestas aplicadas: {adapted.applied_count} de {adapted.total_proposals}")
    pdf.ln(8)

    if adapted.warnings:
        pdf.set_font(_PDF_FONT_FAMILY, "B", 10)
        pdf.set_text_color(180, 80, 0)
        pdf.cell(text="Advertencias:")
        pdf.ln(5)
        pdf.set_font(_PDF_FONT_FAMILY, "", 9)
        pdf.set_text_color(80, 80, 80)
        for w in adapted.warnings:
            pdf.multi_cell(w=0, h=5, text=_clean_pdf_text(f"- {w}"), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
        pdf.ln(4)

    # Separador
    pdf.set_draw_color(200, 200, 200)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(8)

    # Contenido adaptado
    pdf.set_font(_PDF_FONT_FAMILY, "B", 13)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(text="Contenido")
    pdf.ln(8)

    pdf.set_font(_PDF_FONT_FAMILY, "", 11)
    pdf.set_text_color(20, 20, 20)
    for line in adapted.adapted_text.splitlines():
        stripped = line.strip()
        if not stripped:
            pdf.ln(3)
            continue
        pdf.multi_cell(w=0, h=7, text=_clean_pdf_text(stripped), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    return bytes(pdf.output())


def export_content(adapted: AdaptedDocumentResponse, export_format: str) -> tuple[bytes, str]:
    """
    Genera el material adaptado en el formato solicitado.

    Args:
        adapted:        Resultado de adaptation_service.build_adapted_document().
        export_format:  'pdf', 'docx', 'md' o 'txt'.

    Returns:
        (bytes_del_archivo, content_type_header)

    """
    fmt = export_format.lower()
    if fmt not in _CONTENT_TYPES:
        raise ValueError(f"Formato no soportado para material adaptado: '{fmt}'. Use pdf, docx, md o txt.")

    if fmt == "pdf":
        data = _content_as_pdf(adapted)
    elif fmt == "docx":
        data = _content_as_docx(adapted)
    elif fmt == "md":
        data = _content_as_markdown(adapted)
    else:  # txt
        data = _content_as_txt(adapted)

    return data, _CONTENT_TYPES[fmt]


# ---------------------------------------------------------------------------
# Documento genérico: título, avisos y cuerpo (transformaciones de material, Issue #117)
# ---------------------------------------------------------------------------

_TABLE_SEPARATOR = re.compile(r"^\|?[\s:|-]+\|?$")


def _table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _body_blocks(body: str) -> list[str | list[list[str]]]:
    """
    Renglones del cuerpo, con las tablas Markdown (renglones seguidos que empiezan con '|') como
    listas de filas: en docx y pdf van como tablas de verdad, que un lector de pantalla recorre por
    celda y con encabezado. Sin la fila separadora (|---|) no es una tabla y queda como texto.
    """
    blocks: list[str | list[list[str]]] = []
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        j = i
        while j < len(lines) and lines[j].strip().startswith("|"):
            j += 1
        if j - i >= 2 and _TABLE_SEPARATOR.match(lines[i + 1].strip()):
            rows = [_table_row(line) for k, line in enumerate(lines[i:j]) if k != 1]
            width = max(len(r) for r in rows)
            blocks.append([r + [""] * (width - len(r)) for r in rows])
            i = j
            continue
        blocks.extend(lines[i:max(j, i + 1)])
        i = max(j, i + 1)
    return blocks


def _docx_table(doc, rows: list[list[str]]) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    table = doc.add_table(rows=0, cols=len(rows[0]))
    table.style = "Table Grid"
    for r, values in enumerate(rows):
        cells = table.add_row().cells
        for cell, value in zip(cells, values):
            cell.text = value
            if r == 0:
                for run in cell.paragraphs[0].runs:
                    run.bold = True
    # Fila de encabezado: el lector de pantalla la anuncia con cada celda y se repite en cada página
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    table.rows[0]._tr.get_or_add_trPr().append(header)
    doc.add_paragraph()


def _document_as_docx(title: str, notes: list[str], body: str) -> bytes:
    from docx import Document
    from docx.enum.text import WD_LINE_SPACING
    from docx.shared import Pt, RGBColor

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(12)
    style.paragraph_format.space_after = Pt(8)

    heading = doc.add_heading(title, level=1)
    heading.runs[0].font.color.rgb = RGBColor(0x1F, 0x49, 0x7D)
    if notes:
        doc.add_heading("Avisos", level=2)
        for note in notes:
            doc.add_paragraph(note, style="List Bullet")
    for block in _body_blocks(body):
        if isinstance(block, list):
            _docx_table(doc, block)
        elif block.strip():
            doc.add_paragraph(block.strip()).paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _document_as_pdf(title: str, notes: list[str], body: str) -> bytes:
    pdf = AccessiblePDF(title=title, subject="Material educativo adaptado")
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_font(_PDF_FONT_FAMILY, "B", 18)
    pdf.set_text_color(31, 73, 125)
    pdf.multi_cell(w=0, h=9, text=_clean_pdf_text(title), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    if notes:
        pdf.set_font(_PDF_FONT_FAMILY, "", 9)
        pdf.set_text_color(80, 80, 80)
        for note in notes:
            pdf.multi_cell(w=0, h=5, text=_clean_pdf_text(f"- {note}"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
    pdf.set_font(_PDF_FONT_FAMILY, "", 11)
    pdf.set_text_color(20, 20, 20)
    for block in _body_blocks(body):
        if isinstance(block, list):
            pdf.set_font(_PDF_FONT_FAMILY, "", 10)
            with pdf.table(text_align="LEFT", first_row_as_headings=True) as table:
                for row in block:
                    cells = table.row()
                    for value in row:
                        cells.cell(_clean_pdf_text(value))
            pdf.set_font(_PDF_FONT_FAMILY, "", 11)
            pdf.ln(2)
        elif not block.strip():
            pdf.ln(3)
        else:
            pdf.multi_cell(w=0, h=7, text=_clean_pdf_text(block.strip()), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
    return bytes(pdf.output())


def export_document(title: str, body: str, export_format: str, notes: list[str] | None = None) -> tuple[bytes, str]:
    """Documento con título, avisos opcionales y cuerpo, con la misma tipografía que el material adaptado."""
    fmt = export_format.lower()
    if fmt not in _CONTENT_TYPES:
        raise ValueError(f"Formato no soportado: '{fmt}'. Use pdf, docx, md o txt.")
    notes = notes or []
    if fmt == "pdf":
        data = _document_as_pdf(title, notes, body)
    elif fmt == "docx":
        data = _document_as_docx(title, notes, body)
    elif fmt == "md":
        warnings = "".join(f"> - {n}\n" for n in notes)
        data = f"# {title}\n\n{warnings + chr(10) if warnings else ''}{body}\n".encode("utf-8")
    else:  # txt
        warnings = "".join(f"  - {n}\n" for n in notes)
        data = f"{title.upper()}\n{'=' * 60}\n\n{warnings + chr(10) if warnings else ''}{body}\n".encode("utf-8")
    return data, _CONTENT_TYPES[fmt]


# ---------------------------------------------------------------------------
# Exportación del informe ejecutivo
# ---------------------------------------------------------------------------

def _report_as_markdown(report: FinalReportResponse) -> bytes:
    """
    Genera el informe ejecutivo completo en Markdown (GitHub Flavored).
    """
    lines = [
        "# Informe de Accesibilidad — Material Adaptado",
        "",
        f"**ID de análisis:** `{report.analysis_id}`  ",
        f"**Generado:** {report.generated_at}",
        "",
        "---",
        "",
        "## Resumen ejecutivo",
        "",
    ]
    for phrase in report.executive_summary:
        lines.append(f"- {phrase}")

    lines += [
        "",
        "## Puntaje de accesibilidad",
        "",
        f"| | Antes | Después | Δ |",
        f"|---|---|---|---|",
        f"| **Puntaje** | {report.score_before} | {report.score_after} | "
        f"{'+ ' if report.score_delta >= 0 else ''}{report.score_delta} |",
        "",
        f"> _{report.disclaimer}_",
        "",
        "---",
        "",
        "## Barreras detectadas y decisiones",
        "",
        f"| ID | Categoría | Severidad | Barrera | Estado |",
        f"|---|---|---|---|---|",
    ]

    for b in report.barriers_detail:
        cat   = _CATEGORY_LABELS.get(b.category, b.category)
        sev   = _SEVERITY_LABELS.get(b.severity, b.severity)
        status = _STATUS_LABELS.get(b.resolution_status, b.resolution_status)
        lines.append(f"| {b.barrier_id} | {cat} | {sev} | {b.issue} | {status} |")

    lines += [
        "",
        "---",
        "",
        "## Métricas consolidadas",
        "",
        f"- **Total barreras detectadas:** {report.total_barriers}",
        f"- **Resueltas (aceptadas + editadas):** {report.resolved_count}",
        f"- **Descartadas por el docente:** {report.discarded_count}",
        f"- **Sin decisión (pendientes):** {report.pending_count}",
        f"- **Propuestas de adaptación generadas:** {report.total_proposals}",
    ]

    if report.warnings:
        lines += ["", "## Advertencias", ""]
        for w in report.warnings:
            lines.append(f"- {w}")

    return "\n".join(lines).encode("utf-8")


def _report_as_txt(report: FinalReportResponse) -> bytes:
    """
    Genera el informe ejecutivo en texto plano UTF-8.
    """
    sep = "=" * 60
    thin = "-" * 60
    lines = [
        "INFORME DE ACCESIBILIDAD - MATERIAL ADAPTADO",
        sep,
        f"ID de análisis: {report.analysis_id}",
        f"Generado:       {report.generated_at}",
        sep,
        "",
        "RESUMEN EJECUTIVO",
        thin,
    ]
    for phrase in report.executive_summary:
        lines.append(f"  · {phrase}")

    lines += [
        "",
        "PUNTAJE DE ACCESIBILIDAD",
        thin,
        f"  Antes:    {report.score_before}",
        f"  Después:  {report.score_after}",
        f"  Delta:    {'+' if report.score_delta >= 0 else ''}{report.score_delta}",
        f"  NOTA: {report.disclaimer}",
        "",
        "BARRERAS DETECTADAS Y DECISIONES",
        thin,
    ]

    for b in report.barriers_detail:
        cat    = _CATEGORY_LABELS.get(b.category, b.category)
        sev    = b.severity.replace("_", " ").upper()
        status = b.resolution_status.upper()
        lines.append(f"  [{b.barrier_id}] [{sev}] [{cat}] {b.issue}")
        lines.append(f"         → {status}")
        if b.final_text:
            preview = b.final_text[:120].replace("\n", " ")
            if len(b.final_text) > 120:
                preview += "…"
            lines.append(f"         Texto aplicado: {preview}")
        lines.append("")

    lines += [
        "MÉTRICAS",
        thin,
        f"  Total barreras:          {report.total_barriers}",
        f"  Resueltas:               {report.resolved_count}",
        f"  Descartadas:             {report.discarded_count}",
        f"  Pendientes:              {report.pending_count}",
        f"  Propuestas generadas:    {report.total_proposals}",
    ]

    if report.warnings:
        lines += ["", "ADVERTENCIAS", thin]
        for w in report.warnings:
            lines.append(f"  · {w}")

    return "\n".join(lines).encode("utf-8")


def _report_as_pdf(report: FinalReportResponse) -> bytes:
    """
    Genera el informe ejecutivo de accesibilidad en PDF en memoria (fpdf2).
    Incluye resumen ejecutivo, tabla de puntajes antes/después/delta,
    desglose estructurado de barreras y aclaración de carácter orientativo (WCAG).
    """
    pdf = AccessiblePDF(
        title="Informe de Accesibilidad - Material Adaptado",
        subject=f"Informe ejecutivo de accesibilidad - Análisis {report.analysis_id}",
    )
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Título principal
    pdf.set_font(_PDF_FONT_FAMILY, "B", 16)
    pdf.set_text_color(31, 73, 125)
    pdf.multi_cell(
        w=0,
        h=8,
        text=_clean_pdf_text("Informe de Accesibilidad - Material Adaptado"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    # Metadatos del informe
    pdf.set_font(_PDF_FONT_FAMILY, "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(
        text=_clean_pdf_text(f"ID de análisis: {report.analysis_id}  |  Generado: {report.generated_at}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(8)

    # Resumen ejecutivo
    pdf.set_font(_PDF_FONT_FAMILY, "B", 12)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(text="Resumen ejecutivo", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.set_font(_PDF_FONT_FAMILY, "", 10)
    pdf.set_text_color(30, 30, 30)
    for phrase in report.executive_summary:
        pdf.multi_cell(
            w=0,
            h=6,
            text=_clean_pdf_text(f"- {phrase}"),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(1)
    pdf.ln(5)

    # Puntaje de accesibilidad
    pdf.set_font(_PDF_FONT_FAMILY, "B", 12)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(text="Puntaje de accesibilidad", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    delta_str = f"+{report.score_delta}" if report.score_delta >= 0 else str(report.score_delta)
    pdf.set_font(_PDF_FONT_FAMILY, "", 10)
    with pdf.table(col_widths=(60, 40, 40, 40)) as table:
        h = table.row()
        h.cell("Evaluación")
        h.cell("Antes")
        h.cell("Después")
        h.cell("Diferencial (Delta)")
        r = table.row()
        r.cell("Puntaje general")
        r.cell(str(report.score_before))
        r.cell(str(report.score_after))
        r.cell(delta_str)

    pdf.set_x(15)
    pdf.ln(4)

    # Disclaimer
    pdf.set_font(_PDF_FONT_FAMILY, "I", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(
        w=0,
        h=4.5,
        text=_clean_pdf_text(f"Nota: {report.disclaimer}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(6)

    # Barreras detectadas y decisiones
    pdf.set_font(_PDF_FONT_FAMILY, "B", 12)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(text="Barreras detectadas y decisiones", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.set_font(_PDF_FONT_FAMILY, "", 9)
    with pdf.table(col_widths=(18, 30, 32, 65, 35)) as table:
        h = table.row()
        h.cell("ID")
        h.cell("Categoría")
        h.cell("Severidad")
        h.cell("Barrera")
        h.cell("Estado")
        for b in report.barriers_detail:
            cat = _CATEGORY_LABELS.get(b.category, b.category)
            sev = _SEVERITY_LABELS_CLEAN.get(b.severity, b.severity)
            status = _STATUS_LABELS_CLEAN.get(b.resolution_status, b.resolution_status)
            r = table.row()
            r.cell(_clean_pdf_text(b.barrier_id))
            r.cell(_clean_pdf_text(cat))
            r.cell(_clean_pdf_text(sev))
            r.cell(_clean_pdf_text(b.issue))
            r.cell(_clean_pdf_text(status))

    pdf.set_x(15)
    pdf.ln(6)

    # Métricas consolidadas
    pdf.set_font(_PDF_FONT_FAMILY, "B", 12)
    pdf.set_text_color(31, 73, 125)
    pdf.cell(text="Métricas consolidadas", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.set_font(_PDF_FONT_FAMILY, "", 9)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(w=0, h=5, text=_clean_pdf_text(f"- Total barreras detectadas: {report.total_barriers}"), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(w=0, h=5, text=_clean_pdf_text(f"- Resueltas (aceptadas o editadas): {report.resolved_count}"), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(w=0, h=5, text=_clean_pdf_text(f"- Descartadas por el docente: {report.discarded_count}"), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(w=0, h=5, text=_clean_pdf_text(f"- Sin decisión tomada: {report.pending_count}"), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(w=0, h=5, text=_clean_pdf_text(f"- Propuestas generadas: {report.total_proposals}"), new_x="LMARGIN", new_y="NEXT")

    if report.warnings:
        pdf.ln(4)
        pdf.set_font(_PDF_FONT_FAMILY, "B", 11)
        pdf.set_text_color(180, 80, 0)
        pdf.cell(text="Advertencias:", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
        pdf.set_font(_PDF_FONT_FAMILY, "", 9)
        pdf.set_text_color(80, 80, 80)
        for w in report.warnings:
            pdf.multi_cell(w=0, h=5, text=_clean_pdf_text(f"- {w}"), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def export_report(report: FinalReportResponse, export_format: str) -> tuple[bytes, str]:
    """
    Genera el informe ejecutivo de accesibilidad en el formato solicitado.

    Args:
        report:         Resultado de adaptation_service.build_final_report().
        export_format:  'pdf', 'md' o 'txt'.

    Returns:
        (bytes_del_archivo, content_type_header)

    """
    fmt = export_format.lower()
    if fmt not in _REPORT_CONTENT_TYPES:
        raise ValueError(f"Formato no soportado para informe: '{fmt}'. Use pdf, md o txt.")

    if fmt == "pdf":
        data = _report_as_pdf(report)
    elif fmt == "md":
        data = _report_as_markdown(report)
    else:  # txt
        data = _report_as_txt(report)

    return data, _REPORT_CONTENT_TYPES[fmt]


# ---------------------------------------------------------------------------
# Helper de nombre de archivo para Content-Disposition
# ---------------------------------------------------------------------------

def build_filename(base: str, analysis_id: str, export_format: str) -> str:
    """
    Construye el nombre de archivo para el header Content-Disposition.
    Ejemplo: 'material_adaptado_a1b2c3.docx'
    """
    short_id = analysis_id[:8] if len(analysis_id) >= 8 else analysis_id
    safe_base = _safe_filename(base)
    return f"{safe_base}_{short_id}.{export_format.lower()}"
