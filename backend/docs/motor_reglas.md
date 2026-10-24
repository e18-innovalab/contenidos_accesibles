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
| Referencias exclusivamente visuales (Tarea #25) | `accesibilidad_visual` | referencias a posición espacial ("a la derecha") o color sin texto alternativo (WCAG 1.3.3) | — |
| Imágenes | `accesibilidad_visual` | hay imágenes sin texto alternativo conocido (en PDF no se puede verificar, cuentan todas; en Word y PowerPoint solo las que no lo tienen ni están marcadas como decorativas) | — |
| PDF escaneado | `accesibilidad_visual` | — | sin capa de texto seleccionable |
| Letra chica en el cuerpo (Issue #79, solo archivos) | `accesibilidad_visual` | — | tamaño predominante del texto < 9 pt |
| Pasaje largo en letra chica (Issue #79, solo archivos) | `accesibilidad_visual` | párrafo o bloque con 20+ palabras en < 8 pt (notas, epígrafes) | — |

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

- **Tamaño del cuerpo**: el tamaño predominante ponderado por caracteres, entre los fragmentos con tamaño conocido. Si no se pudo medir ninguno, se usa `structure.body_font_size`.
  - **PDF**: tamaño de cada span de PyMuPDF.
  - **Word**: tamaño del run; si no lo define, el del estilo de carácter, el del estilo de párrafo (y sus estilos base) y por último `docDefaults` (Word usa 10 pt si no está). Incluye celdas de tabla.
  - **PowerPoint**: tamaño del run o del párrafo, multiplicado por la reducción automática del cuadro (`normAutofit fontScale`). Incluye grupos y tablas; se saltean las diapositivas ocultas.
- **Pasaje**: un bloque de texto del PDF o un párrafo de Word/PowerPoint. Cuenta como "letra chica" si tiene **20 palabras o más** en menos de **8 pt**: así no se marcan números de página, fuentes ni pies de foto cortos.
- Si todo el cuerpo ya está en letra chica, no se lista además cada pasaje: alcanza con la barrera del cuerpo.
- Las barreras de esta regla no tienen `anchor`: una barrera de la IA sobre el mismo texto (por ejemplo, de comprensión) habla de otro problema y no debe ocultarla.
- En los pasajes, `original_text` es el comienzo del pasaje, y la página o diapositiva va en `issue` (Word no informa páginas). En el cuerpo, `original_text` es un resumen entre corchetes y `fragment_found` es `null`, como en el resto de las barreras de documento completo.
- Umbrales: `MIN_BODY_FONT_PT` (9) en `legibility_rules.py`; `SMALL_PASSAGE_PT` (8) y `MIN_SMALL_PASSAGE_WORDS` (20) en `legibility_extractor.py`.

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
- **Letra chica en PDF**: un PDF que se generó achicando páginas (por ejemplo, dos por hoja) puede tener letra legible al imprimir aunque los puntos digan otra cosa: la regla mide el tamaño declarado en el archivo.

## Próximos pasos (producto final)

1. Si la IA no responde (429/503), devolver el diagnóstico solo con reglas (`degraded: true`) en lugar de un error.
2. Posición exacta de cada barrera de reglas (`char_start`/`char_end`) para resaltarla en el Frontend y adaptarla en las Semanas 5 y 6.
3. Índice de legibilidad en español (Fernández-Huerta / INFLESZ).
4. Más reglas de texto: siglas sin desarrollar, pasajes largos en MAYÚSCULAS, enumeraciones en línea (`a) … b) …`) y material extenso sin títulos.
5. Reglas del PDF: falta de etiquetas de estructura o idioma, bajo contraste y tipografía poco legible (Issue #79, partes 2 y 3). La letra chica ya está implementada (Issue #79, parte 1).
6. Umbrales configurables por nivel educativo (secundario o superior).
