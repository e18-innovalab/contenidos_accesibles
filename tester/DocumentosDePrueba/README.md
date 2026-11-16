# Documentos de Prueba (`tester/DocumentosDePrueba/`)

Suite acotada de materiales educativos en **todos los formatos aceptados** (`.pdf`, `.docx`, `.pptx`) para evaluar el escáner de accesibilidad, las adaptaciones, las exportaciones y la calibración (#181, #43).

## Regeneración

Desde la raíz del repositorio:

```bash
backend/venv/bin/python tester/DocumentosDePrueba/generar_documentos.py
```

---

## Catálogo de documentos

### PDF (`pdf/`)

| Archivo | Qué evalúa | Resultado esperado |
|---|---|---|
| `01_pdf_control_accesible.pdf` | Documento control accesible (12 pt, alto contraste, oraciones cortas) | `0` barreras en el motor de reglas |
| `02_pdf_legibilidad_contraste_daltonismo.pdf` | Letra chica (7 pt), bajo contraste (`#AAAAAA` sobre blanco), mayúsculas sostenidas, referencia `"en verde"` / `"en rojo"` | Barreras de legibilidad visual, tipografía y solo color / daltonismo |
| `03_pdf_imagenes_grafico_color_y_texto.pdf` | Referencia espacial (`"gráfico de arriba"`), gráfico de barras rojo/verde sin etiquetas, imagen con texto incrustado ausente en el documento | Barrera de imágenes sin alt text, referencia visual y señales de color/texto en IA de visión |
| `04_pdf_escaneado_solo_imagen.pdf` | Página rasterizada sin capa de texto seleccionable | `is_scanned_pdf = true` (`word_count = 0`) |

### Word (`docx/`)

| Archivo | Qué evalúa | Resultado esperado |
|---|---|---|
| `01_docx_control_accesible.docx` | Documento control accesible (títulos `H1`/`H2`, Arial 12 pt, interlineado 1,5, listas) | `0` barreras en el motor de reglas |
| `02_docx_estructura_consignas_densas.docx` | Muro de texto >300 palabras sin títulos, oraciones largas, consignas con múltiples acciones en voseo, justificado e interlineado 1,0 | Múltiples barreras de comprensión, estructura y tipografía |
| `03_docx_solo_color_y_tablas.docx` | Frases `"los de color azul"`, `"pintá de amarillo"`, `"lo resaltado"`, texto en verde/marrón, subrayado largo sin enlace y tabla | Barreras de solo color y tipografía |
| `04_docx_imagenes_sin_alt_y_unicode.docx` | Imagen incrustada sin texto alternativo + símbolos Unicode (`Δ`, `≥`, `→`, `α`, `β`, `γ`, `⚠️`) | Barrera de imagen sin alt text; útil para probar exportación PDF Unicode (#87) |

### PowerPoint (`pptx/`)

| Archivo | Qué evalúa | Resultado esperado |
|---|---|---|
| `01_pptx_control_accesible.pptx` | Presentación control accesible (Arial 22 pt, alto contraste, títulos y viñetas breves) | `0` barreras en el motor de reglas |
| `02_pptx_bajo_contraste_y_fuente_chica.pptx` | Texto azul oscuro sobre fondo oscuro (bajo contraste) y pasaje en 8 pt | Barreras de contraste insuficiente y letra chica |
| `03_pptx_grafico_color_y_referencias.pptx` | Gráfico rojo/verde sin alt text + referencia espacial (`"de la derecha"`) y mención de colores | Barrera de imagen sin alt text y referencia visual |
