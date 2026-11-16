from typing import Literal
from pydantic import BaseModel, Field


MAX_RAW_TEXT_CHARS = 50_000

SourceType = Literal["pdf", "text", "docx", "pptx"]


class TextInputRequest(BaseModel):
    """Esquema para recepción de texto pegado directamente por el docente."""
    text: str = Field(
        ...,
        min_length=10,
        max_length=MAX_RAW_TEXT_CHARS,
        description=f"Texto educativo a analizar (entre 10 y {MAX_RAW_TEXT_CHARS} caracteres)."
    )


class HeadingItem(BaseModel):
    """Encabezado o título detectado en el documento (inferido tipográficamente en PDFs, por estilo en Word y PowerPoint)."""
    level: int = Field(
        description="Nivel jerárquico inferido: 1 para H1 (título principal), 2 para H2 (subtítulo/sección), etc."
    )
    text: str = Field(description="Texto del encabezado.")
    page_number: int = Field(default=1, ge=1, description="Número de página (o de diapositiva en PowerPoint) donde se encuentra.")
    font_size: float | None = Field(
        default=None,
        description="Tamaño de fuente estimado en puntos (pt). Puede faltar en Word y PowerPoint si el estilo no lo define.",
    )
    is_bold: bool = Field(default=False, description="True si la fuente presenta peso de negrita (bold).")


class DocumentStructure(BaseModel):
    """Estructura documental inferida a partir de metadatos tipográficos y espaciales."""
    has_headings: bool = Field(default=False, description="Indica si se detectaron títulos o subtítulos.")
    body_font_size: float | None = Field(default=None, description="Tamaño de fuente predominante (cuerpo del texto).")
    headings: list[HeadingItem] = Field(default_factory=list, description="Lista de encabezados ordenados por aparición.")
    hierarchy_levels: int = Field(default=0, ge=0, description="Cantidad de niveles jerárquicos distintos detectados.")
    list_items_count: int = Field(default=0, ge=0, description="Cantidad de ítems de lista (viñetas o numeración) detectados.")


class SmallTextPassage(BaseModel):
    """Párrafo o bloque escrito con letra más chica que el umbral de legibilidad (issue #79)."""
    text: str = Field(description="Texto del pasaje (recortado si es muy largo).")
    page_number: int = Field(default=1, ge=1, description="Página (o diapositiva en PowerPoint). En Word siempre es 1.")
    font_size: float = Field(description="Tamaño de letra predominante del pasaje, en puntos (pt).")
    word_count: int = Field(ge=0, description="Palabras del pasaje escritas con letra chica.")


class LegibilityStats(BaseModel):
    """Datos tipográficos que usan las reglas de legibilidad visual. Solo para archivos (no texto pegado)."""
    body_font_size: float | None = Field(
        default=None,
        description="Tamaño de letra predominante, ponderado por caracteres, de los fragmentos con tamaño conocido.",
    )
    measured_chars: int = Field(default=0, ge=0, description="Caracteres con tamaño de letra conocido.")
    small_text_passages: list[SmallTextPassage] = Field(
        default_factory=list,
        description="Pasajes con letra más chica que el umbral (los primeros; ver small_text_passages_total).",
    )
    small_text_passages_total: int = Field(default=0, ge=0, description="Cantidad total de pasajes con letra chica.")
    contrast_measured_chars: int = Field(
        default=0, ge=0, description="Caracteres con color de texto y de fondo conocidos (evaluables por contraste)."
    )
    low_contrast_passages: list["LowContrastPassage"] = Field(
        default_factory=list,
        description="Pasajes con contraste texto/fondo insuficiente (los primeros; ver low_contrast_passages_total).",
    )
    low_contrast_passages_total: int = Field(default=0, ge=0, description="Cantidad total de pasajes con bajo contraste.")
    body_font_name: str | None = Field(
        default=None, description="Fuente predominante del texto, ponderada por caracteres (si se conoce)."
    )
    body_font_decorative: bool = Field(
        default=False, description="True si la fuente predominante es decorativa o manuscrita."
    )
    typography_issues: list["TypographyIssue"] = Field(
        default_factory=list,
        description="Problemas de tipografía detectados, uno por regla (cursiva, mayúsculas, subrayado, etc.).",
    )
    colorblind_confusion_pairs: list["ColorConfusionPair"] = Field(
        default_factory=list,
        description="Pares de colores cromáticos en el texto que pueden confundirse con daltonismo (issue #80).",
    )


class TypographyIssue(BaseModel):
    """Una regla de tipografía poco legible y los párrafos donde aparece (issue #79, parte 3)."""
    rule: Literal["cursiva", "mayusculas", "subrayado", "fuente_decorativa", "justificado", "interlineado"]
    passages: int = Field(ge=1, description="Párrafos (o bloques del PDF) donde se detectó.")
    word_count: int = Field(ge=0, description="Palabras afectadas en total.")
    example: str = Field(description="Comienzo del primer pasaje afectado, tal como está en el texto.")
    pages: list[int] = Field(default_factory=list, description="Páginas o diapositivas (las primeras). Vacío en Word.")
    detail: str | None = Field(
        default=None, description="Dato que se informa: la fuente (fuente_decorativa) o el interlineado (interlineado)."
    )


