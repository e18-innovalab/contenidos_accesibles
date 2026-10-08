# Riesgos y limitaciones técnicas - Semana 1 · Dimensión IA (pendiente revisar con límite nuevo)

> Sección del Desarrollador 2 (motor de análisis de accesibilidad con Gemini).
> Complementa la sección 2 de `docs/riesgos_y_limitaciones_semana1.md`.
>
> **Estado: pendiente revisar con límite nuevo.** Los datos de esta sección salen de
> un benchmark incompleto (14 de 30 llamadas exitosas), hecho con keys de la misma
> cuenta de Google, que comparten la cuota diaria de 20 requests. Algunas conclusiones
> difieren de las estimaciones de la sección 2 del documento general, sobre todo en
> latencia y cuota. Se van a revisar y unificar cuando se repita el benchmark con las
> keys nuevas.

## Contexto de las pruebas

- **Modelo:** `gemini-2.5-flash`, capa gratuita, con Salidas Estructuradas (`response_schema`).
- **Endpoint probado:** `POST /api/v1/analysis/sample`.
- **Textos de muestra** (en `tests/fixtures/analysis/`):
  - consigna clara de control (88 palabras);
  - consigna con múltiples acciones (153);
  - texto técnico de química (230);
  - material de Geografía (511);
  - cuadernillo de Biología (2025).
- **Benchmark:** 3 corridas por texto, con *thinking* por defecto y con *thinking* desactivado (`thinking_budget=0`). En total, 30 llamadas el 2026-09-23.
- **Resultados completos:** `docs/benchmarks/analysis_summary_20260923_1957.md`.
- **Llamadas exitosas: 14 de 30.** Las otras 16 fallaron por errores de Google (503 y 429), que son justamente dos de los riesgos de este informe. Falta medir el modo *thinking* por defecto en los textos de 500 y 2000 palabras. Se completará cuando se reinicie la cuota.

## Tabla de riesgos

