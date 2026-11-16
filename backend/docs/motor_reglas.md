# Motor de reglas automáticas y puntaje orientativo (Semanas 2 y 3)

El diagnóstico combina dos fuentes:

- **IA**: evalúa lo semántico (vocabulario, tecnicismos sin definir, consignas con varias acciones, ambigüedades). Es flexible, pero varía entre corridas y solo ve las primeras 3000 palabras.
- **Reglas** (`app/services/rules_service.py`): miden lo objetivo con Python puro. Dan siempre el mismo resultado, no consumen tokens y recorren **el material completo**.

`app/services/accessibility_service.py` une ambas en un único diagnóstico.

## Reglas

| Regla | Categoría | `para_revisar` | `barrera_detectada` |
|---|---|---|---|
| Oración extensa | `comprension` | más de 35 palabras | 50 palabras o más |
| Consignas multi-acción (Tarea #25) | `comprension` | 3 verbos de acción | 4 o más verbos de acción |
| Legibilidad Szigriszt-Pazos (Tarea #25) | `comprension` | IFSZ entre 40.0 y 49.9 (algo difícil) | IFSZ < 40.0 (muy difícil, doc ≥ 100 palabras) |
| Párrafo extenso ("muro de texto") | `estructura` | más de 150 palabras | 250 palabras o más |
| Documento sin títulos estructurados (PDF, Word o PowerPoint) | `estructura` | — | doc ≥ 150 palabras sin H1/H2 |
| Salto de jerarquía en títulos | `estructura` | salto de nivel (ej. H1 a H3) | — |
| Sección extensa sin subdivisiones | `estructura` | más de 300 palabras bajo un título | — |
| Referencias exclusivamente visuales (Tarea #25) | `accesibilidad_visual` | referencias a posición espacial ("a la derecha") o aspecto visual (WCAG 1.3.3) | — |
| Información solo por color (Issue #80, WCAG 1.4.1) | `accesibilidad_visual` | frases de consigna o distinción que dependen solo del color ("están en verde", "pintá de rojo", "lo resaltado") | — |
| Colores problemáticos para daltonismo (Issue #80, solo archivos) | `accesibilidad_visual` | pares de colores cromáticos en el texto que colapsan bajo protanopía, deuteranopía o tritanopía | — |
| Imágenes | `accesibilidad_visual` | hay imágenes sin texto alternativo conocido (en PDF no se puede verificar, cuentan todas; en Word y PowerPoint solo las que no lo tienen ni están marcadas como decorativas) | — |
| PDF escaneado | `accesibilidad_visual` | — | sin capa de texto seleccionable |
| Letra chica en el cuerpo (Issue #79, solo archivos) | `accesibilidad_visual` | — | tamaño predominante del texto < 9 pt |
| Pasaje largo en letra chica (Issue #79, solo archivos) | `accesibilidad_visual` | párrafo o bloque con 20+ palabras en < 8 pt (notas, epígrafes) | — |
| Contraste texto/fondo (Issue #79, WCAG 1.4.3, solo archivos) | `accesibilidad_visual` | texto normal entre 3:1 y 4,5:1 | menos de 3:1 (falla incluso como texto grande) |
| Cursiva en pasajes largos (Issue #79, solo archivos) | `accesibilidad_visual` | 20+ palabras en cursiva en un párrafo | — |
| MAYÚSCULAS sostenidas (Issue #79, solo archivos) | `accesibilidad_visual` | 12+ palabras en mayúsculas que son al menos el 80% del párrafo | — |
| Subrayado que no es enlace (Issue #79, solo archivos) | `accesibilidad_visual` | 5+ palabras subrayadas sin ser un enlace | — |
| Fuente decorativa o manuscrita (Issue #79, solo archivos) | `accesibilidad_visual` | 15+ palabras en una fuente decorativa | la fuente predominante del texto es decorativa |
| Texto justificado (Issue #79, Word y PowerPoint) | `accesibilidad_visual` | párrafos de 30+ palabras justificados (WCAG 1.4.8) | — |
| Interlineado menor a 1,5 (Issue #79, Word y PowerPoint) | `accesibilidad_visual` | párrafos de 30+ palabras con interlineado < 1,5 (WCAG 1.4.8) | — |

- Las palabras se cuentan con el mismo criterio que `DocumentService` (`\b\w+\b`).
- Se listan como máximo **3 barreras por regla** (las más extensas/relevantes). El total aparece en el comentario de la dimensión.
- Las barreras de reglas tienen `source="rules"`, `fragment_found=true` (la cita sale del texto, no puede ser una alucinación) y `suggested_rewrite=null`.
- En los párrafos y secciones extensas, `original_text` trae el fragmento inicial seguido de `…`.
- Los umbrales y pesos son constantes al comienzo de `rules_service.py`.

### Cómo se separan párrafos y oraciones

- **Párrafo**: cada renglón no vacío. Los títulos y los ítems de lista cuentan como bloques propios, porque ya son una división del texto.
- **PDF**: `DocumentService` extrae el texto por **bloques** de PyMuPDF. Une los renglones visuales de cada bloque (juntando las palabras cortadas con guion) y deja cada ítem de lista en su propio renglón. Sin esto, cada página contaría como un único párrafo y las oraciones quedarían cortadas en cada renglón.
- **Word y PowerPoint** (Issue #47): cada párrafo, título, ítem de lista o fila de tabla es un bloque propio. Los títulos salen de los estilos de Word (Título 1, Título 2… o nivel de esquema) y del título de cada diapositiva (portada H1, resto H2 si hay portada). Las viñetas y numeraciones se marcan con `• ` en el texto. Las diapositivas ocultas y las notas del orador no se analizan.
- **Oración**: termina en `.`, `!`, `?` o `…` seguido de espacio. Se protegen:
  - abreviaturas (`pág.`, `ej.`, `Dr.`, `aprox.`…);
  - iniciales (`J. Pérez`);
  - decimales (`3.5`);
  - marcadores de lista (`1. Leé…`);
  - puntos seguidos de minúscula (`etc. y…`).

### Legibilidad visual del archivo (Issue #79)

Las reglas viven en `app/services/legibility_rules.py` y los datos tipográficos los arma `app/services/legibility_extractor.py`, que hace su propia pasada sobre el archivo ya abierto (no modifica la extracción de texto ni la detección de títulos). El resultado queda en `ExtractedDocument.legibility`. No aplican al texto pegado (`source_type == "text"`, que no tiene tipografía) ni al PDF escaneado (ya tiene su propia barrera). No consumen tokens.

**Letra chica**

- **Tamaño del cuerpo**: el tamaño predominante ponderado por caracteres, entre los fragmentos con tamaño conocido. Si no se pudo medir ninguno, se usa `structure.body_font_size`.
  - **PDF**: tamaño de cada span de PyMuPDF.
  - **Word**: tamaño del run; si no lo define, el del estilo de carácter, el del estilo de párrafo (y sus estilos base) y por último `docDefaults` (Word usa 10 pt si no está). Incluye celdas de tabla.
  - **PowerPoint**: tamaño del run o del párrafo, multiplicado por la reducción automática del cuadro (`normAutofit fontScale`). Incluye grupos y tablas; se saltean las diapositivas ocultas.
- **Pasaje**: un bloque de texto del PDF o un párrafo de Word/PowerPoint. Cuenta como "letra chica" si tiene **20 palabras o más** en menos de **8 pt**: así no se marcan números de página, fuentes ni pies de foto cortos.
- Si todo el cuerpo ya está en letra chica, no se lista además cada pasaje: alcanza con la barrera del cuerpo.
- Las barreras de esta regla no tienen `anchor`: una barrera de la IA sobre el mismo texto (por ejemplo, de comprensión) habla de otro problema y no debe ocultarla.
- En los pasajes, `original_text` es el comienzo del pasaje, y la página o diapositiva va en `issue` (Word no informa páginas). En el cuerpo, `original_text` es un resumen entre corchetes y `fragment_found` es `null`, como en el resto de las barreras de documento completo.
- Umbrales: `MIN_BODY_FONT_PT` (9) en `legibility_rules.py`; `SMALL_PASSAGE_PT` (8) y `MIN_SMALL_PASSAGE_WORDS` (20) en `legibility_extractor.py`.

**Contraste (WCAG 1.4.3, nivel AA)**

- Por cada fragmento de texto se calcula la relación de contraste entre su color y el de su fondo, con la fórmula de luminancia relativa de WCAG (de 1:1 a 21:1). Mínimo: **4,5:1** para texto normal y **3:1** para texto grande (18 pt o más, o 14 pt o más en negrita).
- **Severidad**: por debajo de 3:1 el texto falla incluso como texto grande → `barrera_detectada`. Texto normal entre 3:1 y 4,5:1 → `para_revisar`.
- **Pasaje**: el mismo bloque del PDF o párrafo de Word/PowerPoint que en la letra chica. Se marca si tiene **5 palabras o más** con bajo contraste, para no marcar un "Página 1 de 3" en gris. Se informan los 3 pasajes de peor contraste; el total va al comentario.
- **Color del texto y del fondo por formato**:
  - **PDF**: color de cada span de PyMuPDF. Fondo: el último rectángulo relleno (`page.get_drawings()`, opacidad ≥ 50%) que contiene el centro del texto; si no hay ninguno, blanco. El texto invisible (por ejemplo, la capa de OCR) no se evalúa.
  - **Word**: color del run o de sus estilos (RGB, o el valor calculado que Word guarda para los colores del tema). Fondo, en este orden: resaltado del run, sombreado del run, sombreado del párrafo, sombreado de la celda, color de página y, si no hay, blanco.
  - **PowerPoint**: casi todo usa colores del tema ("Texto 1", "Énfasis 2, más claro 40%"). Se resuelven con el tema del patrón: el `clrMap` traduce el nombre (por ejemplo, `tx1` → `dk1`; la diapositiva o el diseño pueden redefinirlo) y los modificadores `lumMod`/`lumOff` (en HSL, como PowerPoint), `tint` y `shade` lo aclaran u oscurecen. El color del texto sale del run, del párrafo o, si no lo define, se hereda en este orden: lista de estilos del cuadro, marcador de posición del diseño y del patrón, estilos de texto del patrón (título, cuerpo u otros), estilo de la forma (`fontRef`) y estilo por defecto de la presentación. Un enlace sin color toma el color de hipervínculo del tema. Fondo: relleno de la forma (propio, heredado del marcador de posición o del estilo de la forma `fillRef`) o, si no tiene, el de la diapositiva, su diseño o el patrón, incluido el fondo del tema (`bgRef`). Todo se lee del XML, sin modificar el archivo.
- Si no se conoce el color del texto o del fondo, ese fragmento **no se evalúa** (ver limitaciones). `contrast_measured_chars` indica cuánto texto se pudo evaluar.
- Si la lectura tipográfica falla con un archivo inesperado, el análisis sigue sin las reglas de legibilidad y se registra una advertencia en el log, en lugar de rechazar el material.
- **Informe final de adaptación**: las penalizaciones de legibilidad (`letra_chica_*`, `contraste_insuficiente`, `tipografia_*`) son reglas del archivo (`_FILE_RULES` en `adaptation_service.py`): adaptar el texto no cambia el formato del archivo original, así que se conservan en `score_after` y, sin cambios aplicados, el puntaje queda igual. Si una de ellas informó una barrera grave, la penalización trae `severe: true` y el informe conserva el tope de 89 (los puntos no alcanzan para saberlo: dos contrastes leves suman lo mismo que uno grave).
- Si no se conoce el tamaño (PowerPoint heredado del patrón), solo se marca lo que falla incluso con el umbral de texto grande (3:1).
- Cada barrera indica los dos colores en hexadecimal, la relación obtenida y la exigida, y la página o diapositiva.
- Umbrales: `NORMAL_TEXT_MIN_RATIO` (4,5), `LARGE_TEXT_MIN_RATIO` (3), `LARGE_TEXT_PT` (18), `LARGE_BOLD_TEXT_PT` (14) y `MIN_LOW_CONTRAST_WORDS` (5) en `legibility_extractor.py`.

### Información solo por color y daltonismo (Issue #80)

1. **Referencias solo por color en el texto (WCAG 1.4.1)**: `_color_only_findings()` en `rules_service.py` detecta frases donde el color o resaltado es el único medio de distinción (por ejemplo `"están en verde"`, `"las incorrectas en rojo"`, `"marcado en rojo"`, `"los de color azul"`, `"pintá de rojo"`, `"lo resaltado"`), contemplando voseo y tuteo.
   - *Limitación*: menciones descriptivas sin rol de indicador (como `"el color verde de las hojas"` o `"las hojas son verdes por la clorofila"`) no se marcan; expresiones nuevas o muy idiomáticas pueden requerir ampliar los patrones.
2. **Pares de colores problemáticos para daltonismo (solo archivos)**: `legibility_extractor.py` agrupa los colores cromáticos del texto (croma ≥ 40, mínimo 4 caracteres) y simula protanopía, deuteranopía y tritanopía mediante matrices de Viénot en sRGB lineal. Si dos colores bien diferenciados en visión normal (`distancia ≥ 60`) colapsan en alguna simulación (`distancia < 45` y relación `< 0,42`), `colorblind_assessment()` genera una barrera `para_revisar` (`colores_daltonismo`, 4 puntos por par, tope 8).
   - *Limitación*: evalúa colores de texto extraídos del archivo; si el color está dentro de una imagen o gráfico rasterizado, la detección queda a cargo de la IA de visión.
3. **IA de visión (`alt_text_service.py`)**: en la **misma** llamada multimodal del texto alternativo (sin costo extra de tokens), cada imagen informa `relies_on_color` (leyendas, mapas, semáforos dependientes solo del color) y `has_untranscribed_text` (texto relevante dentro de la imagen ausente en el documento). `accessibility_service.py` convierte esas señales en barreras de `accesibilidad_visual` (`source="ai"`).

**Tipografía poco legible**

La agrupación por regla está en `app/services/legibility_typography.py`; el extractor resuelve el formato de cada fragmento y de cada párrafo. Respaldo: WCAG 1.4.8 (nivel AAA: texto no justificado e interlineado de al menos 1,5) y la [guía de estilo de la British Dyslexia Association](https://www.wigan.gov.uk/Docs/PDF/Business/Professionals/SEN/HEFA/Dyslexia-Style-Guide.pdf) (evitar cursiva, subrayado y mayúsculas sostenidas; fuentes simples; alineación a la izquierda; interlineado de 1,5).

- **Una barrera por regla**, con la cantidad de párrafos afectados, el comienzo del primero como `original_text` y las páginas o diapositivas donde aparece (las primeras 10). Así un documento todo justificado no genera una barrera por párrafo.
- **Se marcan pasajes, no palabras sueltas**: una palabra en cursiva, un "Importante:" subrayado, un título o una sigla en mayúsculas no cuentan. Los mínimos de palabras (`MIN_ITALIC_WORDS` 20, `MIN_CAPS_WORDS` 12 con `MIN_CAPS_RATIO` 80%, `MIN_UNDERLINE_WORDS` 5, `MIN_DECORATIVE_WORDS` 15, `MIN_LAYOUT_PARAGRAPH_WORDS` 30) son un punto de partida, no salen de una norma: hay que calibrarlos con materiales reales.
- **Interlineado**: el issue proponía 1,15; el equipo eligió **1,5** (`MIN_LINE_SPACING`), que es lo que piden WCAG 1.4.8 y la British Dyslexia Association. Como Word trae 1,08 por defecto y PowerPoint 1,0 o 0,9, la regla va a aparecer en muchos materiales: por eso es `para_revisar` con una penalización chica. Sin interlineado definido, se toma sencillo (1,0), como Word y PowerPoint.
- **Fuentes decorativas**: lista curada de fuentes de script, manuscritas o de fantasía frecuentes (`DECORATIVE_FONTS`), más los nombres que contienen "script", "handwriting" o "calligraph". Comic Sans no se marca: la guía de la British Dyslexia Association la recomienda. Si la fuente predominante del texto es decorativa → `barrera_detectada`.
- **Por formato**:
  - **PDF**: cursiva por la marca de la fuente o su nombre (Italic, Oblique); fuente de cada span; subrayado detectado como una línea fina dibujada justo debajo de la base del texto, que cubre al menos el 70% del fragmento y no es más ancha que el renglón (para no confundirla con el borde de una celda); los fragmentos dentro de un enlace no cuentan. El texto invisible no se evalúa. Justificado e interlineado no se evalúan: el PDF no los guarda como formato.
  - **Word**: cursiva, subrayado, "Todo mayúsculas" y fuente del run o heredados de sus estilos; la fuente del tema (`asciiTheme`) se resuelve con el tema del documento. El texto con estilo de hipervínculo no cuenta como subrayado. Alineación (`w:jc`) e interlineado (`w:spacing`) del párrafo, de su estilo o de `docDefaults`; el interlineado exacto o mínimo en puntos se divide por el tamaño de la letra.
  - **PowerPoint**: los mismos datos del run, del párrafo o heredados por la misma cadena que el color; la fuente del tema (`+mn-lt`, `+mj-lt`) se resuelve con el tema del patrón. Los enlaces (`hlinkClick`) no cuentan como subrayado. "Reducir el texto al desbordar" (`lnSpcReduction`) también achica el interlineado.

## Unión con la IA

1. **Sin duplicados.** Si la IA ya señaló el mismo texto que una regla, se lista solo la barrera de la IA, porque trae `suggested_rewrite`. La regla igual cuenta para el puntaje.
   - En oraciones: alcanza con que las citas se superpongan.
   - En párrafos extensos: la barrera de la IA tiene que ser de `estructura` y citar el comienzo del párrafo. Una barrera sobre una oración del medio habla de otro problema.
   - Las citas de la IA no verificadas (`fragment_found=false`) nunca reemplazan a una regla.
2. **Semáforo coherente.** Cada dimensión toma el peor estado entre IA y reglas, y el comentario suma "Reglas automáticas: …". Así no se muestra "correcta" junto a una barrera de esa categoría.
3. **Orden.** Primero las barreras `barrera_detectada` y después las `para_revisar`. Dentro de cada grupo se respeta el orden de impacto de la IA.
4. **Identificadores.** Los `id` (`bar-1`, `bar-2`…) se asignan al final, sobre la lista ya unida.

## Puntaje orientativo (0-100)

```
rules_score = 100 − penalizaciones

  oraciones_extensas       mín(30, % de oraciones extensas + 3 × oraciones de 50+ palabras)
  consignas_multiaccion    mín(15, 5 × consignas con múltiples acciones)
  legibilidad_baja         10 (IFSZ 40-49) o 15 (IFSZ < 40)
  parrafos_extensos        mín(30, 6 × párrafos de 151-249 palabras + 10 × párrafos de 250+)
  pdf_sin_titulos          20
  salto_jerarquia_titulos  mín(12, 6 × saltos de nivel)
  secciones_extensas       mín(10, 5 × secciones > 300 palabras)
  referencias_visuales     mín(16, 8 × referencias exclusivamente espaciales o de color)
  pdf_escaneado            40
  imagenes_sin_verificar   10   (solo si no es escaneado y hay imágenes sin texto alternativo conocido)
  letra_chica_cuerpo       15   (cuerpo del texto < 9 pt)
  letra_chica_pasajes      mín(15, 5 × pasajes de 20+ palabras en < 8 pt)   (no se suma si ya hay letra_chica_cuerpo)
  contraste_insuficiente   mín(16, 8 × pasajes < 3:1 + 4 × pasajes entre 3:1 y 4,5:1)
  tipografia_*             4 por regla (8 si la fuente principal es decorativa); entre todas, máx. 12
                           (las barreras que superan el tope se muestran, pero no figuran en el desglose)

estimated_score = round(0,7 × puntaje_IA + 0,3 × rules_score)

Topes (el primero que corresponda):
  sin texto digital                → máx. 15
  PDF escaneado                    → máx. 40
  alguna barrera grave de reglas   → máx. 89   (no puede figurar como "muy accesible")
```

- **Por qué ponderar en lugar de restar:** la IA ya considera la longitud de las oraciones. Restarle penalizaciones contaría dos veces lo mismo. La parte determinística además reduce la variación del puntaje entre corridas (ver `riesgos_limitaciones_semana1_ia.md`).
- **Por qué se usa el porcentaje de oraciones:** un cuadernillo de 2000 palabras no debe quedar penalizado solo por ser largo.
- **Sin IA** (PDF sin texto), el puntaje es el de reglas con su tope.

La respuesta expone el cálculo en `score_breakdown`: `ai_score`, `rules_score`, pesos, penalizaciones, tope aplicado y su motivo. Las métricas crudas van en `metadata.rules_metrics`. Frontend puede usar ambos para mostrar "¿cómo se calculó este puntaje?".

### Calibración inicial

Resultados de `python -m scripts.benchmark_analysis --rules-only` sobre los fixtures. El puntaje IA es el promedio del benchmark del 23/09 (`benchmarks/analysis_raw_20260923_1957.json`):

| Texto | Oraciones extensas (graves) | Puntaje IA | Puntaje reglas | Final |
|---|---|---:|---:|---:|
| 01_consigna_simple | 0 (0) | 96 | 100 | 97 |
| 02_consigna_multiaccion | 1 (1), de 145 palabras | 52 | 70 | 57 |
| 03_texto_tecnico_quimica | 0 (0) | 95 | 100 | 96 |
| 04_material_500_palabras | 5 (1) | 65 | 81 | 70 |
| 05_material_2000_palabras | 2 (2) | 85 | 93 | 87 |

Ningún fixture tiene párrafos de más de 150 palabras. Conviene sumar un material real con muros de texto para calibrar esa regla.

## Limitaciones conocidas

- Si el material pegado viene con renglones cortados a mano (por ejemplo, copiado de un correo), cada renglón cuenta como párrafo: no se detectan muros de texto y las oraciones quedan partidas.
- Un párrafo que continúa en la página siguiente del PDF se cuenta como dos.
- Las reglas solo miden algunos aspectos objetivos: que no detecten nada no significa que el material sea accesible. Por eso pesan 30% y la IA 70%.
- **Letra chica en PowerPoint**: el texto que hereda el tamaño del diseño o del patrón de diapositivas (lo habitual en los marcadores de posición) no se mide. Esos fragmentos no se cuentan, en lugar de suponer un tamaño.
- **Letra chica en Word**: todos los pasajes figuran en la página 1, porque el archivo no guarda en qué página cae cada párrafo. El tamaño de los cuadros de texto y de los encabezados y pies de página no se mide.
- **Contraste en Word**: el color "Automático" no se evalúa, porque Word elige negro o blanco según el fondo. Los colores del tema sí: Word guarda junto a ellos el color ya calculado (`w:val`), y es el que se usa; solo un color del tema sin ese valor (raro, lo generan algunas herramientas) queda sin evaluar. Tampoco se miden los cuadros de texto ni el texto sobre imágenes.
- **Contraste en PowerPoint**: los fondos y rellenos con degradado, imagen o trama no se evalúan (el color cambia de un punto a otro), y tampoco el texto con degradado o muy transparente. Las celdas de tabla sin relleno propio no se evalúan, porque su color sale del estilo de tabla. Si un marcador de posición redefine el color del texto con una regla que no está en estas fuentes, se usa el del patrón.
- **Contraste en PDF**: el texto sobre una imagen (por ejemplo, una foto de fondo) se compara con blanco, porque no se analiza la imagen. Tampoco se consideran las transparencias ni el orden en que se dibujaron el texto y los rectángulos.
- **Tipografía en PDF**: no se evalúan justificado ni interlineado. Un subrayado hecho de otra forma (por ejemplo, como parte de la fuente o con un dibujo que no es una línea) no se detecta, y una línea dibujada justo debajo del texto por otro motivo podría tomarse como subrayado.
- **Tipografía en Word**: no se evalúan los cuadros de texto ni los encabezados y pies de página, y el texto dentro de un hipervínculo no entra en ninguna regla de legibilidad. Las fuentes de un estilo vinculado al tema que no está en el archivo se toman como no decorativas.
- **Fuentes decorativas**: una fuente decorativa que no está en la lista ni tiene "script", "handwriting" o "calligraph" en el nombre no se detecta.
- **Letra chica en PDF**: un PDF que se generó achicando páginas (por ejemplo, dos por hoja) puede tener letra legible al imprimir aunque los puntos digan otra cosa: la regla mide el tamaño declarado en el archivo.

## Próximos pasos (producto final)

1. Si la IA no responde (429/503), devolver el diagnóstico solo con reglas (`degraded: true`) en lugar de un error.
2. Posición exacta de cada barrera de reglas (`char_start`/`char_end`) para resaltarla en el Frontend y adaptarla en las Semanas 5 y 6.
3. Índice de legibilidad en español (Fernández-Huerta / INFLESZ).
4. Más reglas de texto: siglas sin desarrollar, enumeraciones en línea (`a) … b) …`) y material extenso sin títulos. Las MAYÚSCULAS sostenidas ya se evalúan en archivos (Issue #79); en el texto pegado todavía no.
5. Reglas del PDF: falta de etiquetas de estructura o idioma. La letra chica, el contraste y la tipografía ya están implementados (Issue #79).
6. Umbrales configurables por nivel educativo (secundario o superior).
