"""Domain schemas — public API."""

from __future__ import annotations

from lpf.domain.artifact import ArtifactBase, ArtifactStatus, GeneratorInfo
from lpf.domain.curriculum import CurriculumBlueprint, CurriculumUnit
from lpf.domain.identity import compute_content_hash, new_id, with_content_hash
from lpf.domain.learner import LearnerProfile
from lpf.domain.objectives import BloomLevel, LearningObjective, Prerequisite
from lpf.domain.product import ProductDefinition
from lpf.domain.validation import check_objective_references

__all__ = [
    "ArtifactBase",
    "ArtifactStatus",
    "BloomLevel",
    "CurriculumBlueprint",
    "CurriculumUnit",
    "GeneratorInfo",
    "LearningObjective",
    "LearnerProfile",
    "Prerequisite",
    "ProductDefinition",
    "check_objective_references",
    "compute_content_hash",
    "new_id",
    "with_content_hash",
]
