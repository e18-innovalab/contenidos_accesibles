"""
Generador reproducible de documentos de prueba para QA y calibración (Issue #181).

Crea una suite acotada pero representativa de archivos .pdf, .docx y .pptx en:
- tester/DocumentosDePrueba/pdf/
- tester/DocumentosDePrueba/docx/
- tester/DocumentosDePrueba/pptx/

Uso (desde la raíz del repositorio):
    backend/venv/bin/python tester/DocumentosDePrueba/generar_documentos.py
"""

from __future__ import annotations

import io
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from fpdf import FPDF
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.dml.color import RGBColor as PptxRGB
from pptx.util import Inches as PptxInches, Pt as PptxPt

BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = BASE_DIR / "pdf"
DOCX_DIR = BASE_DIR / "docx"
PPTX_DIR = BASE_DIR / "pptx"
FONTS_DIR = BASE_DIR.parent.parent / "backend" / "app" / "assets" / "fonts"


def _setup_dirs() -> None:
    for d in (PDF_DIR, DOCX_DIR, PPTX_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _new_unicode_pdf(title: str) -> FPDF:
    pdf = FPDF()
    pdf.add_font("DejaVu", "", str(FONTS_DIR / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONTS_DIR / "DejaVuSans-Bold.ttf"))
    pdf.add_font("DejaVu", "I", str(FONTS_DIR / "DejaVuSans-Oblique.ttf"))
    pdf.set_title(title)
    pdf.set_lang("es")
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    return pdf


def _mc(pdf: FPDF, h: float, text: str) -> None:
    pdf.multi_cell(w=0, h=h, text=text, new_x="LMARGIN", new_y="NEXT")


def _make_color_chart_png() -> bytes:
    """Genera un gráfico de barras cuya leyenda depende solo del color rojo y verde."""
    img = Image.new("RGB", (640, 360), "white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 15), "Rendimiento por grupo", fill=(20, 20, 20))
    # Barras sin etiquetas de patrón, solo rojo y verde
    bars = [(80, 120, (204, 0, 0)), (160, 80, (0, 140, 0)), (260, 150, (204, 0, 0)), (340, 70, (0, 140, 0))]
    for x, top, color in bars:
        draw.rectangle([x, top, x + 55, 300], fill=color)
    draw.line([50, 300, 450, 300], fill=(0, 0, 0), width=2)
    # Leyenda solo color
    draw.rectangle([470, 90, 495, 115], fill=(204, 0, 0))
    draw.text((505, 95), "Grupo A", fill=(20, 20, 20))
    draw.rectangle([470, 130, 495, 155], fill=(0, 140, 0))
    draw.text((505, 135), "Grupo B", fill=(20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_embedded_text_png() -> bytes:
    """Genera una imagen con texto relevante incrustado que no figura en el documento."""
    img = Image.new("RGB", (620, 240), (245, 248, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 610, 230], outline=(31, 73, 125), width=3)
    draw.text((30, 35), "REGLA DE EVALUACION (SOLO EN IMAGEN):", fill=(31, 73, 125))
    draw.text((30, 80), "1. Aprobar requiere >= 70% de asistencia.", fill=(20, 20, 20))
    draw.text((30, 115), "2. Entrega limite: viernes 18:00 hs.", fill=(20, 20, 20))
    draw.text((30, 150), "3. Consultas en aula 4B.", fill=(20, 20, 20))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_scanned_page_png() -> bytes:
    """Genera una página rasterizada simulando un PDF escaneado sin capa de texto."""
    img = Image.new("RGB", (800, 1050), (250, 249, 245))
    draw = ImageDraw.Draw(img)
    draw.text((60, 70), "GUIA DE ACTIVIDADES - BIOLOGIA (ESCANEO)", fill=(30, 30, 30))
    draw.text((60, 130), "Lee el capitulo 3 y responde las preguntas en tu carpeta.", fill=(40, 40, 40))
    draw.text((60, 175), "1. Que funcion cumple la clorofila en las plantas?", fill=(40, 40, 40))
    draw.text((60, 220), "2. Dibuja el ciclo del agua con flechas.", fill=(40, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_pdfs() -> None:
    # 1. Control accesible
    pdf = _new_unicode_pdf("Guía accesible de Ciencias Naturales")
    pdf.set_font("DejaVu", "B", 16)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(text="Unidad 1: Los estados de la materia", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("DejaVu", "", 12)
    _mc(pdf, 7, "La materia se presenta en tres estados principales: sólido, líquido y gaseoso.")
    pdf.ln(3)
    _mc(pdf, 7, "En el estado sólido, las partículas están muy juntas y mantienen una forma fija.")
    pdf.ln(3)
    _mc(pdf, 7, "Actividad: escribí dos ejemplos de cada estado en tu carpeta.")
    pdf.output(str(PDF_DIR / "01_pdf_control_accesible.pdf"))

    # 2. Legibilidad, bajo contraste, mayúsculas y daltonismo
    pdf = _new_unicode_pdf("Evaluación con problemas visuales")
    pdf.set_font("DejaVu", "B", 14)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(text="Evaluación de Matemática", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("DejaVu", "", 12)
    _mc(pdf, 7, "Las respuestas correctas están en verde y las incorrectas en rojo.")
    pdf.ln(3)
    pdf.set_text_color(0, 128, 0)
    _mc(pdf, 7, "Ejemplo correcto: 2 + 2 = 4 (esta opción suma un punto).")
    pdf.set_text_color(204, 0, 0)
    _mc(pdf, 7, "Ejemplo incorrecto: 2 + 2 = 5 (esta opción no suma puntos).")
    pdf.ln(4)
    pdf.set_text_color(170, 170, 170)
    pdf.set_font("DejaVu", "", 11)
    _mc(
        pdf, 6,
        "Este párrafo tiene un contraste muy bajo respecto del fondo blanco y cuesta leerlo con claridad en pantalla o impreso.",
    )
    pdf.ln(4)
    pdf.set_text_color(20, 20, 20)
    pdf.set_font("DejaVu", "", 7)
    _mc(
        pdf, 4,
        "Nota al pie en letra muy pequeña con más de veinte palabras para evaluar la regla de letra chica en pasajes extensos que dificultan la lectura prolongada.",
    )
    pdf.ln(4)
    pdf.set_font("DejaVu", "", 11)
    _mc(
        pdf, 6,
        "ESTE PARRAFO COMPLETO ESTA ESCRITO EN MAYUSCULAS SOSTENIDAS PARA COMPROBAR LA DETECCION DE TIPOGRAFIA POCO LEGIBLE EN DOCUMENTOS.",
    )
    pdf.output(str(PDF_DIR / "02_pdf_legibilidad_contraste_daltonismo.pdf"))

    # 3. Imágenes: gráfico solo color + texto incrustado
    pdf = _new_unicode_pdf("Informe con gráficos e imágenes")
    pdf.set_font("DejaVu", "B", 15)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(text="Análisis de resultados del trimestre", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("DejaVu", "", 11)
    _mc(pdf, 6, "Observá el gráfico de arriba para responder las consignas de la actividad.")
    pdf.ln(3)
    chart_stream = io.BytesIO(_make_color_chart_png())
    pdf.image(chart_stream, x=25, w=140)
    pdf.ln(6)
    _mc(pdf, 6, "Leé atentamente las condiciones del recuadro inferior antes de entregar.")
    pdf.ln(3)
    text_img_stream = io.BytesIO(_make_embedded_text_png())
    pdf.image(text_img_stream, x=25, w=140)
    pdf.output(str(PDF_DIR / "03_pdf_imagenes_grafico_color_y_texto.pdf"))

    # 4. PDF escaneado sin texto digital
    pdf = _new_unicode_pdf("Escaneo sin capa de texto")
    scan_stream = io.BytesIO(_make_scanned_page_png())
    pdf.image(scan_stream, x=10, y=10, w=190)
    pdf.output(str(PDF_DIR / "04_pdf_escaneado_solo_imagen.pdf"))


def _set_cell_shading(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def generate_docxs() -> None:
    # 1. Control accesible
    doc = Document()
    h1 = doc.add_heading("Unidad 2: El ciclo del agua", level=1)
    for run in h1.runs:
        run.font.name = "Arial"
    p = doc.add_paragraph("El agua circula continuamente entre la atmósfera, la tierra y los océanos.")
    p.paragraph_format.line_spacing = 1.5
    for run in p.runs:
        run.font.name = "Arial"
        run.font.size = Pt(12)
    doc.add_heading("Etapas principales", level=2)
    for item in ("Evaporación: el agua pasa de líquido a vapor.", "Condensación: se forman las nubes.", "Precipitación: el agua cae en forma de lluvia o nieve."):
        lp = doc.add_paragraph(item, style="List Bullet")
        lp.paragraph_format.line_spacing = 1.5
    doc.save(str(DOCX_DIR / "01_docx_control_accesible.docx"))

    # 2. Estructura, muro de texto y consignas complejas
    doc = Document()
    dense = (
        "En el siglo XIX se produjeron transformaciones profundas en la organización económica y social de América Latina "
        "que modificaron las relaciones laborales, la distribución de la población entre el campo y las ciudades, el desarrollo "
        "de la infraestructura ferroviaria y portuaria, la inserción en el mercado internacional mediante la exportación de materias "
        "primas y la consolidación de los Estados nacionales modernos a través de nuevas instituciones educativas y jurídicas. "
    ) * 6
    p = doc.add_paragraph(dense.strip())
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.line_spacing = 1.0
    p2 = doc.add_paragraph(
        "Leé atentamente el texto completo, subrayá las ideas principales, resumí cada párrafo en tu carpeta, "
        "compará los datos con el capítulo anterior y respondé el cuestionario final antes del viernes."
    )
    p2.paragraph_format.line_spacing = 1.0
    doc.save(str(DOCX_DIR / "02_docx_estructura_consignas_densas.docx"))

    # 3. Solo color, daltonismo y tabla compleja
    doc = Document()
    doc.add_heading("Actividad de clasificación", level=1)
    p = doc.add_paragraph("Marcá los de color azul y pintá de amarillo lo resaltado. ")
    r_green = p.add_run("Estos términos son conceptos clave en verde.")
    r_green.font.color.rgb = RGBColor(0x2E, 0x7D, 0x32)
    p2 = doc.add_paragraph()
    r_brown = p2.add_run("Estos otros términos son ejemplos secundarios en marrón.")
    r_brown.font.color.rgb = RGBColor(0x79, 0x55, 0x48)
    p3 = doc.add_paragraph()
    r_under = p3.add_run("Este pasaje completo está subrayado sin ser un hipervínculo para probar la regla tipográfica.")
    r_under.underline = True
    table = doc.add_table(rows=3, cols=3)
    for r_idx, row in enumerate(table.rows):
        for c_idx, cell in enumerate(row.cells):
            cell.text = f"Dato {r_idx + 1}-{c_idx + 1}"
            if r_idx == 0:
                _set_cell_shading(cell, "D9E2F3")
    doc.save(str(DOCX_DIR / "03_docx_solo_color_y_tablas.docx"))

    # 4. Imagen sin alt text + Unicode
    doc = Document()
    doc.add_heading("Guía con símbolos Unicode e imagen sin alt text", level=1)
    doc.add_paragraph("Relación matemática: Δx ≥ 0 → resultado válido ⚠️. Alfabeto griego: α, β, γ.")
    img_stream = io.BytesIO(_make_color_chart_png())
    doc.add_picture(img_stream, width=Inches(4.5))
    doc.save(str(DOCX_DIR / "04_docx_imagenes_sin_alt_y_unicode.docx"))


def generate_pptxs() -> None:
    # 1. Control accesible
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Introducción a la Energía Renovable"
    tf = slide.placeholders[1].text_frame
    tf.text = "La energía solar aprovecha la radiación del sol."
    p = tf.add_paragraph()
    p.text = "La energía eólica utiliza la fuerza del viento."
    for para in tf.paragraphs:
        for run in para.runs:
            run.font.name = "Arial"
            run.font.size = PptxPt(22)
    prs.save(str(PPTX_DIR / "01_pptx_control_accesible.pptx"))

    # 2. Bajo contraste y fuente chica
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = PptxRGB(0x1E, 0x29, 0x3B)
    box = slide.shapes.add_textbox(PptxInches(0.8), PptxInches(0.8), PptxInches(8.0), PptxInches(4.0))
    tf = box.text_frame
    tf.word_wrap = True
    p1 = tf.paragraphs[0]
    r1 = p1.add_run()
    r1.text = "Este texto en azul oscuro sobre fondo oscuro tiene muy bajo contraste y dificulta la lectura en clase."
    r1.font.size = PptxPt(14)
    r1.font.color.rgb = PptxRGB(0x2B, 0x3A, 0x55)
    p2 = tf.add_paragraph()
    r2 = p2.add_run()
    r2.text = "Texto en tamaño muy pequeño de ocho puntos con varias palabras para activar la alerta de letra chica en la diapositiva."
    r2.font.size = PptxPt(8)
    r2.font.color.rgb = PptxRGB(0xFF, 0xFF, 0xFF)
    prs.save(str(PPTX_DIR / "02_pptx_bajo_contraste_y_fuente_chica.pptx"))

    # 3. Gráfico dependiente del color + referencias espaciales
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Indicadores de desempeño"
    tf = slide.placeholders[1].text_frame
    tf.text = "Observá el gráfico de la derecha: los valores en rojo indican alerta y los verdes indican aprobación."
    chart_stream = io.BytesIO(_make_color_chart_png())
    slide.shapes.add_picture(chart_stream, PptxInches(4.5), PptxInches(2.2), width=PptxInches(4.8))
    prs.save(str(PPTX_DIR / "03_pptx_grafico_color_y_referencias.pptx"))


def main() -> None:
    _setup_dirs()
    generate_pdfs()
    generate_docxs()
    generate_pptxs()
    print("Documentos de prueba generados en:", BASE_DIR)


if __name__ == "__main__":
    main()
