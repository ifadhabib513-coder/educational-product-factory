"""Learning objectives, Bloom's taxonomy, and prerequisite mapping."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from lpf.domain.artifact import ArtifactBase


class BloomLevel(StrEnum):
    """Bloom's taxonomy levels."""

    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


class LearningObjective(ArtifactBase):
    """A single learning objective."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["learning_objective"] = "learning_objective"
    statement: str
    bloom_level: BloomLevel | None = None
    mastery_criteria: str | None = None


class Prerequisite(BaseModel):
    """A prerequisite relationship between two objectives.

    This is an embedded value object, not a root artifact.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    prerequisite_objective_id: str
    objective_id: str
    rationale: str | None = None
