"""Base artifact model and shared types."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from lpf.domain.identity import new_id


class GeneratorInfo(BaseModel):
    """Metadata about how an artifact was generated."""

    model_config = {"frozen": True, "extra": "forbid"}

    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None


ArtifactStatus = Literal["draft", "validated", "needs_review", "approved", "rejected"]


class ArtifactBase(BaseModel):
    """Base class for all root artifacts.

    Only root artifacts inherit this. Embedded value objects use plain BaseModel.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    schema_version: str = "1"
    id: str = Field(default_factory=new_id)
    artifact_type: str
    status: ArtifactStatus = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_hash: str = ""
    parent_id: str | None = None
    generator: GeneratorInfo | None = None
    source_refs: list[str] = Field(default_factory=list)
