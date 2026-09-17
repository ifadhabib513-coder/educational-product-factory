"""Domain schemas — public API."""

from __future__ import annotations

from lpf.domain.artifact import ArtifactBase, ArtifactStatus, GeneratorInfo
from lpf.domain.content import SolutionStep, SourceRef
from lpf.domain.curriculum import CurriculumBlueprint, CurriculumUnit
from lpf.domain.evidence import EvidenceKind, EvidenceRecord, VerificationStatus
from lpf.domain.identity import compute_content_hash, new_id, with_content_hash
from lpf.domain.learner import LearnerProfile
from lpf.domain.lesson import Lesson
from lpf.domain.misconception import Misconception, MisconceptionSeverity
from lpf.domain.objectives import BloomLevel, LearningObjective, Prerequisite
from lpf.domain.product import ProductDefinition
from lpf.domain.validation import (
    check_misconception_objective_refs,
    check_objective_references,
)
from lpf.domain.worked_example import WorkedExample

__all__ = [
    "ArtifactBase",
    "ArtifactStatus",
    "BloomLevel",
    "CurriculumBlueprint",
    "CurriculumUnit",
    "EvidenceKind",
    "EvidenceRecord",
    "GeneratorInfo",
    "LearningObjective",
    "LearnerProfile",
    "Lesson",
    "Misconception",
    "MisconceptionSeverity",
    "Prerequisite",
    "ProductDefinition",
    "SolutionStep",
    "SourceRef",
    "VerificationStatus",
    "WorkedExample",
    "check_misconception_objective_refs",
    "check_objective_references",
    "compute_content_hash",
    "new_id",
    "with_content_hash",
]
