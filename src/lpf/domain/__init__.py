"""Domain schemas — public API."""

from __future__ import annotations

from lpf.domain.artifact import ArtifactBase, ArtifactStatus, GeneratorInfo
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
from lpf.domain.content import SolutionStep, SourceRef
from lpf.domain.curriculum import CurriculumBlueprint, CurriculumUnit
from lpf.domain.evidence import EvidenceKind, EvidenceRecord, VerificationStatus
from lpf.domain.identity import compute_content_hash, new_id, with_content_hash
from lpf.domain.learner import LearnerProfile
from lpf.domain.lesson import Lesson
from lpf.domain.misconception import Misconception, MisconceptionSeverity
from lpf.domain.objectives import BloomLevel, LearningObjective, Prerequisite
from lpf.domain.practice import (
    DifficultyLevel,
    Hint,
    PracticeQuestion,
    QuestionType,
    ScaffoldingType,
)
from lpf.domain.product import (
    ConstraintsSpec,
    FormatSpec,
    LearningSpec,
    ProductDefinition,
    ProductSpec,
    ProductType,
    QualitySpec,
    TargetAudience,
)
from lpf.domain.quality import (
    Finding,
    GateStatus,
    QualityGate,
    Severity,
    VerificationResult,
)
from lpf.domain.validation import (
    check_answer_key_references,
    check_answer_references,
    check_assessment_references,
    check_misconception_objective_refs,
    check_objective_references,
    check_prerequisite_chain,
    check_quality_gate_references,
    check_question_references,
)
from lpf.domain.worked_example import WorkedExample

__all__ = [
    "Answer",
    "AnswerFormat",
    "AnswerKey",
    "ArtifactBase",
    "ArtifactStatus",
    "Assessment",
    "AssessmentType",
    "BloomLevel",
    "ConstraintsSpec",
    "CurriculumBlueprint",
    "CurriculumUnit",
    "DifficultyLevel",
    "EvidenceKind",
    "EvidenceRecord",
    "Finding",
    "FormatSpec",
    "GateStatus",
    "GeneratorInfo",
    "Hint",
    "LearningObjective",
    "LearningSpec",
    "LearnerProfile",
    "Lesson",
    "Misconception",
    "MisconceptionSeverity",
    "PracticeQuestion",
    "Prerequisite",
    "ProductDefinition",
    "ProductSpec",
    "ProductType",
    "QualityGate",
    "QualitySpec",
    "QuestionType",
    "Rubric",
    "RubricCriterion",
    "RubricLevel",
    "ScaffoldingType",
    "Severity",
    "SolutionStep",
    "SourceRef",
    "TargetAudience",
    "VerificationResult",
    "VerificationStatus",
    "WorkedExample",
    "check_answer_key_references",
    "check_answer_references",
    "check_assessment_references",
    "check_misconception_objective_refs",
    "check_objective_references",
    "check_prerequisite_chain",
    "check_question_references",
    "check_quality_gate_references",
    "compute_content_hash",
    "new_id",
    "with_content_hash",
]
