"""Tests for domain schemas — practice models (Stage 2b-ii)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lpf.domain.identity import compute_content_hash, with_content_hash
from lpf.domain.practice import (
    DifficultyLevel,
    Hint,
    PracticeQuestion,
    QuestionType,
    ScaffoldingType,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_question() -> PracticeQuestion:
    return with_content_hash(
        PracticeQuestion(
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=DifficultyLevel.INTERMEDIATE,
            lesson_id="lesson_001",
            objective_ids=["obj_001", "obj_002"],
            stem="What is the SI unit of force?",
            choices=["Newton", "Joule", "Watt", "Pascal"],
            hints=["Think about F = ma"],
            estimated_time_seconds=60,
        )
    )


def _make_hint(question: PracticeQuestion) -> Hint:
    return with_content_hash(
        Hint(
            question_id=question.id,
            order=1,
            text="Recall Newton's second law: F = ma",
            scaffolding_type=ScaffoldingType.CONCEPTUAL,
        )
    )


# ---------------------------------------------------------------------------
# Tests: QuestionType enum
# ---------------------------------------------------------------------------


class TestQuestionType:
    def test_all_values(self) -> None:
        values = [qt.value for qt in QuestionType]
        assert "multiple_choice" in values
        assert "short_answer" in values
        assert "true_false" in values
        assert "numerical" in values
        assert "proof" in values
        assert "explanation" in values
        assert "matching" in values
        assert "ordering" in values
        assert "fill_blank" in values

    def test_count(self) -> None:
        assert len(QuestionType) == 9


# ---------------------------------------------------------------------------
# Tests: DifficultyLevel enum
# ---------------------------------------------------------------------------


class TestDifficultyLevel:
    def test_all_values(self) -> None:
        values = [dl.value for dl in DifficultyLevel]
        assert "beginner" in values
        assert "intermediate" in values
        assert "advanced" in values
        assert "challenge" in values

    def test_count(self) -> None:
        assert len(DifficultyLevel) == 4


# ---------------------------------------------------------------------------
# Tests: ScaffoldingType enum
# ---------------------------------------------------------------------------


class TestScaffoldingType:
    def test_all_values(self) -> None:
        values = [st.value for st in ScaffoldingType]
        assert "nudge" in values
        assert "conceptual" in values
        assert "procedural" in values
        assert "worked_partial" in values

    def test_count(self) -> None:
        assert len(ScaffoldingType) == 4


# ---------------------------------------------------------------------------
# Tests: PracticeQuestion
# ---------------------------------------------------------------------------


class TestPracticeQuestion:
    def test_construction(self) -> None:
        q = _make_question()
        assert q.artifact_type == "practice_question"
        assert q.question_type == QuestionType.MULTIPLE_CHOICE
        assert q.difficulty == DifficultyLevel.INTERMEDIATE
        assert q.lesson_id == "lesson_001"
        assert len(q.objective_ids) == 2
        assert len(q.choices) == 4

    def test_defaults(self) -> None:
        q = PracticeQuestion(
            question_type=QuestionType.SHORT_ANSWER,
            difficulty=DifficultyLevel.BEGINNER,
            lesson_id="l1",
            objective_ids=["o1"],
            stem="Explain something",
        )
        assert q.choices is None
        assert q.hints == []
        assert q.common_misconceptions == []
        assert q.estimated_time_seconds is None

    def test_empty_objective_ids_raises(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            PracticeQuestion(
                question_type=QuestionType.NUMERICAL,
                difficulty=DifficultyLevel.ADVANCED,
                lesson_id="l1",
                objective_ids=[],
                stem="Calculate x",
            )

    def test_unknown_field_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            PracticeQuestion(
                question_type=QuestionType.TRUE_FALSE,
                difficulty=DifficultyLevel.BEGINNER,
                lesson_id="l1",
                objective_ids=["o1"],
                stem="True or false?",
                bogus_field="nope",  # type: ignore[call-arg]
            )

    def test_frozen(self) -> None:
        q = _make_question()
        with pytest.raises(ValidationError, match="frozen"):
            q.stem = "New stem"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        q1 = _make_question()
        h1 = compute_content_hash(q1)
        data = q1.model_dump(mode="json")
        q2 = PracticeQuestion.model_validate(data)
        h2 = compute_content_hash(q2)
        assert h1 == h2


# ---------------------------------------------------------------------------
# Tests: Hint
# ---------------------------------------------------------------------------


class TestHint:
    def test_construction(self) -> None:
        q = _make_question()
        h = _make_hint(q)
        assert h.artifact_type == "hint"
        assert h.question_id == q.id
        assert h.order == 1
        assert h.scaffolding_type == ScaffoldingType.CONCEPTUAL

    def test_frozen(self) -> None:
        q = _make_question()
        h = _make_hint(q)
        with pytest.raises(ValidationError, match="frozen"):
            h.order = 2  # type: ignore[misc]

    def test_unknown_field_forbidden(self) -> None:
        q = _make_question()
        with pytest.raises(ValidationError, match="extra"):
            Hint(
                question_id=q.id,
                order=1,
                text="hint",
                scaffolding_type=ScaffoldingType.NUDGE,
                bogus_field="nope",  # type: ignore[call-arg]
            )

    def test_json_roundtrip(self) -> None:
        q = _make_question()
        h1 = _make_hint(q)
        h1 = with_content_hash(h1)
        h1_data = h1.model_dump(mode="json")
        h2 = Hint.model_validate(h1_data)
        assert compute_content_hash(h1) == compute_content_hash(h2)
