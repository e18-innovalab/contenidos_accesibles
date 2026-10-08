"use strict";

// ---------------------------------------------------------------------------
// Estado y configuración
// ---------------------------------------------------------------------------

const API_PREFIX = "/api/v1";
const MAX_PDF_BYTES = 10 * 1024 * 1024;
const MIN_TEXT_CHARS = 10;
const MAX_TEXT_CHARS = 20000;
const REQUEST_TIMEOUT_MS = 180000; // la IA real puede tardar; Railway corta antes si algo se cuelga
const MAX_LOG_ENTRIES = 30;

const ADAPTATION_TYPES = {
    lenguaje_claro: "Lenguaje claro",
    consigna_en_pasos: "Consigna en pasos",
    reorganizar: "Reorganizar en bloques",
    mejorar_estructura: "Mejorar estructura",
};

const SAMPLE_TEXT = `Unidad 3: El ciclo del agua

El ciclo del agua, también conocido como ciclo hidrológico, es el proceso de circulación del agua entre los distintos compartimentos de la hidrosfera, en el cual se producen transformaciones de estado físico que dependen de la temperatura y la presión, y que permiten que el agua pase de la superficie terrestre a la atmósfera mediante la evaporación y la transpiración de las plantas, para luego condensarse formando nubes y regresar a la superficie en forma de precipitación.

Actividad 1: Leé el texto de la página 8, subrayá las ideas principales, armá un cuadro comparativo entre evaporación y condensación, respondé las preguntas del final y entregá todo en una hoja aparte antes del viernes.

Observá la imagen de la derecha y completá el esquema.`;

const state = {
    apiBase: "",
    analysis: null, // último AccessibilityAnalysisResponse
    proposals: [],
};

const $ = (id) => document.getElementById(id);

function storageGet(key) {
    try { return localStorage.getItem(key); } catch { return null; }
}

function storageSet(key, value) {
    try { localStorage.setItem(key, value); } catch { /* modo privado o storage bloqueado */ }
}

// ---------------------------------------------------------------------------
// Helpers de DOM (todo el contenido dinámico va por textContent: nada de innerHTML)
// ---------------------------------------------------------------------------

function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
        if (value === undefined || value === null || value === false) continue;
        if (key === "class") node.className = value;
        else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
        else if (key in node && key !== "list") node[key] = value;
        else node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
        if (child === null || child === undefined || child === false) continue;
        node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
}

// Reemplaza el contenido de un nodo ignorando null/false (replaceChildren los escribiría como texto).
function fill(node, ...children) {
    node.replaceChildren(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
}

function badge(text, variant) {
    return el("span", { class: `badge b-${variant || text}` }, text);
}

function kv(pairs) {
    const dl = el("dl", { class: "kv" });
    for (const [key, value] of pairs) {
        if (value === undefined) continue;
        dl.append(el("dt", {}, key), el("dd", {}, value === null ? "—" : String(value)));
    }
    return dl;
}

function rawJson(data, label = "Ver JSON completo") {
    return el("details", {}, el("summary", {}, label), el("pre", {}, JSON.stringify(data, null, 2)));
}

function errorBox(message) {
    return el("div", { class: "error" }, message);
}

function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : `${d.toLocaleString()} (${iso})`;
}

function fmtBytes(n) {
    return n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(2)} MB` : `${Math.ceil(n / 1024)} KB`;
}

// ---------------------------------------------------------------------------
// Cliente HTTP con registro de requests
// ---------------------------------------------------------------------------

// Validación del formulario: se muestra al usuario, no es un fallo de la página.
class InputError extends Error {}

class ApiError extends Error {
    constructor(message, status, data) {
        super(message);
        this.status = status;
        this.data = data;
    }
}

function formatDetail(data, status) {
    const detail = data && data.detail;
    if (typeof detail === "string") return `${status}: ${detail}`;
    if (Array.isArray(detail)) {
        // 422 de FastAPI: lista de {loc, msg}
        const lines = detail.map((d) => `• ${(d.loc || []).join(" → ")}: ${d.msg}`);
        return `${status}: datos inválidos\n${lines.join("\n")}`;
    }
    if (typeof data === "string" && data) return `${status}: ${data.slice(0, 500)}`;
    return `${status}: error sin detalle`;
}

function buildUrl(path, query = {}) {
    let url;
    try {
        url = new URL(state.apiBase + API_PREFIX + path);
    } catch {
        throw new ApiError(`URL del backend inválida: "${state.apiBase}". Ejemplo: https://mi-backend.up.railway.app`, 0, null);
    }
    for (const [key, value] of Object.entries(query)) {
        if (value !== undefined && value !== null) url.searchParams.set(key, value);
    }
    return url.toString();
}

