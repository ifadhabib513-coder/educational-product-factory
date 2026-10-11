"""OpenAI-compatible chat completions adapter.

Targets any server that speaks the ``/chat/completions`` contract — OpenAI,
vLLM, llama.cpp server, LM Studio, Ollama's own OpenAI-compatible endpoint,
and most commercial proxies. Structured output uses ``response_format`` with
``json_object``, the most widely supported form.

Note: JSON mode expects the prompt itself to ask for JSON (OpenAI enforces
this); the adapter asks for JSON and validates the reply but does not rewrite
the caller's messages, so a schema'd call must be instructed in the prompt.
"""

from __future__ import annotations

from typing import Any

from lpf.errors import ProviderError
from lpf.models.providers.base import HttpChatModel

__all__ = ["OpenAICompatibleModel"]


class OpenAICompatibleModel(HttpChatModel):
    """A chat-completions model reached over an OpenAI-compatible API."""

    kind = "openai_compatible"
    endpoint = "/chat/completions"
    default_model = "gpt-4o-mini"
    default_base_url = "https://api.openai.com/v1"

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        client: Any = None,
        retry: Any = None,
        timeout_seconds: float = 60.0,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> None:
        super().__init__(
            model=model,
            base_url=base_url,
            api_key=api_key,
            client=client,
            retry=retry,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def request_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def json_request_field(self) -> dict[str, Any]:
        return {"response_format": {"type": "json_object"}}

    def parse_content(self, payload: object) -> str:
        if isinstance(payload, dict):
            choices = payload.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
        raise ProviderError(
            code="PROVIDER_RESPONSE_MALFORMED",
            message="Provider response is missing choices[0].message.content.",
            details={"payload_preview": repr(payload)[:500]},
        )
