"""Quality gate and verification result models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from lpf.domain.artifact import ArtifactBase


class GateStatus(StrEnum):
    """Outcome of a quality gate check."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"


class Severity(StrEnum):
    """Severity of a QA finding."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class Finding(BaseModel):
    """A single finding from a QA check."""

    model_config = {"frozen": True, "extra": "forbid"}

    severity: Severity
    location: str
    problem: str
    evidence: str | None = None
    suggested_fix: str | None = None


class QualityGate(ArtifactBase):
    """Root artifact: result of a single quality gate check."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["quality_gate"] = "quality_gate"
    gate_name: str
    status: GateStatus
    score: float | None = None
    findings: list[Finding] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class VerificationResult(ArtifactBase):
    """Root artifact: aggregated quality gate results for a product."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["verification_result"] = "verification_result"
    gates: list[QualityGate] = Field(min_length=1)
    overall_status: GateStatus
    overall_score: float | None = None
    iteration: int = 1
    max_iterations: int = 3
