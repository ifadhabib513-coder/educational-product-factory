"""Learner profile — fully subject-agnostic."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from lpf.domain.artifact import ArtifactBase


class LearnerProfile(ArtifactBase):
    """Describes the learner for whom a product is being created.

    This model is fully subject-agnostic: no physics, no math, no domain assumptions.
    Inherits ArtifactBase for stable id and created_at.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["learner_profile"] = "learner_profile"
    subject: str
    level: str
    goals: list[str] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)
    prior_knowledge: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
