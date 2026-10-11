"""Failure-path tests for the pipeline.

Two failure kinds must behave differently and predictably:
expected domain failures (``LpfError``) become a failed run value, while
unexpected exceptions propagate so a real bug is never hidden as a product.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lpf.errors import ConfigError, RenderingError, ValidationError
from lpf.orchestration import pipeline as pipeline_module
from lpf.orchestration.pipeline import FactoryPipeline
from lpf.orchestration.state import RunStage
from lpf.schemas.discovery import DiscoveryInputs


def _inputs() -> DiscoveryInputs:
    return DiscoveryInputs(
        request="Teach me linear algebra basics.",
        subject="linear algebra",
        level="year 10",
    )


class TestRunIdValidation:
    """A run id becomes a path, so the pipeline boundary must reject traversal.

    Enforced at ``run`` so a programmatic caller is covered too, not just the CLI.
    """

    @pytest.mark.parametrize("run_id", ["../outside", "..\\..\\evil", "a/b", "a\\b", "..", ""])
    async def test_traversal_ids_are_rejected_before_any_write(
        self, tmp_path: Path, run_id: str
    ) -> None:
        out = tmp_path / "out"
        pipeline = FactoryPipeline(output_dir=str(out))
        with pytest.raises(ConfigError) as excinfo:
            await pipeline.run(_inputs(), run_id=run_id)
        assert excinfo.value.code == "INVALID_RUN_ID"
        assert not out.exists()

    async def test_ordinary_ids_are_accepted(self, tmp_path: Path) -> None:
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(_inputs(), run_id="ok-run.1")
        assert result.run_id == "ok-run.1"

    async def test_over_long_ids_are_rejected(self, tmp_path: Path) -> None:
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        with pytest.raises(ConfigError):
            await pipeline.run(_inputs(), run_id="x" * 65)


class TestQaFailure:
    async def test_missing_required_gate_fails_the_run_before_packaging(
        self, tmp_path: Path
    ) -> None:
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(
            _inputs(),
            run_id="qa-fail",
            required_gates=["a_gate_that_never_runs"],
        )
        assert not result.succeeded
        assert result.state.stage is RunStage.FAILED
        assert result.package is None
        assert result.state.failure_reason is not None
        assert "QA" in result.state.failure_reason
        assert result.verification is not None
        assert result.verification.overall_status.value == "failed"
        assert not (tmp_path / "qa-fail").exists()

    async def test_run_log_ends_with_failure(self, tmp_path: Path) -> None:
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(
            _inputs(), run_id="qa-fail", required_gates=["a_gate_that_never_runs"]
        )
        assert result.events.events[-1].event_type.value == "run_failed"


class TestDomainFailure:
    async def test_lpf_error_is_returned_as_a_failed_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(*args: object, **kwargs: object) -> None:
            raise ValidationError(code="NO_CONTENT", message="content stage refused to run")

        monkeypatch.setattr(pipeline_module, "build_content", boom)
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(_inputs(), run_id="domain-fail")

        assert not result.succeeded
        assert result.state.stage is RunStage.FAILED
        assert result.package is None
        assert result.state.failure_reason is not None
        assert "NO_CONTENT" in result.state.failure_reason

    async def test_artifacts_from_earlier_stages_are_retained(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(*args: object, **kwargs: object) -> None:
            raise ValidationError(code="NO_CONTENT", message="stop at content")

        monkeypatch.setattr(pipeline_module, "build_content", boom)
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(_inputs(), run_id="partial")

        types = {artifact.artifact_type for artifact in result.artifacts}
        assert "learner_profile" in types
        assert "research_report" in types
        assert "curriculum_blueprint" in types
        assert "lesson" not in types


class TestUnexpectedFailure:
    async def test_unexpected_exception_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("a genuine bug")

        monkeypatch.setattr(pipeline_module, "build_content", boom)
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        with pytest.raises(RuntimeError, match="a genuine bug"):
            await pipeline.run(_inputs(), run_id="crash")


class TestStructuredReplyFailure:
    """A model that returns text for a schema'd request was a raw ``ValueError``
    escape (CLI traceback, no failed run). It must surface as a failed run via a
    typed ``ProviderError``."""

    class _TextModel:
        async def generate(self, *, messages, schema=None, **kwargs) -> str:
            return "plain text" if schema is None else "text when a draft was expected"

        async def count_tokens(self, text: str) -> int:
            return len(text.split())

    async def test_text_reply_for_structured_call_fails_the_run(self, tmp_path: Path) -> None:
        pipeline = FactoryPipeline(output_dir=str(tmp_path), model=self._TextModel())
        result = await pipeline.run(_inputs(), run_id="text-model")
        assert not result.succeeded
        assert result.state.stage is RunStage.FAILED
        assert result.state.failure_reason is not None
        assert "STRUCTURED_REPLY_REQUIRED" in result.state.failure_reason
        assert result.events.events[-1].event_type.value == "run_failed"


class TestPackagingFailure:
    async def test_packaging_failure_after_completion_does_not_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            raise RenderingError(code="RENDER_DISK", message="disk full")

        monkeypatch.setattr(pipeline_module, "package_run", boom)
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(_inputs(), run_id="package-fail")

        # The machine reached COMPLETE before packaging, so there is no FAILED
        # edge to take. The handler must not crash (previously WorkflowError
        # escaped); the failure is recorded and nothing is written.
        assert result.succeeded
        assert result.package is None
        assert result.state.failure_reason is not None
        assert "RENDER_DISK" in result.state.failure_reason
        assert result.events.events[-1].event_type.value == "run_completed"
