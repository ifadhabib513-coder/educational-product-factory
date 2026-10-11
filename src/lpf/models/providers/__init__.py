"""Live model providers — real LLM backends behind the ``ModelProvider`` seam."""

from __future__ import annotations

from typing import Any

from lpf.errors import ConfigError
from lpf.models.providers.base import HttpChatModel
from lpf.models.providers.ollama import OllamaModel
from lpf.models.providers.openai_compatible import OpenAICompatibleModel

__all__ = ["HttpChatModel", "OllamaModel", "OpenAICompatibleModel", "create_live_model"]

_KIND_CLASSES: dict[str, type[HttpChatModel]] = {
    OpenAICompatibleModel.kind: OpenAICompatibleModel,
    OllamaModel.kind: OllamaModel,
}


def create_live_model(
    kind: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    client: Any = None,
) -> HttpChatModel:
    """Build a live adapter by kind name.

    ``client`` is an optional ``httpx.AsyncClient`` injected for tests; when
    omitted each adapter builds a real client with a timeout.
    """
    try:
        cls = _KIND_CLASSES[kind]
    except KeyError as exc:
        raise ConfigError(
            code="UNKNOWN_MODEL_KIND",
            message=f"Unknown model provider kind '{kind}'.",
            details={"kind": kind, "known": sorted(_KIND_CLASSES)},
        ) from exc
    return cls(model=model, base_url=base_url, api_key=api_key, client=client)
