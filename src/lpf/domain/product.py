"""Product definition and specification models."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from lpf.domain.artifact import ArtifactBase
from lpf.domain.objectives import BloomLevel

# ---------------------------------------------------------------------------
# Product taxonomy
# ---------------------------------------------------------------------------


class ProductType(StrEnum):
    """Types of educational products the factory can produce."""

    BOOK = "book"
    WORKBOOK = "workbook"
    REVISION_GUIDE = "revision_guide"
    EXAM_PREP = "exam_prep"
    PRACTICE_PACK = "practice_pack"
    FLASHCARD_PACK = "flashcard_pack"
    STUDY_PLANNER = "study_planner"
    DIAGNOSTIC = "diagnostic"
    RECOVERY_PROGRAM = "recovery_program"
    LEARNING_SYSTEM = "learning_system"
    COURSE = "course"
    WORKSHEET_PACK = "worksheet_pack"
    CHALLENGE_PACK = "challenge_pack"
    PRODUCT_SUITE = "product_suite"


# ---------------------------------------------------------------------------
# Value objects for ProductSpec
# ---------------------------------------------------------------------------


class TargetAudience(BaseModel):
    """Who this product is for."""

    model_config = {"frozen": True, "extra": "forbid"}

    level: str
    age_range: str | None = None
    exam_target: str | None = None
    language: str = "en"


class FormatSpec(BaseModel):
    """Desired format and size of the product."""

    model_config = {"frozen": True, "extra": "forbid"}

    primary: ProductType
    pages: int | None = None
    exercise_count: int | None = None
    assessment_count: int | None = None
    answer_key: bool = True
    include_citations: bool = True


class LearningSpec(BaseModel):
    """Learning design parameters."""

    model_config = {"frozen": True, "extra": "forbid"}

    progression: list[str] = Field(default_factory=list)
    mastery_criteria: str | None = None
    bloom_target: BloomLevel | None = None


class ConstraintsSpec(BaseModel):
    """Production constraints."""

    model_config = {"frozen": True, "extra": "forbid"}

    evidence_required: bool = True
    citation_required: bool = True
    calculator_allowed: bool | None = None
    exam_alignment: str | None = None
    max_pages: int | None = None


class QualitySpec(BaseModel):
    """Quality requirements for the product."""

    model_config = {"frozen": True, "extra": "forbid"}

    minimum_score: float = 0.8
    required_gates: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Root artifacts
# ---------------------------------------------------------------------------


class ProductDefinition(ArtifactBase):
    """Root artifact: what educational product to generate.

    Kept for backward compatibility with Stage 2a tests.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["product_definition"] = "product_definition"
    title: str
    subject: str
    topic: str
    level: str
    problem_statement: str
    learner_profile_id: str


class ProductSpec(ArtifactBase):
    """Root artifact: comprehensive product specification.

    This is the source of truth for everything the factory produces.
    It captures the full intent: what to build, for whom, how, and to what quality.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["product_spec"] = "product_spec"
    title: str
    product_type: ProductType
    subject: str
    topic: str
    language: str = "en"
    audience: TargetAudience
    format: FormatSpec
    learning: LearningSpec
    constraints: ConstraintsSpec
    quality: QualitySpec
    problem_statement: str
    learner_profile_id: str
