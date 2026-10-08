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
| PDF sin títulos estructurados | `estructura` | — | doc ≥ 150 palabras sin H1/H2 |
| Salto de jerarquía en títulos | `estructura` | salto de nivel (ej. H1 a H3) | — |
| Sección extensa sin subdivisiones | `estructura` | más de 300 palabras bajo un título | — |
| Referencias exclusivamente visuales (Tarea #25) | `accesibilidad_visual` | referencias a posición espacial ("a la derecha") o color sin texto alternativo (WCAG 1.3.3) | — |
| Imágenes | `accesibilidad_visual` | hay imágenes (no se puede verificar su texto alternativo) | — |
| PDF escaneado | `accesibilidad_visual` | — | sin capa de texto seleccionable |

- Las palabras se cuentan con el mismo criterio que `DocumentService` (`\b\w+\b`).
- Se listan como máximo **3 barreras por regla** (las más extensas/relevantes). El total aparece en el comentario de la dimensión.
- Las barreras de reglas tienen `source="rules"`, `fragment_found=true` (la cita sale del texto, no puede ser una alucinación) y `suggested_rewrite=null`.
- En los párrafos y secciones extensas, `original_text` trae el fragmento inicial seguido de `…`.
- Los umbrales y pesos son constantes al comienzo de `rules_service.py`.

### Cómo se separan párrafos y oraciones

- **Párrafo**: cada renglón no vacío. Los títulos y los ítems de lista cuentan como bloques propios, porque ya son una división del texto.
- **PDF**: `DocumentService` extrae el texto por **bloques** de PyMuPDF. Une los renglones visuales de cada bloque (juntando las palabras cortadas con guion) y deja cada ítem de lista en su propio renglón. Sin esto, cada página contaría como un único párrafo y las oraciones quedarían cortadas en cada renglón.
- **Oración**: termina en `.`, `!`, `?` o `…` seguido de espacio. Se protegen:
  - abreviaturas (`pág.`, `ej.`, `Dr.`, `aprox.`…);
  - iniciales (`J. Pérez`);
  - decimales (`3.5`);
  - marcadores de lista (`1. Leé…`);
  - puntos seguidos de minúscula (`etc. y…`).

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
  imagenes_sin_verificar   10   (solo si no es escaneado)

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

## Próximos pasos (producto final)

1. Si la IA no responde (429/503), devolver el diagnóstico solo con reglas (`degraded: true`) en lugar de un error.
2. Posición exacta de cada barrera de reglas (`char_start`/`char_end`) para resaltarla en el Frontend y adaptarla en las Semanas 5 y 6.
3. Índice de legibilidad en español (Fernández-Huerta / INFLESZ).
4. Más reglas de texto: siglas sin desarrollar, pasajes largos en MAYÚSCULAS, enumeraciones en línea (`a) … b) …`) y material extenso sin títulos.
5. Reglas del PDF: letra de menos de 9 pt, falta de etiquetas de estructura o idioma, bajo contraste.
6. Umbrales configurables por nivel educativo (secundario o superior).
