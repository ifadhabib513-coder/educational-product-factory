"""Practice question and hint models."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from lpf.domain.artifact import ArtifactBase


class QuestionType(StrEnum):
    """Types of practice questions."""

    MULTIPLE_CHOICE = "multiple_choice"
    SHORT_ANSWER = "short_answer"
    TRUE_FALSE = "true_false"
    NUMERICAL = "numerical"
    PROOF = "proof"
    EXPLANATION = "explanation"
    MATCHING = "matching"
    ORDERING = "ordering"
    FILL_BLANK = "fill_blank"


class DifficultyLevel(StrEnum):
    """Difficulty classification for questions."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    CHALLENGE = "challenge"


class ScaffoldingType(StrEnum):
    """How a hint scaffolds the learner's thinking."""

    NUDGE = "nudge"
    CONCEPTUAL = "conceptual"
    PROCEDURAL = "procedural"
    WORKED_PARTIAL = "worked_partial"


class PracticeQuestion(ArtifactBase):
    """Root artifact: a single practice question."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["practice_question"] = "practice_question"
    question_type: QuestionType
    difficulty: DifficultyLevel
    lesson_id: str
    objective_ids: list[str] = Field(min_length=1)
    stem: str
    choices: list[str] | None = None
    hints: list[str] = Field(default_factory=list)
    common_misconceptions: list[str] = Field(default_factory=list)
    estimated_time_seconds: int | None = None


class Hint(ArtifactBase):
    """Root artifact: a scaffolded hint for a practice question."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["hint"] = "hint"
    question_id: str
    order: int
    text: str
    scaffolding_type: ScaffoldingType