class LowContrastPassage(BaseModel):
    """Párrafo o bloque cuyo texto no alcanza el contraste mínimo de WCAG 1.4.3 (issue #79, parte 2)."""
    text: str = Field(description="Texto del pasaje con bajo contraste (recortado si es muy largo).")
    page_number: int = Field(default=1, ge=1, description="Página (o diapositiva en PowerPoint). En Word siempre es 1.")
    text_color: str = Field(description="Color del texto, en hexadecimal (#RRGGBB).")
    background_color: str = Field(description="Color del fondo detrás del texto, en hexadecimal (#RRGGBB).")
    contrast_ratio: float = Field(description="Relación de contraste (1 a 21), redondeada a 2 decimales.")
    required_ratio: float = Field(description="Mínimo exigido: 4.5 para texto normal, 3 para texto grande.")
    is_large_text: bool = Field(description="True si el texto mide 18 pt o más, o 14 pt o más en negrita.")
    word_count: int = Field(ge=0, description="Palabras del pasaje con bajo contraste.")


class ColorConfusionPair(BaseModel):
    """Par de colores cromáticos usados en el texto que colapsan bajo daltonismo (issue #80)."""
    color_a: str = Field(description="Primer color en hexadecimal (#RRGGBB).")
    color_b: str = Field(description="Segundo color en hexadecimal (#RRGGBB).")
    deficiencies: list[str] = Field(
        default_factory=list,
        description="Tipos de daltonismo afectados: protanopia, deuteranopia y/o tritanopia.",
    )
    sample_a: str = Field(default="", description="Fragmento de ejemplo en el primer color.")
    sample_b: str = Field(default="", description="Fragmento de ejemplo en el segundo color.")
    page_number: int = Field(default=1, ge=1, description="Página donde aparece el primer color.")


class ExtractedDocument(BaseModel):
    """
    Contrato de datos común para la información extraída de cualquier material.
    Este esquema es generado por DocumentService y consumido por el motor de Gemini.
    """
    source_type: SourceType = Field(
        ..., description="Tipo de fuente procesada ('pdf', 'text', 'docx' o 'pptx')."
    )
    filename: str | None = Field(
        None, description="Nombre original del archivo (si aplica)."
    )
    raw_text: str = Field(
        ..., description="Contenido textual completo original extraído del material."
    )
    text_for_analysis: str = Field(
        ...,
        description="Texto optimizado y acotado para el análisis con Gemini (previene exceder límites de tokens)."
    )
    is_truncated: bool = Field(
        default=False,
        description="Indica si el texto para análisis debió ser acotado por exceder el límite seguro de longitud."
    )
    page_count: int = Field(
        default=1, ge=1, description="Cantidad de páginas del documento (diapositivas en PowerPoint)."
    )
    word_count: int = Field(
        ..., ge=0, description="Total de palabras extraídas."
    )
    character_count: int = Field(
        ..., ge=0, description="Total de caracteres (incluyendo espacios)."
    )
    has_images: bool = Field(
        default=False, description="Indica si se detectaron imágenes en el documento."
    )
    image_count: int = Field(
        default=0, ge=0, description="Cantidad total de imágenes detectadas."
    )
    images_with_alt_text: int = Field(
        default=0,
        ge=0,
        description=(
            "Imágenes que ya tienen texto alternativo o están marcadas como decorativas. "
            "Solo se detecta en Word y PowerPoint; en PDF siempre es 0."
        ),
    )
    is_scanned_pdf: bool = Field(
        default=False,
        description="Indica si parece ser un PDF escaneado (fotocopias o imágenes sin capa de texto)."
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Advertencias o anomalías detectadas durante el procesamiento."
    )
    structure: DocumentStructure = Field(
        default_factory=DocumentStructure,
        description="Estructura inferida del documento (encabezados, jerarquía, listas)."
    )
    legibility: LegibilityStats | None = Field(
        default=None,
        description="Tamaños de letra del archivo para las reglas de legibilidad. None en el texto pegado.",
    )
    extracted_images: list["ExtractedImage"] = Field(
        default_factory=list,
        exclude=True,
        description="Imágenes relevantes extraídas en memoria (excluidas de serialización para garantizar privacidad)."
    )


class ExtractedImage(BaseModel):
    """Imagen relevante extraída en memoria de un documento junto a sus metadatos y contexto textual."""
    image_index: int = Field(description="Índice secuencial de la imagen en el documento (1-based).")
    page_number: int = Field(description="Número de página o diapositiva donde se ubica (1-based; 1 en Word).")
    bbox: tuple[float, float, float, float] = Field(
        description="Coordenadas espaciales (x0, y0, x1, y1) en puntos dentro de la página o diapositiva (en Word, solo el tamaño)."
    )
    width: int = Field(description="Ancho en píxeles.")
    height: int = Field(description="Alto en píxeles.")
    location_description: str = Field(description="Descripción textual de su ubicación (ej. 'Página 1, sector superior').")
    context_text: str = Field(default="", description="Texto circundante previo y posterior a la imagen.")
    image_bytes: bytes = Field(exclude=True, description="Bytes PNG de la imagen en memoria (excluido de serialización).")
    mime_type: str = Field(default="image/png", description="MIME type de la imagen.")


LegibilityStats.model_rebuild()
ExtractedDocument.model_rebuild()


