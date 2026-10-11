"""Tests for model provider, router, and prompt registry."""

from __future__ import annotations

import pytest

from lpf.models.provider import (
    MockProvider,
    ModelRouter,
    ModelTier,
    TaskType,
)
from lpf.models.registry import PromptRegistry, PromptTemplate

# ---------------------------------------------------------------------------
# Tests: MockProvider
# ---------------------------------------------------------------------------


class TestMockProvider:
    @pytest.mark.asyncio
    async def test_generate_string(self) -> None:
        provider = MockProvider(default_response="hello")
        result = await provider.generate(messages=[{"role": "user", "content": "hi"}])
        assert result == "hello"
        assert provider.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_with_schema(self) -> None:
        from pydantic import BaseModel

        class MyOutput(BaseModel):
            answer: str

        provider = MockProvider(response_registry={"MyOutput": lambda: MyOutput(answer="42")})
        result = await provider.generate(
            messages=[{"role": "user", "content": "what?"}],
            schema=MyOutput,
        )
        assert isinstance(result, MyOutput)
        assert result.answer == "42"

    @pytest.mark.asyncio
    async def test_count_tokens(self) -> None:
        provider = MockProvider()
        count = await provider.count_tokens("hello world test")
        assert count == 3

    @pytest.mark.asyncio
    async def test_tracks_messages(self) -> None:
        provider = MockProvider()
        msgs = [{"role": "user", "content": "test"}]
        await provider.generate(messages=msgs)
        assert provider.last_messages == msgs


# ---------------------------------------------------------------------------
# Tests: ModelRouter
# ---------------------------------------------------------------------------


class TestModelRouter:
    def test_get_provider(self) -> None:
        mock = MockProvider()
        router = ModelRouter(providers={ModelTier.CHEAP: mock})
        provider, tier = router.get_provider(TaskType.METADATA)
        assert tier == ModelTier.CHEAP
        assert provider is mock

    def test_default_routing(self) -> None:
        mock_cheap = MockProvider()
        mock_medium = MockProvider()
        mock_strong = MockProvider()
        router = ModelRouter(
            providers={
                ModelTier.CHEAP: mock_cheap,
                ModelTier.MEDIUM: mock_medium,
                ModelTier.STRONG: mock_strong,
            }
        )
        _, tier = router.get_provider(TaskType.CURRICULUM_DESIGN)
        assert tier == ModelTier.STRONG

    def test_override_routing(self) -> None:
        mock = MockProvider()
        router = ModelRouter(providers={ModelTier.CHEAP: mock})
        router.override_routing(TaskType.CONTENT_GENERATION, ModelTier.CHEAP)
        _, tier = router.get_provider(TaskType.CONTENT_GENERATION)
        assert tier == ModelTier.CHEAP

    def test_missing_provider_raises(self) -> None:
        router = ModelRouter(providers={})
        with pytest.raises(ValueError, match="No provider registered"):
            router.get_provider(TaskType.METADATA)

    def test_register_provider(self) -> None:
        router = ModelRouter()
        mock = MockProvider()
        router.register_provider(ModelTier.MEDIUM, mock)
        provider, tier = router.get_provider(TaskType.CONTENT_GENERATION)
        assert tier == ModelTier.MEDIUM


# ---------------------------------------------------------------------------
# Tests: PromptRegistry
# ---------------------------------------------------------------------------


class TestPromptRegistry:
    def test_register_and_get(self) -> None:
        registry = PromptRegistry()
        template = PromptTemplate(
            name="test_prompt",
            version="1.0",
            system_prompt="You are a test.",
            user_prompt_template="Answer {question}",
        )
        registry.register(template)
        got = registry.get("test_prompt")
        assert got.version == "1.0"

    def test_get_specific_version(self) -> None:
        registry = PromptRegistry()
        registry.register(
            PromptTemplate(
                name="test",
                version="1.0",
                system_prompt="sys1",
                user_prompt_template="v1",
            )
        )
        registry.register(
            PromptTemplate(
                name="test",
                version="2.0",
                system_prompt="sys2",
                user_prompt_template="v2",
            )
        )
        v1 = registry.get("test", version="1.0")
        v2 = registry.get("test", version="2.0")
        assert v1.user_prompt_template == "v1"
        assert v2.user_prompt_template == "v2"

    def test_missing_prompt_raises(self) -> None:
        registry = PromptRegistry()
        with pytest.raises(KeyError, match="No prompt registered"):
            registry.get("nonexistent")

    def test_list_prompts(self) -> None:
        registry = PromptRegistry()
        registry.register(
            PromptTemplate(name="alpha", version="1.0", system_prompt="", user_prompt_template="")
        )
        registry.register(
            PromptTemplate(name="beta", version="1.0", system_prompt="", user_prompt_template="")
        )
        assert registry.list_prompts() == ["alpha", "beta"]


class TestDeterministicMockModelGuards:
    """The offline model refuses schemas it has no deterministic reply for with
    a typed ``WorkflowError``, so the run loop reports it instead of crashing."""

    async def test_unknown_schema_raises_workflow_error(self) -> None:
        from pydantic import BaseModel

        from lpf.errors import WorkflowError
        from lpf.orchestration.model import DeterministicMockModel

        class NeverAskedFor(BaseModel):
            value: int

        model = DeterministicMockModel()
        with pytest.raises(WorkflowError) as excinfo:
            await model.generate(
                messages=[{"role": "user", "content": "anything"}], schema=NeverAskedFor
            )
        assert excinfo.value.code == "UNSUPPORTED_SCHEMA"

    def test_render_user(self) -> None:
        template = PromptTemplate(
            name="test",
            version="1.0",
            system_prompt="sys",
            user_prompt_template="Solve {problem} for {variable}",
        )
        rendered = template.render_user(problem="2x+3=7", variable="x")
        assert "2x+3=7" in rendered
        assert "x" in rendered
