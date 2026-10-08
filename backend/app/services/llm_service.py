import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.services import key_rotation_service
from app.services.key_rotation_service import AllKeysExhaustedError
from app.services.llm.base import (
    AdapterResult,
    AIConnection,
    LLMInvalidResponseError,
    LLMUnavailableError,
    ProviderRateLimitError,
    ProviderServerError,
    Usage,
)
from app.services.llm.gemini_adapter import GeminiAdapter
from app.services.llm.openai_adapter import OpenAICompatibleAdapter
from app.services.llm.providers import uses_native_gemini

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)

# Reintentos sobre la misma conexión ante 5xx / red: esperas de 2s y 4s.
MAX_SERVER_RETRIES = 2
# Si una conexión sigue fallando (5xx) o está mal configurada (key inválida,
# modelo inexistente), queda fuera de rotación un rato y se usa la siguiente.
SERVER_ERROR_COOLDOWN_S = 60
CONFIG_ERROR_COOLDOWN_S = 300

_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


@dataclass
class StructuredResult(Generic[SchemaT]):
    parsed: SchemaT
    provider: str
    model: str
    connection_label: str
    latency_ms: int
    usage: Usage | None


def _parse_json(text: str, schema: type[SchemaT]) -> SchemaT:
    match = _CODE_FENCE.match(text)
    payload = match.group(1) if match else text
    try:
        return schema.model_validate_json(payload)
    except ValidationError as e:
        raise LLMInvalidResponseError(
            f"El modelo no devolvió un JSON válido para {schema.__name__}: "
            f"{e.error_count()} error(es) de validación."
        ) from e


class LLMService:
    """
    Capa de servicio para modelos de lenguaje, independiente del proveedor.

    Usa las conexiones cargadas en /admin en orden de prioridad y rota entre
    ellas (aunque sean de proveedores distintos) ante límites o fallas. Los
    endpoints y el motor de accesibilidad no conocen a ningún proveedor.
    """

    def __init__(self):
        self._gemini = GeminiAdapter()
        self._openai_compatible = OpenAICompatibleAdapter()

    def _adapter(self, conn: AIConnection):
        return self._gemini if uses_native_gemini(conn.provider) else self._openai_compatible

    async def _generate(
        self,
        *,
        system_instruction: str | None,
        contents: Any,
        schema: type[BaseModel] | None,
        temperature: float | None,
        max_output_tokens: int | None,
        overrides: dict | None,
        require_vision: bool = False,
    ) -> tuple[AIConnection, AdapterResult]:
        last_error: Exception | None = None
        while True:
            try:
                conn = key_rotation_service.get_active_connection(require_vision=require_vision)
            except AllKeysExhaustedError:
                if last_error is not None:
                    raise LLMUnavailableError(
                        "Ninguna conexión de IA pudo responder. "
                        f"Último error: {last_error}"
                    ) from last_error
                raise

            params = {**conn.extra_params, **(overrides or {})}
            for attempt in range(MAX_SERVER_RETRIES + 1):
                try:
                    result = await self._adapter(conn).generate(
                        conn,
                        system_instruction=system_instruction,
                        contents=contents,
                        schema=schema,
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                        extra_params=params,
                    )
                except ProviderRateLimitError as e:
                    key_rotation_service.mark_rate_limited(conn.id, e.until)
                    break
                except ProviderServerError as e:
                    key_rotation_service.record_failed_request(conn.id)
                    last_error = e
                    if attempt < MAX_SERVER_RETRIES:
                        await asyncio.sleep(2 ** (attempt + 1))
                        continue
                    self._cooldown(conn, SERVER_ERROR_COOLDOWN_S)
                    break
                except Exception as e:
                    # Key inválida, modelo inexistente, parámetro no soportado, etc.
                    logger.warning("Conexión de IA '%s' falló: %s", conn.label, e)
                    last_error = e
                    self._cooldown(conn, CONFIG_ERROR_COOLDOWN_S)
                    break

                key_rotation_service.record_usage(conn.id, result.usage)
                return conn, result

    @staticmethod
    def _cooldown(conn: AIConnection, seconds: int) -> None:
        key_rotation_service.mark_rate_limited(
            conn.id, datetime.now(timezone.utc) + timedelta(seconds=seconds)
        )

    async def ping_connection(self) -> dict:
        """Envía un prompt mínimo para validar credenciales y conectividad."""
        conn, result = await self._generate(
            system_instruction=None,
            contents="Respondé únicamente con la palabra: CONECTADO",
            schema=None,
            temperature=None,
            max_output_tokens=None,
            overrides=None,
        )
        return {
            "status": "success",
            "connection": conn.label,
            "provider": conn.provider,
            "model": conn.model,
            "response": result.text.strip(),
        }

    async def generate_structured(
        self,
        *,
        system_instruction: str,
        contents: Any,
        schema: type[SchemaT],
        temperature: float = 0.2,
        max_output_tokens: int = 8192,
        overrides: dict | None = None,
        require_vision: bool = False,
    ) -> StructuredResult[SchemaT]:
        """
        Genera una respuesta tipada: se pide salida estructurada al proveedor
        (según lo que soporte) y el resultado siempre se valida con Pydantic.

        overrides: parámetros que pisan los extra_params de la conexión para
        esta llamada (ej. {"thinking_budget": 0}); útil en benchmarks.
        La latencia informada incluye reintentos y rotaciones.
        """
        started = time.perf_counter()
        conn, result = await self._generate(
            system_instruction=system_instruction,
            contents=contents,
            schema=schema,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            overrides=overrides,
            require_vision=require_vision,
        )

        latency_ms = int((time.perf_counter() - started) * 1000)
        # NOTE: GeminiAdapter ya parsea la respuesta de forma nativa (response.parsed),
        # pero la devuelve como texto (result.text) para mantener una interfaz uniforme
        # con OpenAICompatibleAdapter, que solo devuelve texto crudo.
        # _parse_json re-parsea ese texto con Pydantic, lo que es un paso redundante
        # para Gemini pero correcto. Optimización futura: que los adaptadores puedan
        # devolver el objeto ya parseado cuando el proveedor lo soporte nativamente.
        return StructuredResult(
            parsed=_parse_json(result.text, schema),
            provider=conn.provider,
            model=conn.model,
            connection_label=conn.label,
            latency_ms=latency_ms,
            usage=result.usage,
        )


llm_service = LLMService()
