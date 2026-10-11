"""Tests for model provider and router."""

from __future__ import annotations

import pytest

from lpf.models.provider import (
    MockProvider,
    ModelRouter,
    ModelTier,
    TaskType,
)

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
# Tests: DeterministicMockModel guards
# ---------------------------------------------------------------------------


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
