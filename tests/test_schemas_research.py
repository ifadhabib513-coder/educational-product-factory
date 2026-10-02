"""Tests for research schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lpf.domain.identity import with_content_hash
from lpf.schemas.research import (
    EvidenceClaim,
    ResearchPlan,
    ResearchQuestion,
    SearchProvider,
    SearchResult,
    SearchStrategy,
    SourceAuthority,
    VerifiedSource,
)

# ---------------------------------------------------------------------------
# Tests: SearchResult
# ---------------------------------------------------------------------------


class TestSearchResult:
    def test_construction(self) -> None:
        r = SearchResult(
            source_id="src1",
            title="Test",
            url="https://example.com",
            snippet="A snippet",
            domain="example.com",
            provider=SearchProvider.MOCK,
        )
        assert r.source_id == "src1"
        assert r.authority == SourceAuthority.UNKNOWN

    def test_with_authority(self) -> None:
        r = SearchResult(
            source_id="src2",
            title="Academic",
            url="https://arxiv.org/abs/1234",
            snippet="Paper",
            domain="arxiv.org",
            provider=SearchProvider.ARXIV,
            authority=SourceAuthority.ACADEMIC,
            relevance_score=0.9,
        )
        assert r.authority == SourceAuthority.ACADEMIC
        assert r.relevance_score == 0.9


# ---------------------------------------------------------------------------
# Tests: EvidenceClaim
# ---------------------------------------------------------------------------


class TestEvidenceClaim:
    def test_construction(self) -> None:
        c = EvidenceClaim(
            claim_id="clm1",
            claim="Water boils at 100C",
            source_ids=["src1"],
            evidence_text="Direct measurement",
        )
        assert c.claim_id == "clm1"
        assert c.confidence == 0.0

    def test_empty_source_ids_raises(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            EvidenceClaim(
                claim_id="clm1",
                claim="test",
                source_ids=[],
                evidence_text="test",
            )


# ---------------------------------------------------------------------------
# Tests: ResearchQuestion
# ---------------------------------------------------------------------------


class TestResearchQuestion:
    def test_construction(self) -> None:
        q = ResearchQuestion(
            question_id="q1",
            text="What causes confusion?",
            topic="linear equations",
            strategy=SearchStrategy(),
        )
        assert q.question_id == "q1"
        assert q.priority == 1


# ---------------------------------------------------------------------------
# Tests: ResearchPlan
# ---------------------------------------------------------------------------


class TestResearchPlan:
    def test_construction(self) -> None:
        plan = with_content_hash(
            ResearchPlan(
                product_spec_id="spec1",
                questions=[
                    ResearchQuestion(
                        question_id="q1",
                        text="What?",
                        topic="t",
                        strategy=SearchStrategy(),
                    )
                ],
            )
        )
        assert plan.artifact_type == "research_plan"
        assert len(plan.questions) == 1

    def test_empty_questions_raises(self) -> None:
        with pytest.raises(ValidationError, match="too_short"):
            ResearchPlan(
                product_spec_id="spec1",
                questions=[],
            )


# ---------------------------------------------------------------------------
# Tests: VerifiedSource
# ---------------------------------------------------------------------------


class TestVerifiedSource:
    def test_construction(self) -> None:
        vs = VerifiedSource(
            source_id="vs1",
            url="https://example.com",
            title="Example",
            domain="example.com",
            authority=SourceAuthority.INSTITUTIONAL,
        )
        assert vs.exists is True
        assert vs.relevant is True


# ---------------------------------------------------------------------------
# Tests: ResearchReport
# ---------------------------------------------------------------------------


class TestResearchReport:
    def test_construction(self) -> None:
        rr = with_content_hash(
            EvidenceClaim(
                claim_id="c1",
                claim="test",
                source_ids=["s1"],
                evidence_text="text",
            )
        )
        # ResearchReport needs claims
        from lpf.schemas.research import ResearchReport

        report = with_content_hash(
            ResearchReport(
                product_spec_id="spec1",
                claims=[rr],
            )
        )
        assert report.artifact_type == "research_report"
        assert len(report.claims) == 1
