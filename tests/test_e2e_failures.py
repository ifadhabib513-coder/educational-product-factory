"""Failure-path tests for the pipeline.

Two failure kinds must behave differently and predictably:
expected domain failures (``LpfError``) become a failed run value, while
unexpected exceptions propagate so a real bug is never hidden as a product.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lpf.errors import ValidationError
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
