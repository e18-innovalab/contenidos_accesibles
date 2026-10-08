import re
from datetime import datetime, timedelta, timezone

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.services.llm.base import (
    AdapterResult,
    AIConnection,
    ProviderRateLimitError,
    ProviderServerError,
    Usage,
)

# La cuota diaria de la capa gratuita se reinicia a la medianoche del Pacífico.
# Se usa UTC-8 fijo (PST): durante el horario de verano (PDT) espera una hora de
# más, que es preferible a reintentar antes de tiempo. Evita depender de tzdata
# (no viene instalado en Windows).
PACIFIC_STANDARD_TIME = timezone(timedelta(hours=-8))
DEFAULT_MINUTE_COOLDOWN_S = 60


def _rate_limit_until(error: errors.APIError) -> datetime:
    """
    Calcula hasta cuándo dejar la conexión fuera de rotación a partir del 429 de Google:
    cuota diaria (quotaId con 'PerDay') -> próxima medianoche del Pacífico;
    cualquier otra (por minuto) -> el retryDelay sugerido por Google, o 60s.
    """
    now = datetime.now(timezone.utc)
    details = (
        (error.details or {}).get("error", {}).get("details", [])
        if isinstance(error.details, dict)
        else []
    )

    quota_ids = [v.get("quotaId", "") for d in details for v in d.get("violations", [])]
    if any("PerDay" in q for q in quota_ids):
        pacific_now = now.astimezone(PACIFIC_STANDARD_TIME)
        next_midnight = (pacific_now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return next_midnight.astimezone(timezone.utc)

    retry_delay = next((d.get("retryDelay") for d in details if d.get("retryDelay")), None)
    match = re.fullmatch(r"(\d+(?:\.\d+)?)s", retry_delay or "")
    seconds = float(match.group(1)) if match else DEFAULT_MINUTE_COOLDOWN_S
    return now + timedelta(seconds=seconds)


class GeminiAdapter:
    """
    Adaptador con el SDK nativo de Google (google-genai).

    extra_params admitidos: `thinking_budget` (0 desactiva el thinking de
    Gemini 2.5) y cualquier otro campo de types.GenerateContentConfig.
    """

    def __init__(self):
        # Clave (id, api_key): si se edita la key desde /admin, se crea un cliente nuevo.
        self._clients: dict[tuple[int, str], genai.Client] = {}

    def _client(self, conn: AIConnection) -> genai.Client:
        cache_key = (conn.id, conn.api_key)
        if cache_key not in self._clients:
            self._clients[cache_key] = genai.Client(api_key=conn.api_key)
        return self._clients[cache_key]

    async def generate(
        self,
        conn: AIConnection,
        *,
        system_instruction: str | None,
        contents: str,
        schema: type[BaseModel] | None,
        temperature: float | None,
        max_output_tokens: int | None,
        extra_params: dict,
    ) -> AdapterResult:
        params = dict(extra_params)
        thinking_budget = params.pop("thinking_budget", None)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            # Sin tools: se desactiva AFC para evitar el warning del SDK en cada llamada.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            **params,
        )
        if schema is not None:
            config.response_mime_type = "application/json"
            config.response_schema = schema
        if thinking_budget is not None:
            config.thinking_config = types.ThinkingConfig(thinking_budget=thinking_budget)

        # Normalizar contents si viene como lista multimodal estructurada
        payload_contents = contents
        if isinstance(contents, list):
            payload_contents = []
            for item in contents:
                if isinstance(item, dict) and item.get("type") == "image":
                    payload_contents.append(
                        types.Part.from_bytes(
                            data=item["data"],
                            mime_type=item.get("mime_type", "image/png"),
                        )
                    )
                elif isinstance(item, dict) and item.get("type") == "text":
                    payload_contents.append(item["text"])
                else:
                    payload_contents.append(item)

        try:
            response = await self._client(conn).aio.models.generate_content(
                model=conn.model, contents=payload_contents, config=config
            )

        except errors.APIError as e:
            if e.code == 429:
                raise ProviderRateLimitError(str(e), _rate_limit_until(e)) from e
            if e.code and e.code >= 500:
                raise ProviderServerError(str(e)) from e
            raise
        except httpx.TransportError as e:
            raise ProviderServerError(f"Error de red con Gemini: {e}") from e

        meta = response.usage_metadata
        usage = (
            Usage(
                prompt_tokens=meta.prompt_token_count or 0,
                output_tokens=meta.candidates_token_count or 0,
                thinking_tokens=meta.thoughts_token_count or 0,
                total_tokens=meta.total_token_count or 0,
            )
            if meta is not None
            else None
        )
        return AdapterResult(text=response.text or "", usage=usage)
