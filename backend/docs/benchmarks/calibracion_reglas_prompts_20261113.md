# Calibración de prompts y motor de reglas (Issue #43)

- Fecha (UTC): 2026-11-13
- Script ejecutado: `python -m scripts.benchmark_analysis --rules-only`
- Fixtures evaluados: `backend/tests/fixtures/analysis/` (`01` a `08`, incorporando `06_guia_tp_laboratorio_colores`, `07_evaluacion_historia_accesible` y `08_texto_denso_sin_subdivisiones`).

## Hallazgos detectados antes de calibrar

1. **Falso negativo en consignas de laboratorio / con pronombres enclíticos (`rules_service.py`)**:
   - En `06_guia_tp_laboratorio_colores`, la consigna `"Prepará los cinco tubos de ensayo, rotulalos del 1 al 5, agregá cinco gotas del indicador en cada tubo, agitá suavemente durante diez segundos y registrá el cambio observado..."` no activaba `consignas_multiaccion` porque faltaban verbos de laboratorio (`agregá`, `agitá`, `registrá`, `rotulá`, `observá`, `elegí`, `medí`, etc.) y no se reconocían pronombres enclíticos (`rotulalos`, `explicala`).
2. **Falso positivo con `"una"` al ampliar `_ACTION_VERBS`**:
   - La palabra `"una"` (presente en `_ACTION_VERBS` como subjuntivo de `unir`) provocaba un falso positivo en `01_consigna_simple` (`"4. Elegí una etapa y explicala..."` → 3 acciones por contar `"una"`).
3. **Consistencia y falsos positivos en `SYSTEM_PROMPT` (`accessibility_service.py`)**:
   - Se reforzó el criterio para no marcar menciones literales/descriptivas de color (`"bandera verde y blanca"`, `"hojas verdes"`) y priorizar de forma estable las consignas multi-acción y oraciones más extensas con `suggested_rewrite` conciso (1 a 3 oraciones).

## Comparativa antes vs después (`--rules-only`)

| Fixture | Score antes | Score después | Cambio / Efecto |
|---|---:|---:|---|
| `01_consigna_simple` | 100 | 100 | Sin falsos positivos tras quitar `"una"` de `_ACTION_VERBS` |
| `02_consigna_multiaccion` | 50 | 50 | Estable (`oraciones_extensas -30, consignas_multiaccion -5, legibilidad_baja -15`) |
| `03_texto_tecnico_quimica` | 100 | 100 | Sin falsos positivos en terminología técnica |
| `04_material_500_palabras` | 76 | 76 | Estable |
| `05_material_2000_palabras` | 88 | 88 | Estable |
| `06_guia_tp_laboratorio_colores` | 70 | 65 | Ahora detecta `consignas_multiaccion -5` en la consigna de 5 pasos |
| `07_evaluacion_historia_accesible` | 100 | 100 | Control positivo: menciones de color descriptivas no generan penalización |
| `08_texto_denso_sin_subdivisiones` | 44 | 44 | Detecta oraciones extensas, párrafo extenso, multi-acción y legibilidad baja |
