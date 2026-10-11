"""Tests for the bounded QA revision loop (TASK-006).

The stage machine is allowed exactly one kind of cycle: QA rewinding to the
stage that produced a failing artifact. Three outcomes have to be right - a
repair that converges, a budget that runs out, and a failure with nowhere to
go - plus the invariant that a revised run is still reproducible, because a
loop that varies between runs would break the byte-identical guarantee.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from lpf.domain.identity import with_content_hash
from lpf.domain.quality import GateStatus
from lpf.orchestration import gates as gate_catalog
from lpf.orchestration import pipeline as pipeline_module
from lpf.orchestration.content_stage import ContentBundle
from lpf.orchestration.gates import REQUIRED_GATES_PRESENT
from lpf.orchestration.pipeline import FactoryPipeline, FactoryRunResult
from lpf.orchestration.qa_stage import QaBundle
from lpf.orchestration.revision import (
    ASSESSMENT_GATES,
    CONTENT_GATES,
    NON_REPAIRABLE_GATES,
    OWNED_GATES,
    route_failed_gates,
)
from lpf.orchestration.state import MAX_REVISIONS, RunStage
from lpf.schemas.discovery import DiscoveryInputs


def _inputs() -> DiscoveryInputs:
    return DiscoveryInputs(
        request="Teach me linear algebra basics.",
        subject="linear algebra",
        level="year 10",
    )


def _hops(result: FactoryRunResult) -> list[tuple[RunStage, RunStage]]:
    """Every accepted transition, as a (from, to) pair."""
    return [(t.from_stage, t.to_stage) for t in result.state.history]


def _visits(result: FactoryRunResult, stage: RunStage) -> int:
    """How many times the run entered ``stage``."""
    return sum(1 for transition in result.state.history if transition.to_stage is stage)


def _revision_events(result: FactoryRunResult) -> int:
    return sum(1 for event in result.events.events if event.event_type.value == "revision_started")


def _files(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _poison_misconception(bundle: ContentBundle) -> ContentBundle:
    """Return ``bundle`` with one misconception pointing at a bogus objective.

    A real, content-owned defect: the misconception gate reads misconceptions and
    nothing else, so re-running content is the only way to clear it.
    """
    broken = with_content_hash(
        bundle.misconceptions[0].model_copy(
            update={"objective_ids": ["objective-that-does-not-exist"]}
        )
    )
    return ContentBundle(
        lessons=bundle.lessons,
        worked_examples=bundle.worked_examples,
        misconceptions=(broken, *bundle.misconceptions[1:]),
    )


def _poison_first_pass(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Break only the first content build of a run; return its call counter."""
    real = pipeline_module.build_content
    calls = {"count": 0}

    async def wrapper(*args: object, **kwargs: object) -> ContentBundle:
        calls["count"] += 1
        bundle = await real(*args, **kwargs)
        if calls["count"] == 1 and bundle.misconceptions:
            return _poison_misconception(bundle)
        return bundle

    monkeypatch.setattr(pipeline_module, "build_content", wrapper)
    return calls


