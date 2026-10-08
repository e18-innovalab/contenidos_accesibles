from typing import Literal
from pydantic import BaseModel, Field


MAX_RAW_TEXT_CHARS = 50_000


class TextInputRequest(BaseModel):
    """Esquema para recepción de texto pegado directamente por el docente."""
    text: str = Field(
        ...,
        min_length=10,
        max_length=MAX_RAW_TEXT_CHARS,
        description=f"Texto educativo a analizar (entre 10 y {MAX_RAW_TEXT_CHARS} caracteres)."
    )


class HeadingItem(BaseModel):
    """Encabezado o título detectado en el documento (inferido tipográficamente en PDFs)."""
    level: int = Field(
        description="Nivel jerárquico inferido: 1 para H1 (título principal), 2 para H2 (subtítulo/sección), etc."
    )
    text: str = Field(description="Texto del encabezado.")
    page_number: int = Field(default=1, ge=1, description="Número de página donde se encuentra.")
    font_size: float = Field(description="Tamaño de fuente estimado en puntos (pt).")
    is_bold: bool = Field(default=False, description="True si la fuente presenta peso de negrita (bold).")


class DocumentStructure(BaseModel):
    """Estructura documental inferida a partir de metadatos tipográficos y espaciales."""
    has_headings: bool = Field(default=False, description="Indica si se detectaron títulos o subtítulos.")
    body_font_size: float | None = Field(default=None, description="Tamaño de fuente predominante (cuerpo del texto).")
    headings: list[HeadingItem] = Field(default_factory=list, description="Lista de encabezados ordenados por aparición.")
    hierarchy_levels: int = Field(default=0, ge=0, description="Cantidad de niveles jerárquicos distintos detectados.")
    list_items_count: int = Field(default=0, ge=0, description="Cantidad de ítems de lista (viñetas o numeración) detectados.")


class ExtractedDocument(BaseModel):
    """
    Contrato de datos común para la información extraída de cualquier material.
    Este esquema es generado por DocumentService y consumido por el motor de Gemini.
    """
    source_type: Literal["pdf", "text"] = Field(
        ..., description="Tipo de fuente procesada ('pdf' o 'text')."
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
        default=1, ge=1, description="Cantidad de páginas del documento."
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
    extracted_images: list["ExtractedImage"] = Field(
        default_factory=list,
        exclude=True,
        description="Imágenes relevantes extraídas en memoria (excluidas de serialización para garantizar privacidad)."
    )


class ExtractedImage(BaseModel):
    """Imagen relevante extraída en memoria de un PDF junto a sus metadatos y contexto textual."""
    image_index: int = Field(description="Índice secuencial de la imagen en el documento (1-based).")
    page_number: int = Field(description="Número de página donde se ubica (1-based).")
    bbox: tuple[float, float, float, float] = Field(description="Coordenadas espaciales (x0, y0, x1, y1) en la página.")
    width: int = Field(description="Ancho en píxeles.")
    height: int = Field(description="Alto en píxeles.")
    location_description: str = Field(description="Descripción textual de su ubicación (ej. 'Página 1, sector superior').")
    context_text: str = Field(default="", description="Texto circundante previo y posterior a la imagen.")
    image_bytes: bytes = Field(exclude=True, description="Bytes PNG de la imagen en memoria (excluido de serialización).")
    mime_type: str = Field(default="image/png", description="MIME type de la imagen.")


ExtractedDocument.model_rebuild()


