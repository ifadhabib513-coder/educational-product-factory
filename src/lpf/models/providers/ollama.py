"""Ollama native chat adapter.

Targets Ollama's native ``/api/chat`` endpoint. Structured output uses the
``format: json`` request field, which asks the model to emit JSON and replies
with ``message.content`` rather than ``choices[0].message.content``.
"""

from __future__ import annotations

from typing import Any

from lpf.errors import ProviderError
from lpf.models.providers.base import HttpChatModel

__all__ = ["OllamaModel"]


class OllamaModel(HttpChatModel):
    """A model served by a local Ollama instance, over its native API."""

    kind = "ollama"
    endpoint = "/api/chat"
    default_model = "llama3.2"
    default_base_url = "http://localhost:11434"

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        client: Any = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> None:
        super().__init__(
            model=model,
            base_url=base_url,
            api_key=api_key,
            client=client,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def json_request_field(self) -> dict[str, Any]:
        return {"format": "json"}

    def parse_content(self, payload: object) -> str:
        if isinstance(payload, dict):
            message = payload.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
        raise ProviderError(
            code="PROVIDER_RESPONSE_MALFORMED",
            message="Provider response is missing message.content.",
            details={"payload_preview": repr(payload)[:500]},
        )
