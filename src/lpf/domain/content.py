"""Shared value objects for content models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SolutionStep(BaseModel):
    """A single step in a worked-example solution."""

    model_config = {"frozen": True, "extra": "forbid"}

    order: int
    statement: str
    expression: str | None = None


class SourceRef(BaseModel):
    """Reference to an external source.

    Distinguished from ArtifactBase.source_refs (which lists other artifact IDs).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    source_type: Literal["book", "journal", "website", "dataset", "curriculum_standard", "other"]
    identifier: str
    location: str | None = None
    retrieved_at: datetime | None = None
