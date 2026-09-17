"""Product definition — the top-level artifact describing what is being built."""

from __future__ import annotations

from typing import Literal

from lpf.domain.artifact import ArtifactBase


class ProductDefinition(ArtifactBase):
    """Root artifact: what educational product to generate."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["product_definition"] = "product_definition"
    title: str
    subject: str
    topic: str
    level: str
    problem_statement: str
    learner_profile_id: str
