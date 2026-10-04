"""Factual consistency validators."""

from __future__ import annotations

from lpf.domain.lesson import Lesson
from lpf.errors import ValidationError
from lpf.result import Result, err, ok
from lpf.schemas.research import EvidenceClaim, EvidenceMap


def check_factual_claims_reference_valid_evidence(
    claims: list[EvidenceClaim],
    evidence_record_ids: set[str] | None = None,
) -> Result[list[EvidenceClaim], ValidationError]:
    """Verify factual claims cite valid evidence record IDs."""
    if evidence_record_ids is None:
        evidence_record_ids = set()

    missing: list[dict[str, str]] = []
    for claim in claims:
        if evidence_record_ids:
            for sid in claim.source_ids:
                if sid not in evidence_record_ids:
                    missing.append({"claim_id": claim.claim_id, "evidence_record_id": sid})
        elif not claim.source_ids:
            missing.append({"claim_id": claim.claim_id, "issue": "no evidence references"})

    if missing:
        return err(
            ValidationError(
                code="INVALID_EVIDENCE_REFERENCES",
                message="Factual claims reference invalid evidence records",
                details={"missing": missing},
            )
        )
    return ok(claims)


def check_factual_consistency(
    lessons: list[Lesson],
    evidence_map: EvidenceMap,
) -> Result[tuple[Lesson, ...], ValidationError]:
    """Verify that factual claims in content align with evidence."""
    evidence_ids = set()
    for claim in evidence_map.claims:
        evidence_ids.update(claim.source_ids)
    claim_check = check_factual_claims_reference_valid_evidence(evidence_map.claims, evidence_ids)
    if claim_check.is_err():
        return err(claim_check.error)

    if lessons and evidence_map.conflicting_claims > 0 and evidence_map.supported_claims == 0:
        return err(
            ValidationError(
                code="UNSUPPORTED_CONFLICTING_CLAIMS",
                message="Factual claims are contradictory and ungrounded by supported evidence.",
                details={
                    "conflicting_claims": evidence_map.conflicting_claims,
                    "supported_claims": evidence_map.supported_claims,
                },
            )
        )

    if lessons and evidence_map.supported_claims == 0 and evidence_map.total_claims > 0:
        return err(
            ValidationError(
                code="UNGROUNDED_CLAIMS",
                message="Factual claims are not grounded in supported evidence.",
                details={
                    "total_claims": evidence_map.total_claims,
                    "supported_claims": evidence_map.supported_claims,
                },
            )
        )

    return ok(tuple(lessons))
