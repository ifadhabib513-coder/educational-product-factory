"""Tests for domain schemas — content models (Stage 2b-i)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lpf.domain.content import SolutionStep, SourceRef
from lpf.domain.evidence import EvidenceKind, EvidenceRecord
from lpf.domain.identity import compute_content_hash, with_content_hash
from lpf.domain.learner import LearnerProfile
from lpf.domain.lesson import Lesson
from lpf.domain.misconception import Misconception, MisconceptionSeverity
from lpf.domain.objectives import LearningObjective
from lpf.domain.validation import check_misconception_objective_refs
from lpf.domain.worked_example import WorkedExample

# ---------------------------------------------------------------------------
# Helpers: build a full content plan
# ---------------------------------------------------------------------------


def _make_profile() -> LearnerProfile:
    return with_content_hash(
        LearnerProfile(subject="Physics", level="high-school", goals=["Understand motion"])
    )


def _make_objectives() -> list[LearningObjective]:
    return [
        with_content_hash(LearningObjective(statement="Define velocity")),
        with_content_hash(LearningObjective(statement="Calculate acceleration")),
    ]


def _make_lesson(objs: list[LearningObjective]) -> Lesson:
    return with_content_hash(
        Lesson(
            title="Velocity Basics",
            unit_id="u1",
            objective_ids=[objs[0].id, objs[1].id],
            body_markdown="## Velocity\nVelocity is the rate of change of position.",
        )
    )


def _make_worked_example(lesson: Lesson) -> WorkedExample:
    return with_content_hash(
        WorkedExample(
            title="Calculate Velocity",
            lesson_id=lesson.id,
            problem_statement="A car travels 100m in 5s. Find its velocity.",
            solution_steps=[
                SolutionStep(order=1, statement="Identify given values", expression="d=100m, t=5s"),
                SolutionStep(order=2, statement="Apply formula", expression="v = d/t"),
                SolutionStep(order=3, statement="Compute", expression="v = 100/5 = 20 m/s"),
            ],
            final_answer="20 m/s",
            common_errors=["Forgetting units"],
        )
    )


def _make_misconception(objs: list[LearningObjective]) -> Misconception:
    return with_content_hash(
        Misconception(
            statement="Heavier objects fall faster",
            correction="All objects accelerate equally under gravity",
            objective_ids=[objs[0].id],
            severity=MisconceptionSeverity.COMMON,
        )
    )


def _make_evidence() -> EvidenceRecord:
    return with_content_hash(
        EvidenceRecord(
            claim="Velocity equals displacement divided by time",
            evidence_kind=EvidenceKind.DIRECT_SOURCE,
            source=SourceRef(source_type="book", identifier="Halliday & Resnick"),
        )
    )


# ---------------------------------------------------------------------------
# Tests: Lesson
# ---------------------------------------------------------------------------


class TestLesson:
    def test_construction(self) -> None:
        objs = _make_objectives()
        lesson = _make_lesson(objs)
        assert lesson.artifact_type == "lesson"
        assert lesson.title == "Velocity Basics"
        assert len(lesson.objective_ids) == 2

    def test_empty_objective_ids_raises(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            Lesson(
                title="Bad",
                unit_id="u1",
                objective_ids=[],
                body_markdown="empty",
            )

    def test_unknown_field_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            Lesson(
                title="X",
                unit_id="u1",
                objective_ids=["o1"],
                body_markdown="x",
                bogus_field="nope",  # type: ignore[call-arg]
            )


# ---------------------------------------------------------------------------
# Tests: WorkedExample
# ---------------------------------------------------------------------------


class TestWorkedExample:
    def test_construction(self) -> None:
        lesson = _make_lesson(_make_objectives())
        we = _make_worked_example(lesson)
        assert we.artifact_type == "worked_example"
        assert len(we.solution_steps) == 3
        assert we.final_answer == "20 m/s"

    def test_empty_solution_steps_raises(self) -> None:
        lesson = _make_lesson(_make_objectives())
        with pytest.raises(ValidationError, match="too_short"):
            WorkedExample(
                title="Empty",
                lesson_id=lesson.id,
                problem_statement="x",
                solution_steps=[],
                final_answer="?",
            )

    def test_missing_lesson_id_field(self) -> None:
        with pytest.raises(ValidationError, match="Field required"):
            WorkedExample(
                title="No lesson",
                problem_statement="x",
                solution_steps=[SolutionStep(order=1, statement="step")],
                final_answer="?",
            )


# ---------------------------------------------------------------------------
# Tests: Misconception
# ---------------------------------------------------------------------------


class TestMisconception:
    def test_construction(self) -> None:
        objs = _make_objectives()
        m = _make_misconception(objs)
        assert m.artifact_type == "misconception"
        assert m.severity == MisconceptionSeverity.COMMON

    def test_empty_objective_ids_raises(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            Misconception(
                statement="wrong",
                correction="right",
                objective_ids=[],
            )


# ---------------------------------------------------------------------------
# Tests: EvidenceRecord
# ---------------------------------------------------------------------------


class TestEvidenceRecord:
    def test_direct_source_with_source(self) -> None:
        e = _make_evidence()
        assert e.evidence_kind == EvidenceKind.DIRECT_SOURCE
        assert e.source is not None

    def test_direct_source_without_source_raises(self) -> None:
        with pytest.raises(ValidationError, match="direct_source.*requires a source"):
            EvidenceRecord(
                claim="Test claim",
                evidence_kind=EvidenceKind.DIRECT_SOURCE,
            )

    def test_model_generated_without_source_ok(self) -> None:
        e = with_content_hash(
            EvidenceRecord(
                claim="LLM explanation",
                evidence_kind=EvidenceKind.MODEL_GENERATED,
            )
        )
        assert e.evidence_kind == EvidenceKind.MODEL_GENERATED
        assert e.source is None

    def test_default_verification_status(self) -> None:
        e = _make_evidence()
        assert e.verification_status == "unverified"


# ---------------------------------------------------------------------------
# Tests: check_misconception_objective_refs
# ---------------------------------------------------------------------------


class TestCheckMisconceptionObjectiveRefs:
    def test_ok_path(self) -> None:
        objs = _make_objectives()
        m = _make_misconception(objs)
        result = check_misconception_objective_refs([m], {o.id for o in objs})
        from lpf.result import is_ok

        assert is_ok(result)

    def test_err_path_missing_id(self) -> None:
        objs = _make_objectives()
        m = _make_misconception(objs)
        # Provide only a bogus ID set
        result = check_misconception_objective_refs([m], {"bogus_id"})
        from lpf.result import is_err

        assert is_err(result)
        error = result.error  # type: ignore[union-attr]
        assert error.code == "MISSING_OBJECTIVE_REFS"
        assert "missing" in error.details
        assert any(item["objective_id"] == objs[0].id for item in error.details["missing"])


# ---------------------------------------------------------------------------
# Tests: JSON round-trip hash stability
# ---------------------------------------------------------------------------


class TestJsonRoundTrip:
    def test_evidence_record_hash_stability(self) -> None:
        e1 = _make_evidence()
        h1 = compute_content_hash(e1)
        data = e1.model_dump(mode="json")
        e2 = EvidenceRecord.model_validate(data)
        h2 = compute_content_hash(e2)
        assert h1 == h2

    def test_lesson_hash_stability(self) -> None:
        objs = _make_objectives()
        l1 = _make_lesson(objs)
        h1 = compute_content_hash(l1)
        data = l1.model_dump(mode="json")
        l2 = Lesson.model_validate(data)
        h2 = compute_content_hash(l2)
        assert h1 == h2


# ---------------------------------------------------------------------------
# Tests: Full content plan
# ---------------------------------------------------------------------------


class TestFullContentPlan:
    def test_coherent_plan(self) -> None:
        objs = _make_objectives()
        lesson = _make_lesson(objs)
        we = _make_worked_example(lesson)
        m = _make_misconception(objs)
        evidence = _make_evidence()

        # Cross-references are consistent
        assert we.lesson_id == lesson.id
        assert m.objective_ids[0] == objs[0].id
        assert lesson.objective_ids[0] == objs[0].id
        assert evidence.evidence_kind == EvidenceKind.DIRECT_SOURCE
        assert evidence.source is not None
