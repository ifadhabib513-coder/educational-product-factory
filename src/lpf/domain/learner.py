"""Learner profile — fully subject-agnostic."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LearnerProfile(BaseModel):
    """Describes the learner for whom a product is being created.

    This model is fully subject-agnostic: no physics, no math, no domain assumptions.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    subject: str
    level: str
    goals: list[str] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)
    prior_knowledge: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
