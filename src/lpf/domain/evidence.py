"""Evidence record model — honest provenance tracking."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import model_validator

from lpf.domain.artifact import ArtifactBase
from lpf.domain.content import SourceRef


class EvidenceKind(StrEnum):
    """How this evidence was produced.

    Model-generated content is ALLOWED but must be honestly labeled.
    """

    DIRECT_SOURCE = "direct_source"
    MODEL_GENERATED = "model_generated"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    EXAMPLE = "example"
    ILLUSTRATIVE = "illustrative"
    HUMAN_APPROVED = "human_approved"


VerificationStatus = Literal["unverified", "verified", "refuted", "needs_review"]


class EvidenceRecord(ArtifactBase):
    """Root artifact: a factual or educational claim with provenance.

    evidence_kind=direct_source WITHOUT a source is a schema error:
    this enforces the no-fabricated-citations rule at the type level.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["evidence_record"] = "evidence_record"
    claim: str
    evidence_kind: EvidenceKind
    source: SourceRef | None = None
    verification_status: VerificationStatus = "unverified"
    notes: str | None = None

    @model_validator(mode="after")
    def _check_direct_source_requires_source(self) -> EvidenceRecord:
        if self.evidence_kind == EvidenceKind.DIRECT_SOURCE and self.source is None:
            raise ValueError(
                "evidence_kind='direct_source' requires a source; "
                "a claim cannot carry a direct-source label without a source reference"
            )
        return self
