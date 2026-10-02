"""Assessment, answer, rubric, and answer-key models."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from lpf.domain.artifact import ArtifactBase
from lpf.domain.content import SolutionStep


class AnswerFormat(StrEnum):
    """How an answer should be evaluated."""

    EXACT = "exact"
    NUMERIC = "numeric"
    RANGE = "range"
    RUBRIC = "rubric"
    EXPLANATION = "explanation"


class AssessmentType(StrEnum):
    """Purpose of an assessment."""

    DIAGNOSTIC = "diagnostic"
    FORMATIVE = "formative"
    SUMMATIVE = "summative"
    CHALLENGE = "challenge"


class RubricLevel(BaseModel):
    """A single performance level within a rubric criterion."""

    model_config = {"frozen": True, "extra": "forbid"}

    label: str
    points: float
    description: str


class RubricCriterion(BaseModel):
    """A single criterion in a rubric, with performance levels."""

    model_config = {"frozen": True, "extra": "forbid"}

    criterion: str
    max_points: float
    levels: list[RubricLevel] = Field(min_length=2)


class Answer(ArtifactBase):
    """Root artifact: a correct answer for a practice question."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["answer"] = "answer"
    question_id: str
    correct_answer: str
    answer_format: AnswerFormat
    solution_steps: list[SolutionStep] = Field(default_factory=list)
    rubric_id: str | None = None


class AnswerKey(ArtifactBase):
    """Root artifact: complete answer key for an assessment."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["answer_key"] = "answer_key"
    assessment_id: str
    answers: list[Answer] = Field(min_length=1)
    total_points: float


class Rubric(ArtifactBase):
    """Root artifact: scoring rubric for a question or assessment."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["rubric"] = "rubric"
    question_id: str
    criteria: list[RubricCriterion] = Field(min_length=1)
    total_points: float


class Assessment(ArtifactBase):
    """Root artifact: a collection of questions forming an assessment."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["assessment"] = "assessment"
    assessment_type: AssessmentType
    title: str
    question_ids: list[str] = Field(min_length=1)
    total_points: float
    time_limit_minutes: int | None = None
