"""Factual consistency validators.

The gate verifies two things before content can ship:

1. Every factual claim cites at least one evidence record, and (when an
   evidence catalogue is supplied) every cited record actually exists.
2. The evidence backing the content is not purely contradictory: claims that
   are all conflicting and none supported mean the content asserts things the
   research could not stand behind.
"""

from __future__ import annotations

from lpf.domain.lesson import Lesson
from lpf.errors import ValidationError
from lpf.result import Result, err, is_err, ok
from lpf.schemas.research import EvidenceClaim, EvidenceMap


def check_factual_claims_reference_valid_evidence(
    claims: list[EvidenceClaim],
    evidence_record_ids: set[str] | None = None,
) -> Result[list[EvidenceClaim], ValidationError]:
    """Verify factual claims cite valid evidence record IDs.

    ``evidence_record_ids`` is the catalogue of evidence records known to
    exist. When it is ``None`` the catalogue is unavailable and only
    non-empty citations are required; when it is provided, every cited id
    must resolve against it.
    """
    missing: list[dict[str, str]] = []
    for claim in claims:
        if not claim.source_ids:
            missing.append({"claim_id": claim.claim_id, "issue": "no evidence references"})
            continue
        if evidence_record_ids is None:
            continue
        for sid in claim.source_ids:
            if sid not in evidence_record_ids:
                missing.append({"claim_id": claim.claim_id, "evidence_record_id": sid})

    if missing:
        return err(
            ValidationError(
                code="INVALID_EVIDENCE_REFERENCES",
                message=f"Factual claims reference {len(missing)} invalid evidence record(s)",
                details={"missing": missing},
            )
        )
    return ok(claims)


def check_factual_consistency(
    lessons: list[Lesson],
    evidence_map: EvidenceMap,
    evidence_record_ids: set[str] | None = None,
) -> Result[tuple[Lesson, ...], ValidationError]:
    """Verify that factual claims in content align with research evidence.

    Fails when the content is grounded only in contradictory evidence
    (claims conflict and nothing clears the support threshold) or when the
    claims are entirely unsupported. Lessons with no research at all are
    reported by the ``research_evidence`` gate instead, so an empty evidence
    map alone is not a hard failure here.
    """
    claim_check = check_factual_claims_reference_valid_evidence(
        evidence_map.claims, evidence_record_ids
    )
    if is_err(claim_check):
        return err(claim_check.error)

    if lessons and evidence_map.supported_claims == 0 and evidence_map.conflicting_claims > 0:
        return err(
            ValidationError(
                code="CONTRADICTORY_EVIDENCE",
                message="Content is backed only by contradictory evidence.",
                details={
                    "conflicting_claims": evidence_map.conflicting_claims,
                    "supported_claims": evidence_map.supported_claims,
                    "total_claims": evidence_map.total_claims,
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