def _poison_every_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Break content on every pass, so the run can only end by exhausting."""
    real = pipeline_module.build_content

    async def wrapper(*args: object, **kwargs: object) -> ContentBundle:
        bundle = await real(*args, **kwargs)
        return _poison_misconception(bundle) if bundle.misconceptions else bundle

    monkeypatch.setattr(pipeline_module, "build_content", wrapper)


def _fail_gate(bundle: QaBundle, name: str) -> QaBundle:
    """Return ``bundle`` with gate ``name`` reported as FAILED."""
    gates = tuple(
        gate.model_copy(update={"status": GateStatus.FAILED, "score": 0.0})
        if gate.gate_name == name
        else gate
        for gate in bundle.gates
    )
    verification = bundle.verification.model_copy(
        update={"gates": list(gates), "overall_status": GateStatus.FAILED}
    )
    return QaBundle(gates=gates, verification=verification)


class TestRepairableFailure:
    async def test_content_defect_is_repaired_on_the_second_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _poison_first_pass(monkeypatch)
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(_inputs(), run_id="repaired")

        assert result.succeeded
        assert calls["count"] == 2
        assert result.state.stage is RunStage.COMPLETE
        assert result.state.revisions == 1
        assert (RunStage.QA, RunStage.CONTENT) in _hops(result)
        assert (RunStage.QA, RunStage.ASSESSMENT) not in _hops(result)
        assert _visits(result, RunStage.QA) == 2
        assert _revision_events(result) == 1

    async def test_the_successful_verification_is_the_second_iteration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _poison_first_pass(monkeypatch)
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(_inputs(), run_id="iteration")

        assert result.verification is not None
        assert result.verification.overall_status is not GateStatus.FAILED
        assert result.verification.iteration == 2
        assert result.verification.max_iterations == MAX_REVISIONS + 1

    async def test_superseded_artifacts_are_dropped_before_the_rebuild(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clean = await FactoryPipeline(output_dir=str(tmp_path / "clean")).run(
            _inputs(), run_id="mix"
        )
        _poison_first_pass(monkeypatch)
        repaired = await FactoryPipeline(output_dir=str(tmp_path / "repaired")).run(
            _inputs(), run_id="mix"
        )

        assert clean.succeeded and repaired.succeeded
        assert Counter(a.artifact_type for a in repaired.artifacts) == Counter(
            a.artifact_type for a in clean.artifacts
        )
        bogus = [
            artifact
            for artifact in repaired.artifacts
            if artifact.artifact_type == "misconception"
            and "objective-that-does-not-exist" in artifact.objective_ids  # type: ignore[attr-defined]
        ]
        assert bogus == []

    async def test_only_the_live_verification_is_shipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _poison_first_pass(monkeypatch)
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(
            _inputs(), run_id="one-verification"
        )

        assert result.succeeded
        verifications = [a for a in result.artifacts if a.artifact_type == "verification_result"]
        assert len(verifications) == 1
        ids = [artifact.id for artifact in result.artifacts]
        assert len(ids) == len(set(ids))


class TestAssessmentRouting:
    async def test_assessment_failure_revisits_assessment_alone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_content = pipeline_module.build_content
        real_qa = pipeline_module.build_qa
        content_calls = {"count": 0}
        qa_calls = {"count": 0}

        async def counting_content(*args: object, **kwargs: object) -> ContentBundle:
            content_calls["count"] += 1
            return await real_content(*args, **kwargs)

        def flaky_qa(*args: object, **kwargs: object) -> QaBundle:
            qa_calls["count"] += 1
            bundle = real_qa(*args, **kwargs)
            return _fail_gate(bundle, "answer_key_references") if qa_calls["count"] == 1 else bundle

        monkeypatch.setattr(pipeline_module, "build_content", counting_content)
        monkeypatch.setattr(pipeline_module, "build_qa", flaky_qa)

        result = await FactoryPipeline(output_dir=str(tmp_path)).run(
            _inputs(), run_id="assessment-only"
        )

        assert result.succeeded
        assert content_calls["count"] == 1
        assert qa_calls["count"] == 2
        assert result.state.revisions == 1
        assert (RunStage.QA, RunStage.ASSESSMENT) in _hops(result)
        assert (RunStage.QA, RunStage.CONTENT) not in _hops(result)
        assert _visits(result, RunStage.CONTENT) == 1
        assert _visits(result, RunStage.ASSESSMENT) == 2


class TestBoundedBudget:
    async def test_the_run_fails_once_the_budget_is_spent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _poison_every_pass(monkeypatch)
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(_inputs(), run_id="bounded")

        assert not result.succeeded
        assert result.state.stage is RunStage.FAILED
        assert result.state.revisions == MAX_REVISIONS
        assert result.state.revisions_exhausted
        assert result.state.failure_reason is not None
        assert "revision budget" in result.state.failure_reason
        assert result.package is None
        assert not (tmp_path / "bounded").exists()

    async def test_the_budget_bounds_how_often_qa_may_rewind(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _poison_every_pass(monkeypatch)
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(
            _inputs(), run_id="bounded-hops"
        )

        assert _hops(result).count((RunStage.QA, RunStage.CONTENT)) == MAX_REVISIONS
        assert _visits(result, RunStage.QA) == MAX_REVISIONS + 1
        assert _revision_events(result) == MAX_REVISIONS
        assert result.events.events[-1].event_type.value == "run_failed"


class TestUnrepairableFailure:
    async def test_a_gate_with_no_owner_aborts_before_any_revision(self, tmp_path: Path) -> None:
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(
            _inputs(),
            run_id="unrepairable",
            required_gates=["a_gate_that_never_runs"],
        )

        assert not result.succeeded
        assert result.state.revisions == 0
        assert result.state.failure_reason is not None
        assert "not repairable" in result.state.failure_reason
        assert _visits(result, RunStage.QA) == 1
        assert (RunStage.QA, RunStage.CONTENT) not in _hops(result)
        assert (RunStage.QA, RunStage.ASSESSMENT) not in _hops(result)
        assert _revision_events(result) == 0
        assert result.package is None


class TestRoutingTable:
    def test_every_owned_gate_routes_to_the_stage_that_made_it(self) -> None:
        for gate in CONTENT_GATES:
            assert route_failed_gates([gate]) is RunStage.CONTENT, gate
        for gate in ASSESSMENT_GATES:
            assert route_failed_gates([gate]) is RunStage.ASSESSMENT, gate

    def test_every_non_repairable_gate_aborts(self) -> None:
        for gate in NON_REPAIRABLE_GATES:
            assert route_failed_gates([gate]) is None, gate

    def test_named_non_repairable_gates_are_never_owned(self) -> None:
        assert NON_REPAIRABLE_GATES.isdisjoint(OWNED_GATES)

    def test_unknown_and_empty_failures_abort(self) -> None:
        assert route_failed_gates(["a_gate_nobody_owns"]) is None
        assert route_failed_gates([]) is None

    def test_one_non_repairable_gate_poisons_the_whole_failure_set(self) -> None:
        assert route_failed_gates(["factual_consistency", "research_evidence"]) is None

    def test_factual_consistency_is_unowned_because_its_inputs_are_research(self) -> None:
        assert route_failed_gates(["factual_consistency"]) is None

    def test_content_wins_over_assessment_in_a_mixed_failure(self) -> None:
        assert (
            route_failed_gates(["answer_references", "misconception_references"])
            is RunStage.CONTENT
        )

    def test_the_ownership_sets_do_not_overlap(self) -> None:
        assert not CONTENT_GATES & ASSESSMENT_GATES
        assert not CONTENT_GATES & NON_REPAIRABLE_GATES
        assert not ASSESSMENT_GATES & NON_REPAIRABLE_GATES

    def test_the_gate_catalog_matches_the_ownership_sets_exactly(self) -> None:
        owned = CONTENT_GATES | ASSESSMENT_GATES | NON_REPAIRABLE_GATES
        assert set(gate_catalog.ALL_GATES) == owned

    def test_every_catalog_gate_lives_in_exactly_one_ownership_set(self) -> None:
        for name in gate_catalog.ALL_GATES:
            membership = [
                name in CONTENT_GATES,
                name in ASSESSMENT_GATES,
                name in NON_REPAIRABLE_GATES,
            ]
            assert sum(membership) == 1, name


class TestGateCatalogSurface:
    """The QA stage emits exactly the gate catalog (TASK-013)."""

    async def test_a_default_run_emits_every_unconditional_catalog_gate(
        self, tmp_path: Path
    ) -> None:
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(_inputs(), run_id="gates")
        assert result.verification is not None
        emitted = {gate.gate_name for gate in result.verification.gates}
        unconditional = (CONTENT_GATES | ASSESSMENT_GATES | NON_REPAIRABLE_GATES) - {
            REQUIRED_GATES_PRESENT
        }
        assert emitted == unconditional
        assert emitted.issubset(set(gate_catalog.ALL_GATES))

    async def test_a_required_gates_run_emits_every_catalog_gate(self, tmp_path: Path) -> None:
        result = await FactoryPipeline(output_dir=str(tmp_path)).run(
            _inputs(), run_id="gates", required_gates=["objective_references"]
        )
        assert result.verification is not None
        emitted = {gate.gate_name for gate in result.verification.gates}
        assert REQUIRED_GATES_PRESENT in emitted
        assert emitted == set(gate_catalog.ALL_GATES)


class TestReproducibility:
    async def test_a_repaired_run_repeats_byte_identically(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _poison_first_pass(monkeypatch)
        first = await FactoryPipeline(output_dir=str(tmp_path / "a")).run(_inputs(), run_id="det")
        calls["count"] = 0
        second = await FactoryPipeline(output_dir=str(tmp_path / "b")).run(_inputs(), run_id="det")

        assert first.succeeded and second.succeeded
        assert first.state.revisions == second.state.revisions == 1
        left = {artifact.id: artifact.content_hash for artifact in first.artifacts}
        right = {artifact.id: artifact.content_hash for artifact in second.artifacts}
        assert left == right
        assert _files(first.package.root) == _files(second.package.root)  # type: ignore[union-attr]

    async def test_an_exhausted_run_repeats_identically(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _poison_every_pass(monkeypatch)
        first = await FactoryPipeline(output_dir=str(tmp_path / "a")).run(
            _inputs(), run_id="doomed"
        )
        second = await FactoryPipeline(output_dir=str(tmp_path / "b")).run(
            _inputs(), run_id="doomed"
        )

        assert not first.succeeded and not second.succeeded
        assert first.state.revisions == second.state.revisions
        assert first.state.failure_reason == second.state.failure_reason
        left = {artifact.id: artifact.content_hash for artifact in first.artifacts}
        right = {artifact.id: artifact.content_hash for artifact in second.artifacts}
        assert left == right
