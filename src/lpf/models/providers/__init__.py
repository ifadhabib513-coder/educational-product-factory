"""Live model providers — real LLM backends behind the ``ModelProvider`` seam."""

from __future__ import annotations

from typing import Any

from lpf.errors import ConfigError
from lpf.models.providers.base import HttpChatModel
from lpf.models.providers.ollama import OllamaModel
from lpf.models.providers.openai_compatible import OpenAICompatibleModel
from lpf.models.providers.opencode_server import OpenCodeServerModel
from lpf.research.transport import RetryPolicy

__all__ = ["HttpChatModel", "OllamaModel", "OpenAICompatibleModel", "OpenCodeServerModel", "create_live_model"]

_KIND_CLASSES: dict[str, type[HttpChatModel]] = {
    OpenAICompatibleModel.kind: OpenAICompatibleModel,
    OllamaModel.kind: OllamaModel,
    OpenCodeServerModel.kind: OpenCodeServerModel,
}


def _normalize_kind(kind: str) -> str:
    """Fold a provider kind to its canonical name.

    ``openai_compatible`` and ``OPENAI-COMPATIBLE`` both resolve to the
    canonical ``openai-compatible``, so the CLI/env spelling and the class
    ``kind`` never drift into an ``UNKNOWN_MODEL_KIND`` again.
    """
    return kind.strip().lower().replace("_", "-")


def create_live_model(
    kind: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    client: Any = None,
    retry: RetryPolicy | None = None,
    timeout_seconds: float = 60.0,
) -> HttpChatModel:
    """Build a live adapter by kind name.

    ``client`` is an optional ``httpx.AsyncClient`` injected for tests; when
    omitted each adapter builds a real client with a timeout. ``retry`` and
    ``timeout_seconds`` configure the bounded retry/backoff policy.
    """
    normalized = _normalize_kind(kind)
    try:
        cls = _KIND_CLASSES[normalized]
    except KeyError as exc:
        raise ConfigError(
            code="UNKNOWN_MODEL_KIND",
            message=f"Unknown model provider kind '{kind}'.",
            details={"kind": kind, "known": sorted(_KIND_CLASSES)},
        ) from exc
    return cls(
        model=model,
        base_url=base_url,
        api_key=api_key,
        client=client,
        retry=retry,
        timeout_seconds=timeout_seconds,
    )
