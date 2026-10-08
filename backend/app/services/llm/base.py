"""
Tipos y errores comunes a todos los adaptadores de proveedores de IA.

Cada adaptador traduce los errores de su SDK a estas excepciones, así
LLMService puede rotar entre conexiones sin conocer a ningún proveedor.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AIConnection:
    """Conexión de IA cargada desde /admin, con la API key ya descifrada."""

    id: int
    label: str
    provider: str
    base_url: str | None
    model: str
    api_key: str
    extra_params: dict = field(default_factory=dict)
    supports_vision: bool = False



@dataclass
class Usage:
    prompt_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    total_tokens: int = 0


@dataclass
class AdapterResult:
    text: str
    usage: Usage | None


class ProviderRateLimitError(Exception):
    """429 del proveedor: la conexión queda en cooldown hasta `until` (UTC)."""

    def __init__(self, message: str, until: datetime):
        super().__init__(message)
        self.until = until


class ProviderServerError(Exception):
    """5xx, timeout o error de red: reintentable, y la request cuenta para la cuota."""


class LLMInvalidResponseError(Exception):
    """El modelo respondió, pero no con un JSON válido para el schema pedido."""


class LLMUnavailableError(Exception):
    """Ninguna conexión pudo responder por errores del proveedor (5xx / red)."""
