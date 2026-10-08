"""
Plantillas de proveedores para el panel /admin.

Son solo valores sugeridos para completar el formulario: cualquier proveedor
con API compatible con OpenAI funciona eligiendo "custom" e indicando base_url
y modelo. Los límites cambian seguido; verificarlos en la consola de cada
proveedor (valores relevados en septiembre de 2026).
"""

from dataclasses import asdict, dataclass, field

# Proveedores que usan el SDK nativo de Google. Todo lo demás se habla con el
# adaptador compatible con OpenAI (Chat Completions).
NATIVE_GEMINI_PROVIDERS = {"gemini"}


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    label: str
    base_url: str | None
    model: str
    rpm: int | None = None
    tpm: int | None = None
    rpd: int | None = None
    tpd: int | None = None
    extra_params: dict = field(default_factory=dict)
    notes: str = ""


PRESETS: list[ProviderPreset] = [
    ProviderPreset(
        id="gemini",
        label="Google Gemini (SDK nativo)",
        base_url=None,
        model="gemini-2.5-flash",
        rpm=5, tpm=250_000, rpd=20,
        extra_params={"thinking_budget": 0},
        notes="Capa gratuita: 20 requests/día por proyecto. Límites reales en AI Studio > Rate limits.",
    ),
    ProviderPreset(
        id="groq",
        label="Groq",
        base_url="https://api.groq.com/openai/v1",
        model="openai/gpt-oss-120b",
        rpm=30, tpm=8_000, rpd=1_000, tpd=200_000,
        extra_params={"reasoning_effort": "low"},
        notes="Cuota por organización y por modelo: otro modelo (ej. qwen/qwen3.8-27b) suma cuota aparte.",
    ),
    ProviderPreset(
        id="mistral",
        label="Mistral",
        base_url="https://api.mistral.ai/v1",
        model="mistral-small-latest",
        rpm=60,
        notes="Plan Experiment: ~1 req/s y ~1.000M tokens/mes. Desactivar el entrenamiento con tus datos en la consola.",
    ),
    ProviderPreset(
        id="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        model="",
        rpm=20, rpd=50,
        notes="Modelos gratuitos terminan en ':free'. 50 req/día (1.000 si alguna vez cargaste USD 10).",
    ),
    ProviderPreset(
        id="cerebras",
        label="Cerebras",
        base_url="https://api.cerebras.ai/v1",
        model="gpt-oss-120b",
        notes="Sin capa gratuita permanente desde julio 2026 (solo crédito de prueba).",
    ),
    ProviderPreset(
        id="ollama",
        label="Ollama (local)",
        base_url="http://localhost:11434/v1",
        model="llama3.1",
        notes="Modelo corriendo en tu máquina: sin cuotas. La API key puede ser cualquier texto.",
    ),
    ProviderPreset(
        id="custom",
        label="Otro compatible con OpenAI",
        base_url="",
        model="",
        notes="Cualquier API compatible con OpenAI Chat Completions (DeepSeek, Together, Anthropic, etc.).",
    ),
]

PRESETS_BY_ID = {p.id: p for p in PRESETS}


def presets_as_dicts() -> list[dict]:
    return [asdict(p) for p in PRESETS]


def uses_native_gemini(provider: str) -> bool:
    return provider in NATIVE_GEMINI_PROVIDERS


VISION_CAPABLE_PROVIDERS = {"gemini"}


def supports_vision(provider: str, model: str = "", extra_params: dict | None = None) -> bool:
    """Indica si una conexión cuenta con soporte para visión/multimodalidad."""
    if extra_params and extra_params.get("supports_vision") is True:
        return True
    if provider in VISION_CAPABLE_PROVIDERS:
        return True
    m = model.lower()
    if any(tag in m for tag in ("gpt-4o", "gpt-4-turbo", "vision", "-vl", "claude-3")):
        return True
    return False

