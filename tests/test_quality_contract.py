"""Phase D contract-honesty tests (TASK-015).

The audit found several ProductSpec fields that looked load-bearing but did
nothing. These tests pin the fix: a spec's ``quality.minimum_score`` and
``quality.required_gates`` are enforced by the QA stage, and
``constraints.evidence_required`` decides whether a run with no supported
evidence fails or merely warns. A run only stays green if it genuinely honours
what the spec declared.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from lpf.domain.identity import with_content_hash
from lpf.domain.product import ConstraintsSpec, QualitySpec
from lpf.orchestration import pipeline as pipeline_module
from lpf.orchestration.discovery_stage import SpecificationBundle
from lpf.orchestration.gates import MINIMUM_SCORE, REQUIRED_GATES_PRESENT, RESEARCH_EVIDENCE
from lpf.orchestration.pipeline import FactoryPipeline, FactoryRunResult
from lpf.schemas.discovery import DiscoveryInputs


def _inputs() -> DiscoveryInputs:
    return DiscoveryInputs(
        request="Teach me linear algebra basics.",
        subject="linear algebra",
        level="year 10",
    )


def _patch_spec(
    monkeypatch: pytest.MonkeyPatch,
    *,
    quality: QualitySpec | None = None,
    constraints: ConstraintsSpec | None = None,
) -> None:
    """Replace the spec the pipeline builds, keeping everything else identical."""
    real = pipeline_module.build_specification

    def wrapper(ctx, inputs, discovery):  # type: ignore[no-untyped-def]
        bundle = real(ctx, inputs, discovery)
        updates: dict[str, object] = {}
        if quality is not None:
            updates["quality"] = quality
        if constraints is not None:
            updates["constraints"] = constraints
        spec = with_content_hash(bundle.spec.model_copy(update=updates))
        return SpecificationBundle(spec=spec)

    monkeypatch.setattr(pipeline_module, "build_specification", wrapper)


def _patch_zero_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the research stage report an evidence map with nothing supported."""
    real = pipeline_module.build_research

    async def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        bundle = await real(*args, **kwargs)
        empty = with_content_hash(
            bundle.evidence_map.model_copy(
                update={
                    "claims": [],
                    "total_claims": 0,
                    "supported_claims": 0,
                    "conflicting_claims": 0,
                }
            )
        )
        return dataclasses.replace(bundle, evidence_map=empty)

    monkeypatch.setattr(pipeline_module, "build_research", wrapper)


def _gate(result: FactoryRunResult, name: str):  # type: ignore[no-untyped-def]
    assert result.verification is not None
    return next(gate for gate in result.verification.gates if gate.gate_name == name)


class TestMinimumScore:
    async def test_a_default_run_passes_the_declared_floor(self, tmp_path: Path) -> None:
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(_inputs(), run_id="floor")
        gate = _gate(result, MINIMUM_SCORE)
        assert result.succeeded
        assert gate.status.value == "passed"
        assert gate.score == 1.0

    async def test_a_floor_above_the_pass_rate_fails_the_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_zero_evidence(monkeypatch)
        _patch_spec(
            monkeypatch,
            quality=QualitySpec(minimum_score=1.0),
            constraints=ConstraintsSpec(evidence_required=False),
        )
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(_inputs(), run_id="floor-fail")
        assert not result.succeeded
        assert _gate(result, RESEARCH_EVIDENCE).status.value == "warning"
        failed = {
            gate.gate_name
            for gate in result.verification.gates  # type: ignore[union-attr]
            if gate.status.value == "failed"
        }
        assert failed == {MINIMUM_SCORE}

    async def test_a_low_floor_still_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_zero_evidence(monkeypatch)
        _patch_spec(
            monkeypatch,
            quality=QualitySpec(minimum_score=0.1),
            constraints=ConstraintsSpec(evidence_required=False),
        )
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(_inputs(), run_id="floor-low")
        assert result.succeeded
        assert _gate(result, MINIMUM_SCORE).status.value == "passed"


class TestSpecRequiredGates:
    async def test_a_spec_declared_gate_that_exists_passes(
        self, tmp_path: Path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        _patch_spec(monkeypatch, quality=QualitySpec(required_gates=["objective_references"]))
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(_inputs(), run_id="req-ok")
        assert result.succeeded
        assert _gate(result, REQUIRED_GATES_PRESENT).status.value == "passed"

    async def test_a_spec_declared_gate_that_never_runs_fails_the_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_spec(monkeypatch, quality=QualitySpec(required_gates=["a_gate_that_never_runs"]))
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(_inputs(), run_id="req-miss")
        assert not result.succeeded
        gate = _gate(result, REQUIRED_GATES_PRESENT)
        assert gate.status.value == "failed"
        assert "a_gate_that_never_runs" in gate.findings[0].evidence  # type: ignore[arg-type]

    async def test_a_default_spec_declares_no_gate(self, tmp_path: Path) -> None:
        """The old default named a gate (``schema_validity``) that no longer exists."""
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(_inputs(), run_id="req-none")
        names = {gate.gate_name for gate in result.verification.gates}  # type: ignore[union-attr]
        assert REQUIRED_GATES_PRESENT not in names


class TestEvidenceRequired:
    async def test_zero_evidence_fails_when_required(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_zero_evidence(monkeypatch)
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(_inputs(), run_id="ev-req")
        assert not result.succeeded
        assert _gate(result, RESEARCH_EVIDENCE).status.value == "failed"
        assert result.state.failure_reason is not None
        assert "QA" in result.state.failure_reason
        assert result.package is None

    async def test_zero_evidence_only_warns_when_not_required(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_zero_evidence(monkeypatch)
        _patch_spec(monkeypatch, constraints=ConstraintsSpec(evidence_required=False))
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(_inputs(), run_id="ev-warn")
        assert result.succeeded
        assert _gate(result, RESEARCH_EVIDENCE).status.value == "warning"
        assert result.verification.overall_status.value == "warning"  # type: ignore[union-attr]
