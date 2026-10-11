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

from lpf.domain.content import SolutionStep
from lpf.domain.worked_example import WorkedExampleDraft


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
            return self._structured(prompt, schema)
        return self._compose(prompt)

    async def count_tokens(self, text: str) -> int:
        """Whitespace token estimate, matching ``MockProvider``."""
        return len(text.split())

    def _structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        """Deterministic structured reply for the schemas the stages ask for.

        The offline pipeline keeps producing the byte-identical worked examples
        it produced before the Content stage asked the model for them: the mock
        returns exactly the canonical template, so a structured call is a no-op
        with respect to the package. Any other schema is refused loudly rather
        than hallucinated.
        """
        if schema is WorkedExampleDraft:
            return WorkedExampleDraft(
                problem_statement=f"Apply what you just learned: {self._title(prompt)}.",
                solution_steps=[
                    SolutionStep(order=1, statement="Identify what is being asked."),
                    SolutionStep(order=2, statement="Choose the method that fits."),
                    SolutionStep(
                        order=3,
                        statement="Carry it out and check the result.",
                        expression="result = apply(method, problem)",
                    ),
                ],
                final_answer="The problem is solved and the result checked.",
                common_errors=["Skips the check step."],
            )
        raise ValueError(
            f"DeterministicMockModel cannot produce '{schema.__name__}'; "
            "register a deterministic reply for it or use a live provider."
        )

    @staticmethod
    def _title(prompt: str) -> str:
        """Recover the quoted title from the worked-example prompt."""
        start = prompt.find('"')
        end = prompt.rfind('"')
        if start != -1 and end > start:
            return prompt[start + 1 : end]
        return prompt.strip().splitlines()[0][:200]

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
