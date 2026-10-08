import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import openai
from pydantic import BaseModel


from app.services.llm.base import (
    AdapterResult,
    AIConnection,
    ProviderRateLimitError,
    ProviderServerError,
    Usage,
)

DEFAULT_RATE_LIMIT_COOLDOWN_S = 60
REQUEST_TIMEOUT_S = 120

# Modos de salida estructurada, del más estricto al más permisivo. No todos los
# proveedores soportan json_schema estricto; si uno lo rechaza (400/422) se baja
# al siguiente, y el modo que funcionó queda recordado para esa conexión+modelo.
# En todos los casos LLMService valida el JSON con Pydantic.
STRUCTURED_MODES = ("json_schema", "json_object", "prompt_only")


def to_strict_json_schema(schema: type[BaseModel]) -> dict:
    """
    JSON Schema compatible con el modo `strict` de OpenAI (y de Groq, etc.):
    referencias inline, todos los campos en `required`, sin propiedades
    adicionales ni `title`/`default`.
    """
    raw = schema.model_json_schema()
    defs = raw.pop("$defs", {})

    def convert(node):
        if isinstance(node, list):
            return [convert(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return convert(defs[node["$ref"].split("/")[-1]])
        out = {k: convert(v) for k, v in node.items() if k not in ("title", "default")}
        if out.get("type") == "object" and "properties" in out:
            out["required"] = list(out["properties"])
            out["additionalProperties"] = False
        return out

    return convert(raw)


def _rate_limit_until(error: openai.RateLimitError) -> datetime:
    retry_after = error.response.headers.get("retry-after") if error.response else None
    try:
        seconds = float(retry_after) if retry_after else DEFAULT_RATE_LIMIT_COOLDOWN_S
    except ValueError:
        seconds = DEFAULT_RATE_LIMIT_COOLDOWN_S
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


class OpenAICompatibleAdapter:
    """
    Adaptador para cualquier API compatible con OpenAI Chat Completions
    (Groq, Mistral, OpenRouter, Cerebras, DeepSeek, Ollama, Together, etc.).

    extra_params se envía tal cual en el body del request, así se pueden usar
    parámetros propios de cada proveedor (ej. `reasoning_effort` en Groq) sin
    tocar código.
    """

    def __init__(self):
        self._clients: dict[tuple[int, str, str | None], openai.AsyncOpenAI] = {}
        self._structured_mode: dict[tuple[int, str], str] = {}

    def _client(self, conn: AIConnection) -> openai.AsyncOpenAI:
        cache_key = (conn.id, conn.api_key, conn.base_url)
        if cache_key not in self._clients:
            self._clients[cache_key] = openai.AsyncOpenAI(
                api_key=conn.api_key,
                base_url=conn.base_url or None,
                # Los reintentos y la rotación los maneja LLMService.
                max_retries=0,
                timeout=REQUEST_TIMEOUT_S,
            )
        return self._clients[cache_key]

    @staticmethod
    def _request_args(
        mode: str, system_instruction: str | None, schema: type[BaseModel]
    ) -> tuple[str | None, dict | None]:
        if mode == "json_schema":
            return system_instruction, {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": to_strict_json_schema(schema),
                    "strict": True,
                },
            }
        schema_hint = (
            "Respondé únicamente con un objeto JSON válido (sin texto adicional ni "
            "bloques de código) que cumpla este JSON Schema:\n"
            + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        )
        system = f"{system_instruction}\n\n{schema_hint}" if system_instruction else schema_hint
        response_format = {"type": "json_object"} if mode == "json_object" else None
        return system, response_format

    async def _complete(
        self,
        conn: AIConnection,
        system: str | None,
        contents: Any,
        response_format: dict | None,
        temperature: float | None,
        max_output_tokens: int | None,
        extra_params: dict,
    ):
        user_content = contents
        if isinstance(contents, list):
            user_content = []
            for item in contents:
                if isinstance(item, dict) and item.get("type") == "image":
                    b64 = base64.b64encode(item["data"]).decode("ascii")
                    mime = item.get("mime_type", "image/png")
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    })
                elif isinstance(item, dict) and item.get("type") == "text":
                    user_content.append({"type": "text", "text": item["text"]})
                elif isinstance(item, str):
                    user_content.append({"type": "text", "text": item})
                else:
                    user_content.append(item)

        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": user_content}
        ]
        kwargs = {"model": conn.model, "messages": messages}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_output_tokens is not None:
            kwargs["max_tokens"] = max_output_tokens
        if response_format is not None:
            kwargs["response_format"] = response_format
        if extra_params:
            kwargs["extra_body"] = extra_params

        try:
            return await self._client(conn).chat.completions.create(**kwargs)
        except openai.RateLimitError as e:
            raise ProviderRateLimitError(str(e), _rate_limit_until(e)) from e
        except (openai.InternalServerError, openai.APIConnectionError) as e:
            # APITimeoutError es subclase de APIConnectionError.
            raise ProviderServerError(str(e)) from e

    async def generate(
        self,
        conn: AIConnection,
        *,
        system_instruction: str | None,
        contents: Any,
        schema: type[BaseModel] | None,
        temperature: float | None,
        max_output_tokens: int | None,
        extra_params: dict,
    ) -> AdapterResult:

        if schema is None:
            response = await self._complete(
                conn, system_instruction, contents, None, temperature, max_output_tokens, extra_params
            )
        else:
            mode_key = (conn.id, conn.model)
            start = STRUCTURED_MODES.index(self._structured_mode.get(mode_key, STRUCTURED_MODES[0]))
            for mode in STRUCTURED_MODES[start:]:
                system, response_format = self._request_args(mode, system_instruction, schema)
                try:
                    response = await self._complete(
                        conn, system, contents, response_format,
                        temperature, max_output_tokens, extra_params,
                    )
                except (openai.BadRequestError, openai.UnprocessableEntityError):
                    if mode == STRUCTURED_MODES[-1]:
                        raise
                    continue
                self._structured_mode[mode_key] = mode
                break

        choice = response.choices[0] if response.choices else None
        text = (choice.message.content if choice else None) or ""
        u = response.usage
        usage = None
        if u is not None:
            details = getattr(u, "completion_tokens_details", None)
            usage = Usage(
                prompt_tokens=u.prompt_tokens or 0,
                output_tokens=u.completion_tokens or 0,
                thinking_tokens=(getattr(details, "reasoning_tokens", None) or 0) if details else 0,
                total_tokens=u.total_tokens or 0,
            )
        return AdapterResult(text=text, usage=usage)
