"""Worked example model."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from lpf.domain.artifact import ArtifactBase
from lpf.domain.content import SolutionStep


class WorkedExample(ArtifactBase):
    """Root artifact: a step-by-step worked example."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["worked_example"] = "worked_example"
    title: str
    lesson_id: str
    problem_statement: str
    solution_steps: list[SolutionStep] = Field(min_length=1)
    final_answer: str
    common_errors: list[str] = Field(default_factory=list)
