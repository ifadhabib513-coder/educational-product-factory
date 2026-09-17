"""Curriculum blueprint — ordered units referencing learning objectives."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from lpf.domain.artifact import ArtifactBase


class CurriculumUnit(BaseModel):
    """A single unit in the curriculum.

    Embedded value object, not a root artifact.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    unit_id: str
    title: str
    objective_ids: list[str] = Field(default_factory=list)
    order: int


class CurriculumBlueprint(ArtifactBase):
    """Root artifact: ordered curriculum units referencing objectives."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["curriculum_blueprint"] = "curriculum_blueprint"
    title: str = ""
    units: list[CurriculumUnit] = Field(default_factory=list)
