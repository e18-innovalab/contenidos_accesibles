# 📑 Riesgos y Limitaciones Técnicas - Sprint 1 (Semana 1)
> **Proyecto:** Asistente de Accesibilidad para Contenidos Educativos  
> **Área:** Backend & Procesamiento de Materiales

---

## 1. Procesamiento y Extracción de Documentos (PDF / Texto)

### 🔴 Riesgo 1: PDFs Escaneados o Fotocopiados (Sin capa de texto digital)
* **Descripción:** Muchos docentes utilizan fotocopias digitalizadas de libros o cuadernillos guardados como PDF. Estos archivos contienen únicamente imágenes de páginas sin texto seleccionable.
* **Impacto:** Las herramientas estándar de extracción de texto (como PyMuPDF o pypdf) extraen 0 palabras, impidiendo que el motor de accesibilidad analice el contenido.
* **Mitigación implementada (Semana 1):** 
  - Se incorporó una heurística en document_service.py que detecta si el documento tiene imágenes o páginas pero menos de 25 palabras legibles, marcando la bandera is_scanned_pdf: True y emitiendo una advertencia explícita.
* **Propuesta para Future Scope:** Evaluar un motor OCR ligero (ej. Tesseract OCR o el modelo de visión de Gemini) para digitalizar el texto de las imágenes antes del análisis.

### 🟡 Riesgo 2: Consumo de Memoria por Archivos Extensos (Denegación de Servicio / OOM)
* **Descripción:** Si un usuario sube un PDF de cientos de megabytes con imágenes de alta resolución, la memoria RAM del servidor puede saturarse al abrir el stream.
* **Mitigación implementada (Semana 1):**
  - Validación de tamaño en streaming mediante lectura en chunks con un límite estricto de **10 MB por archivo** (HTTP 413 Payload Too Large).
  - Procesamiento **100% en memoria** liberando los punteros mediante doc.close() en bloques inally (cumple con las políticas de privacidad docente y no persiste datos en disco).

### 🟡 Riesgo 3: PDFs Cifrados o Protegidos con Contraseña
* **Descripción:** Documentos institucionales protegidos contra lectura o edición.
* **Mitigación implementada (Semana 1):**
  - Detección temprana mediante doc.is_encrypted, arrojando un error controlado HTTP 400 que informa claramente al docente que debe desproteger el archivo.

---

## 2. Análisis con Inteligencia Artificial (Google Gemini)

### 🟡 Riesgo 4: Latencia en Textos Extensos
* **Descripción:** El tiempo de respuesta de los modelos de lenguaje (LLM) escala con la cantidad de tokens analizados (puede oscilar entre 2 y 6 segundos).
* **Mitigación implementada:**
  - Comunicación asíncrona no bloqueante (client.aio) para no congelar el servidor mientras se espera la respuesta.
  - Se coordinará con Frontend la implementación de loaders/skeletons con mensajes pedagógicos durante la espera.

### 🟢 Riesgo 5: Saturación de Cuotas de la Capa Gratuita (RPM / TPM)
* **Descripción:** Límites de 5 a 15 peticiones por minuto en Gemini Free Tier.
* **Mitigación implementada:**
  - Panel administrativo en /admin con **rotación automática de hasta 3 API keys** y persistencia en SQLite con cifrado Fernet.

---

## 3. Matriz Resumen de Viabilidad Técnica

| Dimensión | Viabilidad Técnica | Estado actual en MVP |
| :--- | :---: | :--- |
| **Ingesta de Texto Plano** | Alta | ✅ Validado y operativo (/documents/process-text). |
| **Extracción de PDF digital** | Alta | ✅ Validado y operativo con PyMuPDF (/documents/upload-pdf). |
| **Detección de Imágenes en PDF** | Alta | ✅ Validado (conteo y detección para textos alternativos). |
| **PDFs Escaneados (OCR)** | Media (Complejidad extra) | ⚠️ Identificado con advertencia al usuario. Reservado para Future Scope. |
| **Conexión Asíncrona con Gemini** | Alta | ✅ Validado con gemini-2.5-flash y rotación de keys. |
