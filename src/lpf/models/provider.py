"""Model provider abstraction — Protocol + MockProvider + ModelRouter."""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model tiers
# ---------------------------------------------------------------------------


class ModelTier(StrEnum):
    """Cost/quality tiers for model routing."""

    CHEAP = "cheap"
    MEDIUM = "medium"
    STRONG = "strong"


class TaskType(StrEnum):
    """Task types for model routing."""

    METADATA = "metadata"
    CLASSIFICATION = "classification"
    SIMPLE_REWRITE = "simple_rewrite"
    CONTENT_GENERATION = "content_generation"
    RESEARCH_SYNTHESIS = "research_synthesis"
    CURRICULUM_DESIGN = "curriculum_design"
    QA_ARBITRATION = "qa_arbitration"
    REASONING = "reasoning"
    MATH_SOLVING = "math_solving"


# Default routing: task_type → tier
DEFAULT_ROUTING: dict[TaskType, ModelTier] = {
    TaskType.METADATA: ModelTier.CHEAP,
    TaskType.CLASSIFICATION: ModelTier.CHEAP,
    TaskType.SIMPLE_REWRITE: ModelTier.CHEAP,
    TaskType.CONTENT_GENERATION: ModelTier.MEDIUM,
    TaskType.RESEARCH_SYNTHESIS: ModelTier.STRONG,
    TaskType.CURRICULUM_DESIGN: ModelTier.STRONG,
    TaskType.QA_ARBITRATION: ModelTier.STRONG,
    TaskType.REASONING: ModelTier.STRONG,
    TaskType.MATH_SOLVING: ModelTier.CHEAP,  # Use Python/SymPy, not LLM
}


# ---------------------------------------------------------------------------
# ModelProvider Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ModelProvider(Protocol):
    """Protocol for all LLM providers.

    Agents never know which vendor they're using.
    """

    async def generate(
        self,
        *,
        messages: list[dict[str, str]],
        schema: type[BaseModel] | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str | BaseModel:
        """Generate a response from the LLM.

        If schema is provided, return a validated Pydantic instance.
        Otherwise return a string.
        """
        ...

    async def count_tokens(self, text: str) -> int:
        """Estimate token count for a text string."""
        ...


# ---------------------------------------------------------------------------
# MockProvider — deterministic responses for testing
# ---------------------------------------------------------------------------


class MockProvider:
    """Returns deterministic responses for testing.

    Supports schema-based responses via a registry of response factories.
    """

    def __init__(
        self,
        default_response: str = "mock response",
        response_registry: dict[str, Callable[[], Any]] | None = None,
    ) -> None:
        self._default = default_response
        self._registry = response_registry or {}
        self._call_count = 0
        self._last_messages: list[dict[str, str]] = []

    async def generate(
        self,
        *,
        messages: list[dict[str, str]],
        schema: type[BaseModel] | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str | BaseModel:
        self._call_count += 1
        self._last_messages = messages

        # Check registry for schema-based response
        if schema is not None:
            schema_name = schema.__name__
            if schema_name in self._registry:
                return self._registry[schema_name]()

        return self._default

    async def count_tokens(self, text: str) -> int:
        return len(text.split())

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def last_messages(self) -> list[dict[str, str]]:
        return self._last_messages


# ---------------------------------------------------------------------------
# ModelRouter — maps task types to providers/tiers
# ---------------------------------------------------------------------------


class ModelRouter:
    """Routes task types to appropriate model providers and tiers.

    Uses a configurable routing table. Default maps cheap tasks to
    cheap models, content to medium, and reasoning/synthesis to strong.
    """

    def __init__(
        self,
        providers: dict[ModelTier, ModelProvider] | None = None,
        routing: dict[TaskType, ModelTier] | None = None,
    ) -> None:
        self._providers = providers or {}
        self._routing = routing or DEFAULT_ROUTING.copy()

    def get_provider(self, task_type: TaskType) -> tuple[ModelProvider, ModelTier]:
        """Get the provider and tier for a task type."""
        tier = self._routing.get(task_type, ModelTier.MEDIUM)
        provider = self._providers.get(tier)
        if provider is None:
            raise ValueError(
                f"No provider registered for tier '{tier}' (task_type={task_type.value})"
            )
        return provider, tier

    def register_provider(self, tier: ModelTier, provider: ModelProvider) -> None:
        """Register a provider for a tier."""
        self._providers[tier] = provider

    def override_routing(self, task_type: TaskType, tier: ModelTier) -> None:
        """Override the default routing for a task type."""
        self._routing[task_type] = tier

    def get_model_name(self, task_type: TaskType) -> str | None:
        """Get the model name hint for a task type (for logging)."""
        tier = self._routing.get(task_type, ModelTier.MEDIUM)
        provider = self._providers.get(tier)
        if isinstance(provider, MockProvider):
            return f"mock-{tier.value}"
        return tier.value
