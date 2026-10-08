import re
import pymupdf
from app.schemas.document import DocumentStructure, ExtractedDocument, ExtractedImage, HeadingItem

# Límite máximo de palabras enviadas al análisis de Gemini en el escaneo inicial
# Previene saturar cuotas de Tokens por Minuto (TPM) en la capa gratuita
MAX_ANALYSIS_WORDS = 3000

# Umbrales para filtrado y extracción de imágenes en PDFs (Tarea #28)
MIN_IMAGE_DIMENSION_PX = 60
MIN_IMAGE_RENDER_PT = 35
MAX_ASPECT_RATIO = 8.0
MIN_ASPECT_RATIO = 0.125
MAX_IMAGES_FOR_ALT_TEXT = 5
MAX_IMAGE_SIDE_PX = 1200

# Renglones que inician un ítem de lista ("1.", "a)", "-", "•"): no se unen al renglón anterior.

_LIST_ITEM_RE = re.compile(r"^(?:[-•▪◦*·–]|\d{1,2}[.)]|[a-zA-Z][)])\s+")
# Palabra cortada con guion al final del renglón ("bio-" + "lógico").
_HYPHENATED_END_RE = re.compile(r"[^\W\d_]-$")


class DocumentService:
    """
    Servicio de extracción y procesamiento de documentos educativos.

    Implementa procesamiento 100% en memoria para cumplir con los requisitos
    de privacidad docente (no persiste archivos de estudiantes en disco).
    """

    @staticmethod
    def _reflow_block(block_text: str) -> str:
        """
        Une los renglones visuales de un bloque del PDF en un único párrafo.

        PyMuPDF devuelve un salto de línea por renglón impreso: sin esto, una
        oración que ocupa dos renglones queda partida y el motor de reglas no
        puede medir oraciones ni párrafos. Los ítems de lista conservan su salto.
        """
        lines: list[str] = []
        for line in (raw.strip() for raw in block_text.splitlines()):
            if not line:
                continue
            if not lines or _LIST_ITEM_RE.match(line):
                lines.append(line)
            elif _HYPHENATED_END_RE.search(lines[-1]) and line[0].islower():
                lines[-1] = lines[-1][:-1] + line
            else:
                lines[-1] = f"{lines[-1]} {line}"
        return "\n".join(lines)

    @classmethod
    def _extract_page_text(cls, page: pymupdf.Page) -> str:
        """Texto de la página con un párrafo por bloque, separados por línea en blanco."""
        # Cada bloque es (x0, y0, x1, y1, texto, nro_bloque, tipo); tipo 0 = texto, 1 = imagen.
        blocks = page.get_text("blocks")
        paragraphs = (cls._reflow_block(b[4]) for b in blocks if b[6] == 0)
        return "\n\n".join(p for p in paragraphs if p)

    @classmethod
    def _extract_pdf_structure(cls, doc: pymupdf.Document) -> DocumentStructure:
        """
        Infiere la estructura del PDF (títulos, jerarquía H1/H2/H3 y listas)
        a partir de los metadatos tipográficos y espaciales de PyMuPDF.
        """
        font_char_counts: dict[float, int] = {}
        raw_candidates: list[dict] = []
        list_items_count = 0

        # Pase 1: Calcular la moda de tamaño de fuente (cuerpo de texto) y recolectar candidatos
        for page_idx in range(len(doc)):
            page = doc.load_page(page_idx)
            page_height = page.rect.height
            page_dict = page.get_text("dict")

            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:  # 0 = texto
                    continue

                bbox = block.get("bbox", (0, 0, 0, 0))
                # Filtro zona muerta: encabezados repetidos (top 5%) o números de pie de página (bottom 5%)
                is_in_margin = (bbox[1] < page_height * 0.05) or (bbox[3] > page_height * 0.95)

                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    line_text = " ".join(s.get("text", "").strip() for s in spans if s.get("text", "").strip()).strip()
                    if not line_text:
                        continue

                    # Conteo de ítems de listas
                    if _LIST_ITEM_RE.match(line_text):
                        list_items_count += 1

                    for span in spans:
                        stext = span.get("text", "").strip()
                        if stext:
                            size = round(span.get("size", 10.0), 1)
                            font_char_counts[size] = font_char_counts.get(size, 0) + len(stext)

                    # Si está en margen superior/inferior y es corto o un número, ignorar como título
                    if is_in_margin and (len(line_text.split()) <= 4 or line_text.isdigit()):
                        continue

                    line_size = max((round(s.get("size", 10.0), 1) for s in spans), default=10.0)
                    is_bold = any(
                        bool(
                            (s.get("flags", 0) & 16)
                            or any(w in s.get("font", "").lower() for w in ("bold", "black", "heavy"))
                        )
                        for s in spans
                    )

                    raw_candidates.append({
                        "text": line_text,
                        "size": line_size,
                        "is_bold": is_bold,
                        "page_number": page_idx + 1,
                        "word_count": len(line_text.split()),
                    })

        if not font_char_counts:
            return DocumentStructure(
                has_headings=False,
                body_font_size=None,
                headings=[],
                hierarchy_levels=0,
                list_items_count=list_items_count,
            )

        body_font_size = max(font_char_counts, key=font_char_counts.get)

        # Pase 2: Filtrar líneas que califican como títulos / encabezados
        filtered_headings: list[dict] = []
        for cand in raw_candidates:
            text = cand["text"]
            size = cand["size"]
            is_bold = cand["is_bold"]
            words = cand["word_count"]

            if words > 20:
                continue

            is_heading = False
            # Caso A: Fuente visiblemente mayor al cuerpo (al menos 1.2 pt mayor)
            if size >= body_font_size + 1.2:
                # Si termina en punto pero es claramente mayor (+2.0pt), puede ser título. Si no, evitar oraciones comunes
                if not text.endswith(".") or size >= body_font_size + 2.0:
                    is_heading = True
            # Caso B: Fuente igual o similar al cuerpo pero con negrita destacada y pocas palabras (subtítulo)
            elif size >= body_font_size - 0.5 and is_bold and words <= 12 and not _LIST_ITEM_RE.match(text):
                if not text.endswith((".", ";", ",")):
                    is_heading = True

            if is_heading:
                # Si el encabezado anterior está en la misma página y tiene el mismo tamaño/estilo, unir si parece continuación
                if (
                    filtered_headings
                    and filtered_headings[-1]["page_number"] == cand["page_number"]
                    and abs(filtered_headings[-1]["size"] - size) <= 0.5
                    and filtered_headings[-1]["is_bold"] == is_bold
                    and (filtered_headings[-1]["word_count"] + words) <= 25
                    and not filtered_headings[-1]["text"].endswith((":", "?", "!"))
                ):
                    filtered_headings[-1]["text"] += f" {text}"
                    filtered_headings[-1]["word_count"] += words
                else:
                    filtered_headings.append(cand)

        if not filtered_headings:
            return DocumentStructure(
                has_headings=False,
                body_font_size=body_font_size,
                headings=[],
                hierarchy_levels=0,
                list_items_count=list_items_count,
            )

        # Pase 3: Agrupar tamaños con tolerancia (0.5 pt) y asignar niveles H1, H2, H3...
        unique_sizes = sorted({round(h["size"], 1) for h in filtered_headings}, reverse=True)
        size_clusters: list[float] = []
        for s in unique_sizes:
            if not size_clusters or not any(abs(s - c) <= 0.5 for c in size_clusters):
                size_clusters.append(s)

        headings: list[HeadingItem] = []
        for h in filtered_headings:
            level = 1
            for idx, c in enumerate(size_clusters, start=1):
                if abs(h["size"] - c) <= 0.5:
                    level = idx
                    break

            headings.append(
                HeadingItem(
                    level=level,
                    text=h["text"],
                    page_number=h["page_number"],
                    font_size=h["size"],
                    is_bold=h["is_bold"],
                )
            )

        return DocumentStructure(
            has_headings=True,
            body_font_size=body_font_size,
            headings=headings,
            hierarchy_levels=len(size_clusters),
            list_items_count=list_items_count,
        )

    @staticmethod
    def _prepare_analysis_text(full_text: str, words: list[str]) -> tuple[str, bool, list[str]]:
        """
        Recorta el texto si excede el límite seguro de tokens para Gemini
        y genera las advertencias pertinentes.
        """
        warnings = []
        word_count = len(words)
        is_truncated = False

        if word_count > MAX_ANALYSIS_WORDS:
            is_truncated = True
            text_for_analysis = " ".join(words[:MAX_ANALYSIS_WORDS])
            warnings.append(
                f"El material es extenso ({word_count} palabras). "
                f"Se optimizó el escaneo inicial para las primeras {MAX_ANALYSIS_WORDS} palabras para evitar demoras y saturación de cuotas."
            )
        else:
            text_for_analysis = full_text

        return text_for_analysis, is_truncated, warnings

    @classmethod
    def process_text(cls, raw_text: str, filename: str | None = None) -> ExtractedDocument:
        """
        Procesa texto plano ingresado o pegado directamente en la plataforma.
        """
        cleaned_text = raw_text.strip()
        words = re.findall(r'\b\w+\b', cleaned_text)
        word_count = len(words)
        character_count = len(cleaned_text)

        text_for_analysis, is_truncated, warnings = cls._prepare_analysis_text(cleaned_text, words)

        if word_count == 0:
            warnings.append("El texto ingresado no contiene palabras reconocibles.")

        list_items_count = sum(1 for line in cleaned_text.splitlines() if _LIST_ITEM_RE.match(line.strip()))
        structure = DocumentStructure(
            has_headings=False,
            body_font_size=None,
            headings=[],
            hierarchy_levels=0,
            list_items_count=list_items_count,
        )

        return ExtractedDocument(
            source_type="text",
            filename=filename,
            raw_text=cleaned_text,
            text_for_analysis=text_for_analysis,
            is_truncated=is_truncated,
            page_count=1,
            word_count=word_count,
            character_count=character_count,
            has_images=False,
            image_count=0,
            is_scanned_pdf=False,
            warnings=warnings,
            structure=structure,
        )

    @staticmethod
    def _decode_embedded_png(doc: pymupdf.Document, xref: int) -> tuple[bytes, int, int]:
        """Decodifica la imagen embebida como PNG. PNG solo admite Gray/RGB: CMYK, Lab, etc. se convierten."""
        pix = pymupdf.Pixmap(doc, xref)
        if pix.colorspace is None or pix.colorspace.n not in (1, 3):
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        # Reducir resolución si es excesiva (> MAX_IMAGE_SIDE_PX)
        while max(pix.width, pix.height) > MAX_IMAGE_SIDE_PX:
            pix.shrink(1)
        return pix.tobytes("png"), pix.width, pix.height

    @classmethod
    def _encode_image_png(
        cls, doc: pymupdf.Document, page: pymupdf.Page, img_info: tuple, rect: pymupdf.Rect
    ) -> tuple[bytes, int, int] | None:
        """
        Codifica una imagen del PDF como PNG para la IA de visión. Devuelve
        (bytes, ancho, alto) o None si ningún método pudo procesarla.

        1. Decodifica la imagen embebida (convertida a RGB si hace falta).
        2. Si falla, o la imagen tiene transparencia (smask, que el paso 1 ignora),
           renderiza la zona de la página tal como la vería un visor de PDF.
        """
        xref, smask = img_info[0], img_info[1]

        if not smask:
            try:
                return cls._decode_embedded_png(doc, xref)
            except Exception:
                pass

        try:
            clip = rect & page.rect
            if clip.is_empty:
                return None
            # Resolución nativa de la imagen, acotada para no superar MAX_IMAGE_SIDE_PX
            native_dpi = 72 * img_info[2] / max(rect.width, 1)
            max_dpi = 72 * MAX_IMAGE_SIDE_PX / max(clip.width, clip.height)
            dpi = max(72, min(native_dpi, max_dpi))
            pix = page.get_pixmap(clip=clip, dpi=int(dpi), colorspace=pymupdf.csRGB, alpha=False)
            return pix.tobytes("png"), pix.width, pix.height
        except Exception:
            return None

    @classmethod
    def _extract_images_and_context(
        cls, doc: pymupdf.Document
    ) -> tuple[int, list[ExtractedImage], list[str]]:
        """
        Extrae en memoria las imágenes relevantes de un PDF, filtrando elementos decorativos,
        íconos diminutos y encabezados/pies. Para cada imagen relevante, recolecta el texto
        circundante en la misma página como contexto pedagógico.
        """
        total_images = 0
        extracted: list[ExtractedImage] = []
        warnings: list[str] = []
        relevant_candidates_count = 0

        for page_idx in range(len(doc)):
            page = doc.load_page(page_idx)
            page_height = page.rect.height
            raw_images = page.get_images(full=True)
            total_images += len(raw_images)

            blocks = page.get_text("blocks")
            text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]

            for img_info in raw_images:
                xref = img_info[0]
                rects = page.get_image_rects(xref)
                if not rects:
                    continue

                for rect in rects:
                    # 1. Filtro de dimensiones renderizadas en página
                    if rect.width < MIN_IMAGE_RENDER_PT or rect.height < MIN_IMAGE_RENDER_PT:
                        continue

                    # 2. Filtro de encabezado o pie de página repetitivo (zona 7%)
                    is_in_margin = (rect.y1 < page_height * 0.07 or rect.y0 > page_height * 0.93)
                    if is_in_margin and rect.height < 75:
                        continue

                    # 3. Dimensiones nativas declaradas en el PDF (sin decodificar la imagen)
                    native_w, native_h = img_info[2], img_info[3]
                    if native_w < MIN_IMAGE_DIMENSION_PX or native_h < MIN_IMAGE_DIMENSION_PX:
                        continue

                    ratio = native_w / max(native_h, 1)
                    if ratio > MAX_ASPECT_RATIO or ratio < MIN_ASPECT_RATIO:
                        continue

                    relevant_candidates_count += 1
                    if len(extracted) >= MAX_IMAGES_FOR_ALT_TEXT:
                        continue

                    # 4. Ubicación espacial relativa
                    center_y = (rect.y0 + rect.y1) / 2.0
                    norm_y = center_y / max(page_height, 1.0)
                    if norm_y < 0.35:
                        pos_label = "sector superior"
                    elif norm_y > 0.65:
                        pos_label = "sector inferior"
                    else:
                        pos_label = "sector central"
                    location_desc = f"Página {page_idx + 1}, {pos_label}"

                    encoded = cls._encode_image_png(doc, page, img_info, rect)
                    if encoded is None:
                        # Sin bytes no hay propuesta de IA: avisar para revisión manual
                        warnings.append(
                            f"La imagen de la {location_desc.lower()} no pudo procesarse automáticamente; "
                            "revisá su texto alternativo manualmente."
                        )
                        continue
                    img_bytes, img_width, img_height = encoded

                    # 5. Capturar texto circundante
                    preceding = [
                        cls._reflow_block(b[4])
                        for b in text_blocks
                        if b[3] <= rect.y0 + 5
                    ]
                    following = [
                        cls._reflow_block(b[4])
                        for b in text_blocks
                        if b[1] >= rect.y1 - 5
                    ]

                    context_parts = []
                    if preceding:
                        context_parts.append(preceding[-1])
                    if following:
                        context_parts.append(following[0])

                    context_snippet = " [...] ".join(p.strip() for p in context_parts if p.strip())
                    words = context_snippet.split()
                    if len(words) > 120:
                        context_snippet = " ".join(words[:120]) + "..."

                    next_idx = len(extracted) + 1
                    extracted.append(
                        ExtractedImage(
                            image_index=next_idx,
                            page_number=page_idx + 1,
                            bbox=(
                                round(rect.x0, 1),
                                round(rect.y0, 1),
                                round(rect.x1, 1),
                                round(rect.y1, 1),
                            ),
                            width=img_width,
                            height=img_height,
                            location_description=location_desc,
                            context_text=context_snippet,
                            image_bytes=img_bytes,
                            mime_type="image/png",
                        )
                    )

        if relevant_candidates_count > MAX_IMAGES_FOR_ALT_TEXT:
            warnings.append(
                f"El documento contiene {relevant_candidates_count} imágenes relevantes; "
                f"se generaron propuestas de texto alternativo para las primeras {MAX_IMAGES_FOR_ALT_TEXT} para preservar cuota."
            )

        return total_images, extracted, warnings

    @classmethod
    def process_pdf(cls, file_bytes: bytes, filename: str) -> ExtractedDocument:
        """
        Abre y procesa un PDF directamente en memoria desde su stream de bytes.
        Extrae texto, detecta imágenes e identifica potenciales PDFs escaneados.
        """
        if not file_bytes:
            raise ValueError("El archivo PDF recibido está vacío (0 bytes).")

        doc = None
        try:
            # Abrir stream en memoria (sin tocar disco rígido)
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")

            if doc.is_encrypted:
                raise ValueError("El archivo PDF está protegido con contraseña y no puede ser analizado.")

            page_count = len(doc)
            if page_count == 0:
                raise ValueError("El documento PDF no contiene páginas legibles.")

            extracted_pages_text = []
            for page_idx in range(page_count):
                page = doc.load_page(page_idx)
                extracted_pages_text.append(cls._extract_page_text(page))

            total_images, extracted_images, image_warnings = cls._extract_images_and_context(doc)

            full_text = "\n\n".join(extracted_pages_text).strip()
            words = re.findall(r'\b\w+\b', full_text)
            word_count = len(words)
            character_count = len(full_text)

            text_for_analysis, is_truncated, length_warnings = cls._prepare_analysis_text(full_text, words)
            warnings = list(length_warnings) + image_warnings
            is_scanned = False

            # Heurística corregida de PDF escaneado (fotocopias sin texto digital)
            if word_count == 0:
                is_scanned = True
                warnings.append(
                    "El documento no contiene texto digital seleccionable. "
                    "Parece ser un archivo escaneado que requiere OCR para ser analizado."
                )
            elif word_count < 25 and total_images >= page_count:
                is_scanned = True
                warnings.append(
                    "El documento parece contener páginas fotografiadas o escaneadas con muy poco texto digital seleccionable."
                )

            if total_images > 0:
                warnings.append(
                    f"Se detectaron {total_images} imagen(es) en el documento. "
                    "El escáner de accesibilidad verificará la presencia de descripciones alternativas."
                )

            structure = cls._extract_pdf_structure(doc)

            return ExtractedDocument(
                source_type="pdf",
                filename=filename,
                raw_text=full_text,
                text_for_analysis=text_for_analysis,
                is_truncated=is_truncated,
                page_count=page_count,
                word_count=word_count,
                character_count=character_count,
                has_images=(total_images > 0),
                image_count=total_images,
                is_scanned_pdf=is_scanned,
                warnings=warnings,
                structure=structure,
                extracted_images=extracted_images,
            )

        except Exception as e:
            if isinstance(e, ValueError):
                raise e
            raise ValueError(f"No se pudo procesar el archivo PDF: {str(e)}") from e
        finally:
            if doc is not None:
                doc.close()



document_service = DocumentService()