function shellQuote(s) {
    return `'${String(s).replace(/'/g, `'\\''`)}'`;
}

function toCurl(method, url, body) {
    const parts = [`curl -X ${method} ${shellQuote(url)}`];
    if (body && body.kind === "json") {
        parts.push(`-H 'Content-Type: application/json'`, `-d ${shellQuote(JSON.stringify(body.value))}`);
    } else if (body && body.kind === "file") {
        parts.push(`-F ${shellQuote(`file=@${body.value.name};type=application/pdf`)}`);
    }
    return parts.join(" \\\n  ");
}

/**
 * Llama a la API y registra la llamada. `body` es {kind: "json", value} o {kind: "file", value: File}.
 * Lanza ApiError con un mensaje legible si la respuesta no es 2xx o no hay conexión.
 */
async function api(method, path, { query, body, busyText } = {}) {
    if (!state.apiBase) throw new ApiError("Configurá la URL del backend en el paso 0.", 0, null);

    const url = buildUrl(path, query);
    const init = { method, headers: { Accept: "application/json" } };
    if (body && body.kind === "json") {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(body.value);
    } else if (body && body.kind === "file") {
        const form = new FormData();
        form.append("file", body.value, body.value.name);
        init.body = form;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    init.signal = controller.signal;

    setBusy(true, busyText);
    const started = performance.now();
    let status = 0;
    let data = null;
    let failure = null;
    try {
        const res = await fetch(url, init);
        status = res.status;
        const text = await res.text();
        try { data = text ? JSON.parse(text) : null; } catch { data = text; }
        if (!res.ok) failure = new ApiError(formatDetail(data, status), status, data);
    } catch (err) {
        failure = err.name === "AbortError"
            ? new ApiError(`Sin respuesta tras ${REQUEST_TIMEOUT_MS / 1000} s (timeout del navegador).`, 0, null)
            : new ApiError(
                "No se pudo conectar con el backend. Revisá la URL, que el servicio esté arriba y que el " +
                "origen de esta web esté permitido en CORS (TEST_WEB_URL o BACKEND_CORS_ORIGINS en el backend).",
                0, null,
            );
    } finally {
        clearTimeout(timer);
        setBusy(false);
    }

    addLogEntry({
        method, url, status, data, body,
        ms: Math.round(performance.now() - started),
        error: failure ? failure.message : null,
    });
    if (failure) throw failure;
    return data;
}

function setBusy(on, text) {
    $("busy").hidden = !on;
    $("busy-text").textContent = text || "Procesando…";
    for (const button of document.querySelectorAll("button")) button.disabled = on;
}

function addLogEntry({ method, url, status, data, body, ms, error }) {
    const container = $("log-entries");
    if (!container.querySelector("details")) container.replaceChildren();

    const path = url.replace(state.apiBase, "");
    const statusBadge = badge(status ? String(status) : "sin respuesta", status >= 200 && status < 300 ? "ok" : "error");
    let requestBody = null;
    if (body && body.kind === "json") requestBody = JSON.stringify(body.value, null, 2);
    if (body && body.kind === "file") requestBody = `multipart/form-data → file: ${body.value.name} (${fmtBytes(body.value.size)})`;

    const entry = el("details", { class: "card" },
        el("summary", {}, statusBadge, `${method} ${path} · ${ms} ms · ${new Date().toLocaleTimeString()}`),
        error ? errorBox(error) : null,
        requestBody ? el("div", {}, el("h3", {}, "Request"), el("pre", {}, requestBody)) : null,
        el("h3", {}, "Response"),
        el("pre", {}, typeof data === "string" ? data : JSON.stringify(data, null, 2)),
        el("h3", {}, "curl"),
        el("pre", {}, toCurl(method, url, body)),
    );
    container.prepend(entry);
    while (container.children.length > MAX_LOG_ENTRIES) container.lastChild.remove();
}

// Muestra el error de una acción en el contenedor indicado (sin borrar lo que ya había).
async function run(target, action) {
    target.querySelectorAll(":scope > .error").forEach((n) => n.remove());
    try {
        await action();
    } catch (err) {
        const box = errorBox(err.message || String(err));
        const title = target.querySelector(":scope > h2");
        if (title) title.after(box);
        else target.prepend(box);
        if (!(err instanceof ApiError || err instanceof InputError)) console.error(err);
    }
}

// ---------------------------------------------------------------------------
// 0. Backend
// ---------------------------------------------------------------------------

function normalizeApiBase(raw) {
    let value = (raw || "").trim().replace(/\/+$/, "");
    if (value.endsWith(API_PREFIX)) value = value.slice(0, -API_PREFIX.length);
    return value;
}

function setApiBase(raw) {
    state.apiBase = normalizeApiBase(raw);
    $("api-url").value = state.apiBase;
    storageSet("innovalab.apiBase", state.apiBase);
}

function isMock() {
    return $("mock").checked;
}

async function checkHealth() {
    const out = $("health-status");
    out.className = "muted";
    out.textContent = "";
    try {
        const data = await api("GET", "/health", { busyText: "Probando conexión (si el backend estaba dormido puede tardar)…" });
        out.className = "ok";
        out.textContent = `Conectado · ${JSON.stringify(data)}`;
    } catch (err) {
        out.className = "error";
        out.textContent = err.message;
    }
}

// ---------------------------------------------------------------------------
// 1. Material
// ---------------------------------------------------------------------------

function switchTab(name) {
    for (const tab of document.querySelectorAll(".tab")) tab.classList.toggle("active", tab.dataset.tab === name);
    $("tab-text").hidden = name !== "text";
    $("tab-pdf").hidden = name !== "pdf";
}

function updateTextCount() {
    const n = $("text-input").value.length;
    const out = $("text-count");
    out.textContent = `${n.toLocaleString()} caracteres`;
    out.className = n > 0 && (n < MIN_TEXT_CHARS || n > MAX_TEXT_CHARS) ? "error" : "muted";
}

function readText() {
    const text = $("text-input").value;
    if (text.trim().length < MIN_TEXT_CHARS) throw new InputError(`El texto debe tener al menos ${MIN_TEXT_CHARS} caracteres.`);
    if (text.length > MAX_TEXT_CHARS) throw new InputError(`El texto supera el máximo de ${MAX_TEXT_CHARS.toLocaleString()} caracteres.`);
    return text;
}

function readPdf() {
    const file = $("pdf-input").files[0];
    if (!file) throw new InputError("Elegí un archivo PDF.");
    if (!file.name.toLowerCase().endsWith(".pdf")) throw new InputError("El archivo debe tener extensión .pdf.");
    if (file.size > MAX_PDF_BYTES) throw new InputError(`El archivo pesa ${fmtBytes(file.size)}; el máximo es 10 MB.`);
    return file;
}

function updatePdfInfo() {
    const file = $("pdf-input").files[0];
    $("pdf-info").textContent = file ? `${file.name} · ${fmtBytes(file.size)}` : "";
}

function renderExtraction(doc) {
    const box = $("extraction");
    box.hidden = false;
    const s = doc.structure || {};
    fill(box,
        el("h3", {}, "Extracción (sin IA)"),
        kv([
            ["Origen", doc.source_type],
            ["Archivo", doc.filename],
            ["Páginas", doc.page_count],
            ["Palabras", doc.word_count],
            ["Caracteres", doc.character_count],
            ["Imágenes", doc.image_count],
            ["PDF escaneado", doc.is_scanned_pdf ? "sí" : "no"],
            ["Títulos detectados", (s.headings || []).length],
            ["Niveles de jerarquía", s.hierarchy_levels],
            ["Ítems de lista", s.list_items_count],
            ["Se trunca para la IA", doc.is_truncated ? "sí" : "no"],
        ]),
        doc.warnings && doc.warnings.length
            ? el("div", {}, el("h3", {}, "Advertencias"), el("ul", {}, doc.warnings.map((w) => el("li", {}, w))))
            : null,
        (s.headings || []).length
            ? el("details", {}, el("summary", {}, "Títulos detectados"),
                el("ul", {}, s.headings.map((h) => el("li", {}, `H${h.level} · pág. ${h.page_number} · ${h.text}`))))
            : null,
        el("details", {}, el("summary", {}, "Texto extraído"), el("pre", {}, doc.raw_text || "")),
        rawJson(doc),
    );
}

async function processText() {
    const text = readText();
    renderExtraction(await api("POST", "/documents/process-text", { body: { kind: "json", value: { text } } }));
}

async function processPdf() {
    const file = readPdf();
    renderExtraction(await api("POST", "/documents/upload-pdf", { body: { kind: "file", value: file }, busyText: "Extrayendo PDF…" }));
}

const ANALYSIS_BUSY = () => isMock()
    ? "Analizando (mock)…"
    : "Analizando con IA real (puede tardar hasta 1 minuto)…";

async function analyzeText() {
    const text = readText();
    const data = await api("POST", "/analysis/sample", {
        query: { mock: isMock() },
        body: { kind: "json", value: { text } },
        busyText: ANALYSIS_BUSY(),
    });
    await showAnalysis(data);
}

async function analyzePdf() {
    const file = readPdf();
    const data = await api("POST", "/analysis/pdf", {
        query: { mock: isMock() },
        body: { kind: "file", value: file },
        busyText: ANALYSIS_BUSY(),
    });
    await showAnalysis(data);
}

// ---------------------------------------------------------------------------
// 2. Diagnóstico
// ---------------------------------------------------------------------------

async function loadAnalysis() {
    const id = $("analysis-id-input").value.trim();
    if (!id) throw new InputError("Ingresá un analysis_id.");
    await showAnalysis(await api("GET", `/analysis/${encodeURIComponent(id)}`));
}

async function showAnalysis(data) {
    state.analysis = data;
    state.proposals = [];
    if (data.analysis_id) $("analysis-id-input").value = data.analysis_id;
    renderDiagnosis(data);
    renderBarriers(data);
    $("diagnosis").scrollIntoView({ behavior: "smooth", block: "start" });
    if (data.analysis_id) {
        await refreshProposals();
        await refreshDecisions();
    } else {
        $("proposals").replaceChildren(errorBox("El diagnóstico no trae analysis_id: no se pueden pedir adaptaciones."));
    }
}

function renderDiagnosis(d) {
    const m = d.metadata || {};
    const sb = d.score_breakdown;
    const box = $("diagnosis");
    box.parentElement.querySelectorAll(":scope > .error").forEach((n) => n.remove());

    fill(box,
        el("div", { class: "cols" },
            el("div", {},
                el("div", { class: "score" }, `${d.estimated_score} / 100`),
                el("p", {}, d.summary),
            ),
            kv([
                ["analysis_id", d.analysis_id],
                ["Vence", fmtDate(d.expires_at)],
                ["Proveedor", `${m.provider} · ${m.model}`],
                ["Conexión", m.connection],
                ["Latencia", m.latency_ms !== undefined ? `${m.latency_ms} ms` : undefined],
                ["Tokens", m.total_tokens ?? "—"],
                ["Origen", m.source_type + (m.filename ? ` · ${m.filename}` : "")],
                ["Páginas / imágenes", `${m.page_count} / ${m.image_count}`],
                ["Palabras analizadas", `${m.analyzed_word_count}${m.is_truncated ? " (truncado)" : ""}`],
                ["Fragmentos no verificados", m.unverified_fragments],
            ]),
        ),

        el("h3", {}, "Dimensiones"),
        el("table", {},
            el("tr", {}, el("th", {}, "Dimensión"), el("th", {}, "Estado"), el("th", {}, "Comentario")),
            (d.dimensions || []).map((dim) =>
                el("tr", {}, el("td", {}, dim.category), el("td", {}, badge(dim.status)), el("td", {}, dim.comment))),
        ),

        sb ? el("div", {},
            el("h3", {}, "Cálculo del puntaje"),
            kv([
                ["IA", sb.ai_score === null ? "no consultada" : `${sb.ai_score} (peso ${sb.ai_weight})`],
                ["Reglas", `${sb.rules_score} (peso ${sb.rules_weight})`],
                ["Tope", sb.cap === null || sb.cap === undefined ? "—" : `${sb.cap}: ${sb.cap_reason || ""}`],
                ["Final", sb.final_score],
            ]),
            sb.penalties && sb.penalties.length ? el("table", {},
                el("tr", {}, el("th", {}, "Regla"), el("th", {}, "Categoría"), el("th", {}, "Casos"), el("th", {}, "Puntos")),
                sb.penalties.map((p) => el("tr", {},
                    el("td", {}, p.rule), el("td", {}, p.category), el("td", {}, p.count), el("td", {}, `-${p.points}`))),
            ) : null,
        ) : null,

        d.strengths && d.strengths.length
            ? el("div", {}, el("h3", {}, "Fortalezas"), el("ul", {}, d.strengths.map((s) => el("li", {}, s))))
            : null,

        d.warnings && d.warnings.length
            ? el("div", {}, el("h3", {}, "Advertencias"), el("ul", {}, d.warnings.map((w) => el("li", {}, w))))
            : null,

        d.alt_text_proposals && d.alt_text_proposals.length ? el("div", {},
            el("h3", {}, `Texto alternativo propuesto (${d.alt_text_proposals.length})`),
            el("table", {},
                el("tr", {}, el("th", {}, "#"), el("th", {}, "Ubicación"), el("th", {}, "Alt text"), el("th", {}, "Propósito")),
                d.alt_text_proposals.map((a) => el("tr", {},
                    el("td", {}, a.image_index),
                    el("td", {}, a.location_description),
                    el("td", {}, a.suggested_alt_text),
                    el("td", {}, a.pedagogical_purpose || "—"))),
            ),
        ) : null,

        m.rules_metrics ? rawJson(m.rules_metrics, "Métricas del motor de reglas") : null,
        rawJson(d),
    );
}

// ---------------------------------------------------------------------------
// 3. Barreras → propuestas
// ---------------------------------------------------------------------------

function suggestType(barrier) {
    const text = `${barrier.issue} ${barrier.recommendation}`.toLowerCase();
    if (text.includes("consigna") || text.includes("acciones")) return "consigna_en_pasos";
    if (barrier.category === "estructura") return text.includes("párrafo") ? "reorganizar" : "mejorar_estructura";
    return "lenguaje_claro";
}

function renderBarriers(d) {
    const box = $("barriers");
    const barriers = d.barriers || [];
    if (!barriers.length) {
        box.replaceChildren(el("p", { class: "muted" }, "El diagnóstico no detectó barreras."));
        return;
    }
    box.replaceChildren(...barriers.map((b) => barrierCard(b)));
}

function barrierCard(b) {
    const select = el("select", {},
        Object.entries(ADAPTATION_TYPES).map(([value, label]) => el("option", { value }, label)));
    select.value = suggestType(b);
    const fragment = el("textarea", {
        rows: 3,
        placeholder: b.original_text
            ? "Opcional: dejalo vacío para adaptar el fragmento citado por la barrera."
            : "Obligatorio: esta barrera no cita texto. Pegá el fragmento a adaptar (mín. 10 caracteres).",
    });

    const card = el("div", { class: "card" });
    const submit = el("button", {
        type: "button",
        onclick: () => run(card, async () => {
            const payload = { analysis_id: state.analysis.analysis_id, barrier_id: b.id, adaptation_type: select.value };
            const custom = fragment.value.trim();
            if (custom) payload.fragment = custom;
            await api("POST", "/adaptations", {
                query: { mock: isMock() },
                body: { kind: "json", value: payload },
                busyText: isMock() ? "Generando propuesta (mock)…" : "Generando propuesta con IA…",
            });
            await refreshProposals();
            $("proposals").scrollIntoView({ behavior: "smooth", block: "start" });
        }),
    }, "Proponer adaptación");

    card.append(
        el("div", {},
            badge(b.id, "id"), badge(b.severity), badge(b.category, "cat"), badge(b.source === "ai" ? "IA" : "reglas", "src"),
            b.fragment_found === false ? badge("fragmento no encontrado en el material", "error") : null,
            el("strong", {}, b.issue),
        ),
        b.original_text ? el("pre", {}, b.original_text) : el("p", { class: "muted" }, "(barrera global, sin fragmento citado)"),
        kv([
            ["Por qué", b.explanation],
            ["Recomendación", b.recommendation],
            ["Reescritura sugerida", b.suggested_rewrite || undefined],
        ]),
        el("div", { class: "row" },
            el("label", { class: "grow" }, "Tipo de adaptación", select),
        ),
        el("label", {}, "Fragmento a adaptar", fragment),
        el("div", { class: "row" }, submit),
    );
    return card;
}

// ---------------------------------------------------------------------------
// 4. Revisión docente
// ---------------------------------------------------------------------------

function requireAnalysisId() {
    const id = state.analysis && state.analysis.analysis_id;
    if (!id) throw new InputError("Primero generá o recuperá un diagnóstico.");
    return id;
}

async function refreshProposals() {
    const analysisId = requireAnalysisId();
    state.proposals = await api("GET", "/adaptations", { query: { analysis_id: analysisId } });
    renderProposals();
}

function barrierLabel(barrierId) {
    const b = ((state.analysis && state.analysis.barriers) || []).find((x) => x.id === barrierId);
    return b ? `${barrierId} · ${b.issue}` : barrierId;
}

function renderProposals() {
    const box = $("proposals");
    if (!state.proposals.length) {
        box.replaceChildren(el("p", { class: "muted" }, "Sin propuestas todavía. Pedí una desde una barrera (paso 3)."));
        return;
    }
    const counts = {};
    for (const p of state.proposals) counts[p.status] = (counts[p.status] || 0) + 1;
    box.replaceChildren(
        el("p", {}, Object.entries(counts).map(([status, n]) => badge(`${status}: ${n}`, status))),
        ...state.proposals.map((p) => proposalCard(p)),
    );
}

async function decide(proposalId, decision, editedText) {
    const value = { decision };
    if (decision === "editada") value.edited_text = editedText;
    await api("POST", `/adaptations/${encodeURIComponent(proposalId)}/decision`, { body: { kind: "json", value } });
    await refreshProposals();
    await refreshDecisions();
}

async function undo(proposalId) {
    await api("POST", `/adaptations/${encodeURIComponent(proposalId)}/undo`);
    await refreshProposals();
    await refreshDecisions();
}

function proposalActions(p, card) {
    if (p.status !== "pendiente") {
        return el("div", { class: "row" }, el("button", {
            type: "button", class: "secondary",
            onclick: () => run(card, () => undo(p.proposal_id)),
        }, "Deshacer decisión"));
    }
    const editor = el("textarea", { rows: 5, value: p.proposed_text });
    return el("div", {},
        el("div", { class: "row" },
            el("button", { type: "button", onclick: () => run(card, () => decide(p.proposal_id, "aceptada")) }, "Aceptar"),
            el("button", { type: "button", class: "danger", onclick: () => run(card, () => decide(p.proposal_id, "descartada")) }, "Descartar"),
        ),
        el("details", {},
            el("summary", {}, "Editar antes de aceptar"),
            el("label", {}, "Texto final del docente", editor),
            el("div", { class: "row" },
                el("button", {
                    type: "button",
                    onclick: () => run(card, async () => {
                        if (!editor.value.trim()) throw new InputError("El texto editado no puede estar vacío.");
                        await decide(p.proposal_id, "editada", editor.value);
                    }),
                }, "Guardar edición"),
            ),
        ),
    );
}

function proposalCard(p) {
    const card = el("div", { class: "card" });
    card.append(
        el("div", {},
            badge(p.status), badge(ADAPTATION_TYPES[p.adaptation_type] || p.adaptation_type, "type"),
            badge(p.fragment_source === "request" ? "fragmento del docente" : "fragmento de la barrera", "src"),
            el("strong", {}, barrierLabel(p.barrier_id)),
        ),
        el("div", { class: "cols" },
            el("div", {}, el("h3", {}, "Original"), el("pre", {}, p.original_text)),
            el("div", {}, el("h3", {}, "Propuesta"), el("pre", {}, p.proposed_text)),
        ),
        kv([
            ["Explicación", p.explanation],
            ["Objetivo conservado", p.preserved_objective],
            ["Texto final", p.final_text],
            ["Decidida", p.decided_at ? fmtDate(p.decided_at) : undefined],
            ["Modelo", p.metadata ? `${p.metadata.provider} · ${p.metadata.model} · ${p.metadata.latency_ms} ms` : undefined],
            ["proposal_id", p.proposal_id],
        ]),
        p.warnings && p.warnings.length ? el("ul", {}, p.warnings.map((w) => el("li", {}, w))) : null,
        proposalActions(p, card),
        rawJson(p),
    );
    return card;
}

// ---------------------------------------------------------------------------
// 5. Registro de decisiones
// ---------------------------------------------------------------------------

async function refreshDecisions() {
    const analysisId = requireAnalysisId();
    const entries = await api("GET", "/adaptations/decisions", { query: { analysis_id: analysisId } });
    const box = $("decisions");
    if (!entries.length) {
        box.replaceChildren(el("p", { class: "muted" }, "Sin decisiones todavía."));
        return;
    }
    box.replaceChildren(el("table", {},
        el("tr", {},
            el("th", {}, "Momento"), el("th", {}, "Barrera"), el("th", {}, "Tipo"),
            el("th", {}, "Acción"), el("th", {}, "Estado"), el("th", {}, "Texto del docente")),
        entries.map((e) => el("tr", {},
            el("td", {}, new Date(e.created_at).toLocaleString()),
            el("td", {}, e.barrier_id),
            el("td", {}, ADAPTATION_TYPES[e.adaptation_type] || e.adaptation_type),
            el("td", {}, e.action),
            el("td", {}, badge(e.from_status), "→ ", badge(e.to_status)),
            el("td", {}, e.edited_text || "—"))),
    ));
}

// ---------------------------------------------------------------------------
// Inicio
// ---------------------------------------------------------------------------

function init() {
    const fromQuery = new URLSearchParams(location.search).get("api");
    setApiBase(fromQuery || storageGet("innovalab.apiBase") || window.INNOVALAB_DEFAULT_API || "");
    if (fromQuery) history.replaceState(null, "", location.pathname); // limpia ?api= de la barra

    const savedMock = storageGet("innovalab.mock");
    if (savedMock !== null) $("mock").checked = savedMock === "true";

    $("api-url").addEventListener("change", (e) => setApiBase(e.target.value));
    $("mock").addEventListener("change", (e) => storageSet("innovalab.mock", String(e.target.checked)));
    $("btn-health").addEventListener("click", checkHealth);

    for (const tab of document.querySelectorAll(".tab")) tab.addEventListener("click", () => switchTab(tab.dataset.tab));
    $("text-input").addEventListener("input", updateTextCount);
    $("btn-sample-text").addEventListener("click", () => { $("text-input").value = SAMPLE_TEXT; updateTextCount(); });
    $("pdf-input").addEventListener("change", updatePdfInfo);

    const material = document.querySelector("#tab-text").parentElement;
    $("btn-process-text").addEventListener("click", () => run(material, processText));
    $("btn-analyze-text").addEventListener("click", () => run(material, analyzeText));
    $("btn-process-pdf").addEventListener("click", () => run(material, processPdf));
    $("btn-analyze-pdf").addEventListener("click", () => run(material, analyzePdf));

    const diagnosisSection = $("diagnosis").parentElement;
    $("btn-load-analysis").addEventListener("click", () => run(diagnosisSection, loadAnalysis));
    $("btn-refresh-proposals").addEventListener("click", () => run($("proposals").parentElement, refreshProposals));
    $("btn-refresh-decisions").addEventListener("click", () => run($("decisions").parentElement, refreshDecisions));
    $("btn-clear-log").addEventListener("click", () =>
        $("log-entries").replaceChildren(el("p", { class: "muted" }, "Todavía no se hizo ninguna llamada.")));

    updateTextCount();
}

init();
