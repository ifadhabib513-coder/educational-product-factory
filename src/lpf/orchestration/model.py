"""Deterministic mock model for the offline factory run.

This is a real implementation of the ``ModelProvider`` protocol, not a stub that
raises: stages call it exactly as they would call a hosted model, so the seam is
load-bearing today and swapping in a real provider is a one-line change.

It exists alongside ``MockProvider`` (which returns one fixed string) because the
offline pipeline needs prose that is *derived from its inputs* — a lesson for
"linear algebra" must mention linear algebra — while staying byte-identical across
runs. Output depends only on the prompt text, so no clock or randomness is read.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel


def _digest(text: str) -> str:
    """Short stable digest, used only to vary canned phrasing deterministically."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


class DeterministicMockModel:
    """A model that maps a prompt to deterministic, prompt-derived text."""

    def __init__(self, *, provider: str = "mock", model: str = "mock-deterministic") -> None:
        self.provider = provider
        self.model = model

    async def generate(
        self,
        *,
        messages: list[dict[str, str]],
        schema: type[BaseModel] | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str | BaseModel:
        """Return a response derived solely from the prompt.

        ``temperature`` and ``max_tokens`` are accepted for interface compatibility
        and deliberately ignored: a deterministic model has no sampling to control.
        """
        prompt = self._last_user_message(messages)
        if schema is not None:
            raise ValueError(
                "DeterministicMockModel returns text only; call without a schema and "
                "construct the artifact in the stage, or register a structured factory."
            )
        return self._compose(prompt)

    async def count_tokens(self, text: str) -> int:
        """Whitespace token estimate, matching ``MockProvider``."""
        return len(text.split())

    @staticmethod
    def _last_user_message(messages: list[dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")
        return messages[-1].get("content", "") if messages else ""

    @staticmethod
    def _compose(prompt: str) -> str:
        """Build a short, stable paragraph that references the prompt's subject."""
        subject = prompt.strip().splitlines()[0][:200] if prompt.strip() else "the topic"
        return (
            f"This passage explains {subject}. "
            "It defines the key idea in plain language, gives one concrete example, "
            "and states the common mistake learners make at this point. "
            f"Reference: {_digest(prompt)}."
        )


def protocol_satisfied(model: object) -> bool:
    """Whether ``model`` structurally satisfies ``ModelProvider``.

    Kept as a helper so tests can assert the seam without importing the Protocol
    in every file that builds a model.
    """
    from lpf.models.provider import ModelProvider

    return isinstance(model, ModelProvider)


__all__ = ["DeterministicMockModel", "protocol_satisfied"]
