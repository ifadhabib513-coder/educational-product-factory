"""Tests for the factual quality gate (TASK-003).

Covers both halves of the gate: claims must cite evidence records that exist,
and content must not ship when its evidence is purely contradictory or wholly
unsupported.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from lpf.domain.lesson import Lesson
from lpf.orchestration import pipeline as pipeline_module
from lpf.orchestration.pipeline import FactoryPipeline
from lpf.orchestration.research_stage import ResearchBundle
from lpf.orchestration.state import RunStage
from lpf.result import is_err, is_ok, unwrap
from lpf.schemas.discovery import DiscoveryInputs
from lpf.schemas.research import EvidenceClaim, EvidenceMap
from lpf.validators.factual import (
    check_factual_claims_reference_valid_evidence,
    check_factual_consistency,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lesson() -> Lesson:
    return Lesson(
        title="Velocity Basics",
        unit_id="u1",
        objective_ids=["obj_001"],
        body_markdown="## Velocity\nVelocity is the rate of change of position.",
    )


def _claim(
    claim_id: str,
    *,
    source_ids: list[str] | None = None,
    is_conflicting: bool = False,
) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim_id,
        claim=f"Claim text for {claim_id}",
        source_ids=["src_001"] if source_ids is None else source_ids,
        evidence_text="Retrieved evidence text.",
        confidence=0.9,
        is_conflicting=is_conflicting,
    )


def _evidence_map(
    *,
    claims: list[EvidenceClaim] | None = None,
    supported: int = 1,
    conflicting: int = 0,
    total: int | None = None,
) -> EvidenceMap:
    found = [] if claims is None else claims
    return EvidenceMap(
        research_report_id="rr_001",
        claims=found,
        total_claims=len(found) if total is None else total,
        supported_claims=supported,
        conflicting_claims=conflicting,
    )


def _inputs() -> DiscoveryInputs:
    return DiscoveryInputs(
        request="Teach me linear algebra basics.",
        subject="linear algebra",
        level="year 10",
    )


# ---------------------------------------------------------------------------
# Claims must cite valid evidence records
# ---------------------------------------------------------------------------


class TestClaimsCiteEvidence:
    def test_claim_with_known_evidence_record_passes(self) -> None:
        claims = [_claim("c1"), _claim("c2", source_ids=["src_002"])]
        result = check_factual_claims_reference_valid_evidence(claims, {"src_001", "src_002"})
        assert is_ok(result)

    def test_claim_citing_unknown_evidence_record_fails(self) -> None:
        claims = [_claim("c1", source_ids=["src_001", "src_ghost"])]
        result = check_factual_claims_reference_valid_evidence(claims, {"src_001"})
        assert is_err(result)
        error = result.error  # type: ignore[union-attr]
        assert error.code == "INVALID_EVIDENCE_REFERENCES"
        missing = error.details["missing"]
        assert missing[0]["claim_id"] == "c1"
        assert missing[0]["evidence_record_id"] == "src_ghost"

    def test_all_claims_must_resolve_not_just_the_first(self) -> None:
        claims = [
            _claim("c1", source_ids=["src_001"]),
            _claim("c2", source_ids=["src_002"]),
        ]
        result = check_factual_claims_reference_valid_evidence(claims, {"src_001"})
        assert is_err(result)
        missing = result.error.details["missing"]  # type: ignore[union-attr]
        assert [item["claim_id"] for item in missing] == ["c2"]

    def test_empty_citation_fails_even_without_a_catalogue(self) -> None:
        # Bypass the min_length=1 schema guard to reach the validator.
        claim = EvidenceClaim.model_construct(
            claim_id="c_empty",
            claim="An uncited assertion",
            source_ids=[],
            evidence_text="Evidence text.",
            confidence=0.5,
        )
        result = check_factual_claims_reference_valid_evidence([claim])
        assert is_err(result)
        assert result.error.code == "INVALID_EVIDENCE_REFERENCES"  # type: ignore[union-attr]

    def test_without_a_catalogue_any_non_empty_citation_passes(self) -> None:
        result = check_factual_claims_reference_valid_evidence(
            [_claim("c1", source_ids=["anything"])], None
        )
        assert is_ok(result)


# ---------------------------------------------------------------------------
# Content must be grounded in evidence
# ---------------------------------------------------------------------------


class TestFactualConsistency:
    def test_grounded_content_passes(self) -> None:
        result = check_factual_consistency([_lesson()], _evidence_map(supported=3))
        assert is_ok(result)
        assert len(unwrap(result)) == 1  # type: ignore[arg-type]

    def test_ungrounded_content_fails(self) -> None:
        em = _evidence_map(claims=[_claim("c1")], supported=0, total=1)
        result = check_factual_consistency([_lesson()], em)
        assert is_err(result)
        assert result.error.code == "UNGROUNDED_CLAIMS"  # type: ignore[union-attr]

    def test_contradictory_evidence_fails_with_a_distinct_code(self) -> None:
        em = _evidence_map(
            claims=[_claim("c1"), _claim("c2", is_conflicting=True)],
            supported=0,
            conflicting=2,
        )
        result = check_factual_consistency([_lesson()], em)
        assert is_err(result)
        assert result.error.code == "CONTRADICTORY_EVIDENCE"  # type: ignore[union-attr]

    def test_lessons_with_no_research_at_all_are_not_this_gates_call(self) -> None:
        em = _evidence_map(claims=[], supported=0, conflicting=0, total=0)
        assert is_ok(check_factual_consistency([_lesson()], em))

    def test_no_lessons_means_nothing_to_ground(self) -> None:
        em = _evidence_map(claims=[_claim("c1")], supported=0, total=1)
        assert is_ok(check_factual_consistency([], em))

    def test_catalogue_is_enforced_through_the_consistency_check(self) -> None:
        em = _evidence_map(claims=[_claim("c1", source_ids=["src_ghost"])], supported=1)
        result = check_factual_consistency([_lesson()], em, {"src_001"})
        assert is_err(result)
        assert result.error.code == "INVALID_EVIDENCE_REFERENCES"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# The gate is wired into QA
# ---------------------------------------------------------------------------


class TestQaGateWiring:
    async def test_gate_is_present_in_a_passing_run(self, tmp_path: Path) -> None:
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(_inputs(), run_id="fact-pass")
        assert result.succeeded
        gates = {gate.gate_name: gate for gate in result.verification.gates}  # type: ignore[union-attr]
        assert "factual_consistency" in gates
        assert gates["factual_consistency"].status.value == "passed"

    async def test_ungrounded_evidence_fails_the_run_before_packaging(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original_build_research = pipeline_module.build_research

        async def ungrounded(*args: object, **kwargs: object) -> ResearchBundle:
            bundle = await original_build_research(*args, **kwargs)
            em = bundle.evidence_map
            unsupported = em.model_copy(
                update={
                    "supported_claims": 0,
                    "conflicting_claims": max(1, em.conflicting_claims),
                }
            )
            return replace(bundle, evidence_map=unsupported)

        monkeypatch.setattr(pipeline_module, "build_research", ungrounded)

        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(_inputs(), run_id="fact-fail")

        assert not result.succeeded
        assert result.state.stage is RunStage.FAILED
        # The gate's evidence is research-owned, so the revision cycle cannot
        # repair it: the run aborts immediately instead of burning the budget.
        assert result.state.revisions == 0
        assert result.package is None
        assert not (tmp_path / "fact-fail").exists()
        verification = result.verification
        assert verification is not None
        failed = [gate for gate in verification.gates if gate.gate_name == "factual_consistency"]
        assert failed and failed[0].status.value == "failed"

    async def test_gate_is_required_when_asked_for(self, tmp_path: Path) -> None:
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(
            _inputs(),
            run_id="fact-req",
            required_gates=["factual_consistency"],
        )
        assert result.succeeded
        names = [gate.gate_name for gate in result.verification.gates]  # type: ignore[union-attr]
        assert "factual_consistency" in names
        assert "required_gates_present" in names

    async def test_schema_conformance_has_no_decorative_gate(self, tmp_path: Path) -> None:
        """Pydantic enforces schemas at construction, so no ``schema_validity``
        gate is emitted (the old one was hard-wired PASSED and could never fail)."""
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(_inputs(), run_id="schema-none")
        assert result.succeeded
        names = [gate.gate_name for gate in result.verification.gates]  # type: ignore[union-attr]
        assert "schema_validity" not in names


class TestEvidenceCatalogueIsLive:
    """The citation half of the gate must run against real retrieved sources."""

    async def test_pipeline_hands_the_gate_the_verified_source_catalogue(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import lpf.orchestration.qa_stage as qa_module

        real = qa_module.check_factual_consistency
        seen: list[set[str] | None] = []

        def spy(
            lessons: list[Lesson],
            evidence_map: EvidenceMap,
            evidence_record_ids: set[str] | None = None,
        ):
            seen.append(evidence_record_ids)
            return real(lessons, evidence_map, evidence_record_ids)

        monkeypatch.setattr(qa_module, "check_factual_consistency", spy)

        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(_inputs(), run_id="cat")
        assert result.succeeded

        report = next(
            artifact for artifact in result.artifacts if artifact.artifact_type == "research_report"
        )
        expected = {source.source_id for source in report.verified_sources}
        assert expected
        assert seen == [expected]

    async def test_claim_citing_a_source_that_never_verified_fails_the_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original_build_research = pipeline_module.build_research

        async def with_phantom_source(*args: object, **kwargs: object) -> ResearchBundle:
            bundle = await original_build_research(*args, **kwargs)
            em = bundle.evidence_map
            phantom = _claim("c_phantom", source_ids=["src_never_verified"])
            return replace(
                bundle,
                evidence_map=em.model_copy(update={"claims": [*em.claims, phantom]}),
            )

        monkeypatch.setattr(pipeline_module, "build_research", with_phantom_source)

        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(_inputs(), run_id="phantom")

        assert not result.succeeded
        assert result.state.stage is RunStage.FAILED
        gate = next(
            gate
            for gate in result.verification.gates  # type: ignore[union-attr]
            if gate.gate_name == "factual_consistency"
        )
        assert gate.status.value == "failed"
        finding = gate.findings[0]
        assert "invalid evidence record" in finding.problem
        assert "src_never_verified" in finding.evidence
