"""Misconception model."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from lpf.domain.artifact import ArtifactBase


class MisconceptionSeverity(StrEnum):
    """How common this misconception is among learners."""

    COMMON = "common"
    OCCASIONAL = "occasional"
    RARE = "rare"


class Misconception(ArtifactBase):
    """Root artifact: a common learner misconception."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["misconception"] = "misconception"
    statement: str
    correction: str
    objective_ids: list[str] = Field(min_length=1)
    severity: MisconceptionSeverity | None = None
