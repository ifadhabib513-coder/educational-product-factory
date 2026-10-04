"""Assessment stage — builds practice questions, answers, and an answer key.

Question → answer → answer key must all point at the same ids, so the QA stage can
check referential integrity afterwards. Keeping the construction in one stage is
what makes that check meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass

from lpf.domain.assessment import (
    Answer,
    AnswerFormat,
    AnswerKey,
    Assessment,
    AssessmentType,
)
from lpf.domain.identity import with_content_hash
from lpf.domain.lesson import Lesson
from lpf.domain.practice import DifficultyLevel, PracticeQuestion, QuestionType
from lpf.orchestration.context import RunContext


@dataclass(frozen=True)
class AssessmentBundle:
    """Everything the Assessment stage produces."""

    questions: tuple[PracticeQuestion, ...]
    answers: tuple[Answer, ...]
    answer_key: AnswerKey
    assessment: Assessment


def build_assessment(
    ctx: RunContext,
    *,
    lessons: list[Lesson],
    title: str,
    points_per_question: float = 1.0,
) -> AssessmentBundle:
    """Build one question per lesson with a matching answer and a key."""
    if not lessons:
        raise ValueError("Assessment requires at least one lesson to build questions from.")

    questions = [
        with_content_hash(
            PracticeQuestion(
                id=ctx.id("question"),
                created_at=ctx.now(),
                parent_id=lesson.id,
                question_type=QuestionType.SHORT_ANSWER,
                difficulty=DifficultyLevel.BEGINNER,
                lesson_id=lesson.id,
                objective_ids=list(lesson.objective_ids),
                stem=f"In one or two sentences, explain: {lesson.title}.",
                hints=["Start from the definition, then give one example."],
                estimated_time_seconds=120,
                source_refs=[lesson.id],
            )
        )
        for lesson in lessons
    ]

    total_points = points_per_question * len(questions)

    assessment = with_content_hash(
        Assessment(
            id=ctx.id("assessment"),
            created_at=ctx.now(),
            assessment_type=AssessmentType.FORMATIVE,
            title=title,
            question_ids=[question.id for question in questions],
            total_points=total_points,
            source_refs=[lesson.id for lesson in lessons],
        )
    )

    answers = [
        with_content_hash(
            Answer(
                id=ctx.id("answer"),
                created_at=ctx.now(),
                parent_id=question.id,
                question_id=question.id,
                correct_answer=(
                    f"A correct answer explains {question.stem.rstrip('.')} "
                    "and gives one supporting example."
                ),
                answer_format=AnswerFormat.EXPLANATION,
                source_refs=[question.id],
            )
        )
        for question in questions
    ]

    answer_key = with_content_hash(
        AnswerKey(
            id=ctx.id("answer_key"),
            created_at=ctx.now(),
            parent_id=assessment.id,
            assessment_id=assessment.id,
            answers=answers,
            total_points=total_points,
            source_refs=[assessment.id],
        )
    )

    return AssessmentBundle(
        questions=tuple(questions),
        answers=tuple(answers),
        answer_key=answer_key,
        assessment=assessment,
    )
