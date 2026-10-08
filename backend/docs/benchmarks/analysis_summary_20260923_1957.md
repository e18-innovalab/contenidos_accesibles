# Benchmark del motor de accesibilidad - Semana 1

- Fecha (UTC): 2026-09-23 19:57
- Modelo: `gemini-2.5-flash`
- Modo `default`: thinking dinámico de Gemini 2.5 Flash. Modo `0`: thinking desactivado.
- `Jaccard frag.`: similitud promedio (0 a 1) entre corridas de los fragmentos señalados como barrera.

## Latencia y tokens

| Texto | Palabras | Thinking | OK/Err | Latencia media (s) | Mín-Máx (s) | Tokens entrada | Tokens salida | Tokens thinking |
|---|---:|---|---|---:|---|---:|---:|---:|
| 01_consigna_simple | 88 | 0 | 2/1 | 2.3 | 2.2-2.4 | 851 | 313 | 0 |
| 01_consigna_simple | 88 | default | 3/0 | 12.6 | 8.0-17.9 | 851 | 417.7 | 1739 |
| 02_consigna_multiaccion | 153 | 0 | 2/1 | 15.2 | 12.6-17.9 | 916 | 2165 | 0 |
| 02_consigna_multiaccion | 153 | default | 1/2 | 23.5 | 23.5-23.5 | 916 | 936 | 3761 |
| 03_texto_tecnico_quimica | 230 | 0 | 1/2 | 2.6 | 2.6-2.6 | 1085 | 316 | 0 |
| 03_texto_tecnico_quimica | 230 | default | 2/1 | 12.0 | 10.9-13.2 | 1085 | 411.5 | 1620.5 |
| 04_material_500_palabras | 511 | 0 | 2/1 | 29.6 | 8.7-50.5 | 1410 | 1511.5 | 0 |
| 04_material_500_palabras | 511 | default | 0/3 | None | None-None | None | None | None |
| 05_material_2000_palabras | 2025 | 0 | 1/2 | 6.2 | 6.2-6.2 | 3577 | 1116 | 0 |
| 05_material_2000_palabras | 2025 | default | 0/3 | None | None-None | None | None | None |

## Variabilidad

| Texto | Thinking | Score medio | Rango | Desvío | Barreras (rango) | Jaccard frag. | Frag. no verificados | Comprensión | Estructura |
|---|---|---:|---|---:|---|---:|---:|---|---|
| 01_consigna_simple | 0 | 95 | 95-95 | 0.0 | 0-0 | 1.0 | 0 | correcta | correcta |
| 01_consigna_simple | default | 96 | 95-98 | 1.7 | 0-1 | 0.33 | 0 | correcta | correcta |
| 02_consigna_multiaccion | 0 | 55 | 55-55 | 0.0 | 3-4 | 0.33 | 0 | barrera_detectada/para_revisar | barrera_detectada |
| 02_consigna_multiaccion | default | 45 | 45-45 | None | 1-1 | None | 0 | barrera_detectada | barrera_detectada |
| 03_texto_tecnico_quimica | 0 | 95 | 95-95 | None | 0-0 | None | 0 | correcta | correcta |
| 03_texto_tecnico_quimica | default | 95 | 95-95 | 0.0 | 0-0 | 1.0 | 0 | correcta | correcta |
| 04_material_500_palabras | 0 | 65 | 65-65 | 0.0 | 4-5 | 0.5 | 0 | para_revisar | barrera_detectada |
| 04_material_500_palabras | default | None | - | None | - | None | 0 | - | - |
| 05_material_2000_palabras | 0 | 85 | 85-85 | None | 2-2 | None | 0 | para_revisar | correcta |
| 05_material_2000_palabras | default | None | - | None | - | None | 0 | - | - |
