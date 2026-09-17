"""Lesson model."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from lpf.domain.artifact import ArtifactBase


class Lesson(ArtifactBase):
    """Root artifact: a single lesson in the curriculum."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["lesson"] = "lesson"
    title: str
    unit_id: str
    objective_ids: list[str] = Field(min_length=1)
    body_markdown: str
    summary: str | None = None