| Dimensión | Riesgo / Limitación detectada | Mitigación propuesta para los siguientes Sprints |
|---|---|---|
| IA | **Latencia alta y variable.** Con *thinking* por defecto, entre 8 y 24 s incluso en textos de menos de 160 palabras. Sin *thinking*: 2 a 3 s en textos claros y 12 a 18 s cuando hay muchas barreras. La latencia depende más de la cantidad de barreras y reescrituras que genera el modelo que del largo del texto: el de 2025 palabras tardó 6,2 s. La estimación inicial de 3 a 6 s no se cumple en todos los casos. | Implementado: `thinking_budget=0` por defecto (4 a 5 veces más rápido) y un tope de 10 barreras por análisis. Pendiente: estados de carga claros en el Frontend, considerar *streaming* y generar las reescrituras solo cuando el docente las pida. |
| IA | **Saturación del modelo (503 "high demand").** 9 de 30 llamadas (30 %) fallaron por sobrecarga de los servidores de Google. | Implementado: reintentos automáticos con espera creciente (2 s y 4 s). Si el error persiste, el backend responde un 503 claro, sin error genérico. Pendiente: evaluar un modelo de respaldo configurable (por ejemplo, `gemini-2.5-flash-lite`). |
| IA | **Cuota diaria muy baja: 20 requests por día, por proyecto y por modelo.** Cada análisis consume 1 request, así que el MVP soporta unos 20 análisis diarios por proyecto de Google. | La rotación de keys solo suma cuota si las keys vienen de **proyectos distintos** de Google. Hoy todas las keys son de la misma cuenta, así que la rotación no amplía la capacidad real. Hay que migrar a keys de proyectos separados y evaluar la capa paga antes del piloto con docentes. |
| IA | **El contador de consumo del panel `/admin` subestimaba el uso real.** El panel mostraba 15 de 20 cuando Google ya respondía 429. Las requests fallidas (503) cuentan para Google pero no se registraban, y un 429 real no hacía rotar de key. | Implementado: las requests fallidas se registran, y un 429 de Google deja la key en espera (hasta medianoche del Pacífico si es la cuota diaria, o según el `retryDelay` si es por minuto) y rota a la siguiente. Pendiente: el panel reinicia su contador a las 00:00 UTC, mientras que Google lo hace a medianoche del Pacífico (07:00 u 08:00 UTC). Hay que alinearlos. |
| IA | **Variabilidad entre respuestas.** El puntaje fue estable (desvío entre 0 y 1,7 puntos entre corridas) y el estado de cada dimensión se mantuvo casi siempre. En cambio, **los fragmentos señalados como barrera varían bastante**: la coincidencia entre corridas fue de 0,33 a 0,5 (Jaccard). El mismo material puede mostrar barreras distintas si se analiza dos veces. | `temperature=0.2`. Presentar el puntaje como **orientativo** y las barreras como sugerencias, no como una lista exhaustiva. Pendiente: evaluar si conviene ofrecer la opción de "volver a analizar" o fijar una semilla. |
| IA | **Falsos positivos en textos técnicos.** El riesgo resultó bajo en esta muestra: el texto de química obtuvo 95 puntos y 0 barreras en todas las corridas, y la consigna de control entre 95 y 98. La muestra es chica y cubre una sola disciplina técnica. | Implementado: el prompt indica que la terminología propia de la disciplina no es barrera, salvo que no esté definida. Pendiente: ampliar los textos de prueba con Matemática, Física y Lengua. |
| IA | **Alucinación de fragmentos.** El modelo podría citar un texto que no está en el material. En las 14 respuestas exitosas, el 100 % de los fragmentos se verificó textualmente. | Implementado: cada barrera trae `fragment_found`, que indica si el fragmento aparece tal cual en el material, y si hay fragmentos no verificados se agrega una advertencia visible para el docente. |
| IA | **Gemini no ve las imágenes.** El análisis es solo de texto, por lo que la dimensión `accesibilidad_visual` se basa en reglas: cantidad de imágenes y PDF escaneado. | Hoy se avisa al docente que revise el texto alternativo. *Future Scope:* análisis multimodal de las imágenes con Gemini. |
| IA | **Respuesta cortada o inválida.** Si el JSON supera `max_output_tokens` (8192), la respuesta queda incompleta. No ocurrió en las pruebas: la salida más larga fue de unos 2.200 tokens. | Implementado: tope de 10 barreras, y si la respuesta no es válida el backend devuelve un 502 claro. |
| IA | **Privacidad de los materiales.** En la capa gratuita, Google puede usar el contenido enviado para mejorar sus productos. Los materiales podrían incluir datos de estudiantes. | Avisar al docente que no incluya datos personales. Evaluar la capa paga, donde los datos no se usan para entrenamiento, antes de trabajar con materiales reales. Los archivos no se guardan en el backend (se procesan en memoria). |

## Mediciones principales

| Texto | Palabras | Latencia sin *thinking* (s) | Latencia con *thinking* por defecto (s) | Puntaje | Barreras |
|---|---:|---:|---:|---:|---:|
| Consigna clara (control) | 88 | 2,2 a 2,4 | 8,0 a 17,9 | 95 a 98 | 0 a 1 |
| Consigna con múltiples acciones | 153 | 12,6 a 17,9 | 23,5 | 45 a 55 | 1 a 4 |
| Texto técnico (química) | 230 | 2,6 | 10,9 a 13,2 | 95 | 0 |
| Material de Geografía | 511 | 8,7 a 50,5* | sin datos | 65 | 4 a 5 |
| Cuadernillo de Biología | 2025 | 6,2 | sin datos | 85 | 2 |

\* Valor atípico, registrado durante el período de saturación del modelo.

**Tokens de *thinking*:** entre 1.600 y 3.700 por llamada en el modo por defecto. En la capa gratuita también cuentan para el límite de tokens por minuto.

## Conclusión

El análisis con Gemini y Salidas Estructuradas **es técnicamente viable**:
- las respuestas siempre respetaron el esquema;
- los diagnósticos son coherentes y estables en puntaje;
- no se detectaron fragmentos inventados.

Las limitaciones principales **no son de calidad sino de infraestructura**: la cuota de la capa gratuita, la disponibilidad del modelo y la latencia. Para un piloto con docentes reales hacen falta dos cosas: keys de proyectos separados o la capa paga, y un Frontend preparado para esperas de 5 a 20 segundos.
