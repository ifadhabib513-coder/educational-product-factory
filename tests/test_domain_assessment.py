"""Tests for domain schemas — assessment models (Stage 2b-ii)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lpf.domain.assessment import (
    Answer,
    AnswerFormat,
    AnswerKey,
    Assessment,
    AssessmentType,
    Rubric,
    RubricCriterion,
    RubricLevel,
)
from lpf.domain.content import SolutionStep
from lpf.domain.identity import compute_content_hash, with_content_hash

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_answer(question_id: str = "q1") -> Answer:
    return with_content_hash(
        Answer(
            question_id=question_id,
            correct_answer="Newton",
            answer_format=AnswerFormat.EXACT,
            solution_steps=[
                SolutionStep(order=1, statement="Identify unit", expression="N"),
            ],
        )
    )


def _make_rubric(question_id: str = "q1") -> Rubric:
    return with_content_hash(
        Rubric(
            question_id=question_id,
            criteria=[
                RubricCriterion(
                    criterion="Correctness",
                    max_points=5.0,
                    levels=[
                        RubricLevel(label="excellent", points=5.0, description="Fully correct"),
                        RubricLevel(label="good", points=3.0, description="Mostly correct"),
                        RubricLevel(label="poor", points=0.0, description="Incorrect"),
                    ],
                ),
            ],
            total_points=5.0,
        )
    )


def _make_assessment() -> Assessment:
    return with_content_hash(
        Assessment(
            assessment_type=AssessmentType.FORMATIVE,
            title="Quiz 1",
            question_ids=["q1", "q2", "q3"],
            total_points=10.0,
            time_limit_minutes=30,
        )
    )


def _make_answer_key(assessment: Assessment) -> AnswerKey:
    return with_content_hash(
        AnswerKey(
            assessment_id=assessment.id,
            answers=[
                _make_answer("q1"),
                with_content_hash(
                    Answer(
                        question_id="q2",
                        correct_answer="42",
                        answer_format=AnswerFormat.NUMERIC,
                    )
                ),
            ],
            total_points=10.0,
        )
    )


# ---------------------------------------------------------------------------
# Tests: AnswerFormat enum
# ---------------------------------------------------------------------------


class TestAnswerFormat:
    def test_all_values(self) -> None:
        values = [af.value for af in AnswerFormat]
        assert "exact" in values
        assert "numeric" in values
        assert "range" in values
        assert "rubric" in values
        assert "explanation" in values

    def test_count(self) -> None:
        assert len(AnswerFormat) == 5


# ---------------------------------------------------------------------------
# Tests: AssessmentType enum
# ---------------------------------------------------------------------------


class TestAssessmentType:
    def test_all_values(self) -> None:
        values = [at.value for at in AssessmentType]
        assert "diagnostic" in values
        assert "formative" in values
        assert "summative" in values
        assert "challenge" in values

    def test_count(self) -> None:
        assert len(AssessmentType) == 4


# ---------------------------------------------------------------------------
# Tests: RubricLevel
# ---------------------------------------------------------------------------


class TestRubricLevel:
    def test_construction(self) -> None:
        level = RubricLevel(label="excellent", points=5.0, description="Perfect")
        assert level.label == "excellent"
        assert level.points == 5.0

    def test_frozen(self) -> None:
        level = RubricLevel(label="good", points=3.0, description="OK")
        with pytest.raises(ValidationError, match="frozen"):
            level.label = "bad"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: RubricCriterion
# ---------------------------------------------------------------------------


class TestRubricCriterion:
    def test_construction(self) -> None:
        criterion = RubricCriterion(
            criterion="Clarity",
            max_points=5.0,
            levels=[
                RubricLevel(label="excellent", points=5.0, description="Clear"),
                RubricLevel(label="poor", points=0.0, description="Unclear"),
            ],
        )
        assert criterion.criterion == "Clarity"
        assert len(criterion.levels) == 2

    def test_empty_levels_raises(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            RubricCriterion(
                criterion="Bad",
                max_points=5.0,
                levels=[],
            )

    def test_single_level_raises(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            RubricCriterion(
                criterion="Bad",
                max_points=5.0,
                levels=[RubricLevel(label="only", points=5.0, description="Only one")],
            )


# ---------------------------------------------------------------------------
# Tests: Answer
# ---------------------------------------------------------------------------


class TestAnswer:
    def test_construction(self) -> None:
        a = _make_answer()
        assert a.artifact_type == "answer"
        assert a.correct_answer == "Newton"
        assert a.answer_format == AnswerFormat.EXACT
        assert len(a.solution_steps) == 1

    def test_defaults(self) -> None:
        a = Answer(
            question_id="q1",
            correct_answer="42",
            answer_format=AnswerFormat.NUMERIC,
        )
        assert a.solution_steps == []
        assert a.rubric_id is None

    def test_frozen(self) -> None:
        a = _make_answer()
        with pytest.raises(ValidationError, match="frozen"):
            a.correct_answer = "wrong"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        a1 = _make_answer()
        h1 = compute_content_hash(a1)
        data = a1.model_dump(mode="json")
        a2 = Answer.model_validate(data)
        h2 = compute_content_hash(a2)
        assert h1 == h2


# ---------------------------------------------------------------------------
# Tests: AnswerKey
# ---------------------------------------------------------------------------


class TestAnswerKey:
    def test_construction(self) -> None:
        assessment = _make_assessment()
        ak = _make_answer_key(assessment)
        assert ak.artifact_type == "answer_key"
        assert ak.assessment_id == assessment.id
        assert len(ak.answers) == 2
        assert ak.total_points == 10.0

    def test_empty_answers_raises(self) -> None:
        assessment = _make_assessment()
        with pytest.raises(ValidationError, match="too_short"):
            AnswerKey(
                assessment_id=assessment.id,
                answers=[],
                total_points=10.0,
            )

    def test_json_roundtrip(self) -> None:
        assessment = _make_assessment()
        ak1 = _make_answer_key(assessment)
        h1 = compute_content_hash(ak1)
        data = ak1.model_dump(mode="json")
        ak2 = AnswerKey.model_validate(data)
        h2 = compute_content_hash(ak2)
        assert h1 == h2


# ---------------------------------------------------------------------------
# Tests: Rubric
# ---------------------------------------------------------------------------


class TestRubric:
    def test_construction(self) -> None:
        r = _make_rubric()
        assert r.artifact_type == "rubric"
        assert r.question_id == "q1"
        assert len(r.criteria) == 1
        assert r.total_points == 5.0

    def test_empty_criteria_raises(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            Rubric(
                question_id="q1",
                criteria=[],
                total_points=5.0,
            )

    def test_json_roundtrip(self) -> None:
        r1 = _make_rubric()
        h1 = compute_content_hash(r1)
        data = r1.model_dump(mode="json")
        r2 = Rubric.model_validate(data)
        h2 = compute_content_hash(r2)
        assert h1 == h2


# ---------------------------------------------------------------------------
# Tests: Assessment
# ---------------------------------------------------------------------------


class TestAssessment:
    def test_construction(self) -> None:
        a = _make_assessment()
        assert a.artifact_type == "assessment"
        assert a.assessment_type == AssessmentType.FORMATIVE
        assert a.title == "Quiz 1"
        assert len(a.question_ids) == 3
        assert a.time_limit_minutes == 30

    def test_defaults(self) -> None:
        a = Assessment(
            assessment_type=AssessmentType.SUMMATIVE,
            title="Final Exam",
            question_ids=["q1"],
            total_points=100.0,
        )
        assert a.time_limit_minutes is None

    def test_empty_question_ids_raises(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            Assessment(
                assessment_type=AssessmentType.DIAGNOSTIC,
                title="Empty",
                question_ids=[],
                total_points=0.0,
            )

    def test_frozen(self) -> None:
        a = _make_assessment()
        with pytest.raises(ValidationError, match="frozen"):
            a.title = "New title"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        a1 = _make_assessment()
        h1 = compute_content_hash(a1)
        data = a1.model_dump(mode="json")
        a2 = Assessment.model_validate(data)
        h2 = compute_content_hash(a2)
        assert h1 == h2
