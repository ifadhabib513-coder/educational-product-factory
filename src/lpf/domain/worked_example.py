"""Worked example model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from lpf.domain.artifact import ArtifactBase
from lpf.domain.content import SolutionStep


class WorkedExampleDraft(BaseModel):
    """The writer's answer for a worked example, before identity is stamped.

    This is the schema a model is asked to produce. It deliberately carries no
    artifact identity (``id``, ``created_at``, ``parent_id``, ``source_refs``):
    those are owned by the Content stage, which stamps them onto the draft. The
    numeric QA gate consumes ``solution_steps[].expression`` and
    ``final_answer``, so a model that writes wrong arithmetic here is exactly
    the model-written defect the revision loop is built to repair.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    problem_statement: str
    solution_steps: list[SolutionStep] = Field(min_length=1)
    final_answer: str
    common_errors: list[str] = Field(default_factory=list)


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
