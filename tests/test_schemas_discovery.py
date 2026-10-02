"""Tests for discovery schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lpf.domain.identity import with_content_hash
from lpf.domain.objectives import BloomLevel, LearningObjective
from lpf.schemas.discovery import (
    CompetitorProfile,
    DiscoveryBrief,
    DiscoveryInputs,
    FeasibilityAssessment,
    FeasibilityLevel,
    MarketAnalysis,
    MarketSegment,
    MarketSignal,
    OutcomeDefinition,
    PainPoint,
    PainPointCategory,
    ProblemBarrier,
    ProblemDefinition,
    ProblemScope,
    ProblemUrgency,
    ProductOpportunity,
)


def _pain(description: str = "Cannot tell why an answer is wrong") -> PainPoint:
    return PainPoint(
        description=description,
        category=PainPointCategory.UNDERSTANDING,
        learner_voice="I just know it's wrong but I don't know why",
    )


def _problem() -> ProblemDefinition:
    return ProblemDefinition(
        statement="Learners cannot diagnose why their answers are wrong.",
        subject="mathematics",
        level="secondary",
        learner_profile_id="lp1",
        pain_points=[_pain()],
        barriers=[
            ProblemBarrier(description="No worked reasoning shown", barrier_type="missing_feedback")
        ],
    )


def _opportunity() -> ProductOpportunity:
    return ProductOpportunity(
        problem_id="prob1",
        title="Error Diagnosis Workbook",
        value_proposition="Shows the reasoning behind each wrong answer, not just the answer.",
        differentiation="Existing workbooks mark answers wrong; this one explains the reasoning gap.",
        implied_outcomes=[LearningObjective(statement="Diagnose the cause of a wrong answer")],
        feasibility=FeasibilityAssessment(
            level=FeasibilityLevel.HIGH,
            rationale="All components exist in the content and practice pipelines.",
        ),
    )


def _market() -> MarketAnalysis:
    return MarketAnalysis(
        problem_id="prob1",
        segments=[MarketSegment.SCHOOL, MarketSegment.SELF_LEARNER],
        primary_segment=MarketSegment.SCHOOL,
        signals=[
            MarketSignal(
                description="Schools report error analysis as a top-three priority",
                source_url="https://example.org/report",
                signal_type="institutional_report",
            )
        ],
        competitors=[
            CompetitorProfile(
                name="Generic Workbook",
                kind="print",
                strengths=["cheap"],
                weaknesses=["no reasoning shown"],
            )
        ],
        gaps=["nothing shows the reasoning behind a wrong answer"],
        confidence=0.6,
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_problem_urgency_values(self) -> None:
        assert len(list(ProblemUrgency)) == 4
        assert ProblemUrgency.CRITICAL == "critical"

    def test_problem_scope_values(self) -> None:
        assert len(list(ProblemScope)) == 3

    def test_pain_point_category_values(self) -> None:
        assert len(list(PainPointCategory)) == 7

    def test_market_segment_values(self) -> None:
        assert len(list(MarketSegment)) == 6

    def test_feasibility_level_values(self) -> None:
        assert len(list(FeasibilityLevel)) == 4


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


class TestPainPoint:
    def test_construction(self) -> None:
        p = _pain()
        assert p.category == PainPointCategory.UNDERSTANDING
        assert p.learner_voice is not None

    def test_defaults(self) -> None:
        p = PainPoint(description="d", category=PainPointCategory.RETENTION)
        assert p.learner_voice is None
        assert p.frequency is None

    def test_frozen(self) -> None:
        p = _pain()
        with pytest.raises(ValidationError):
            p.description = "x"  # type: ignore[misc]

    def test_unknown_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            PainPoint(description="d", category=PainPointCategory.RETENTION, bogus=1)


class TestFeasibilityAssessment:
    def test_construction(self) -> None:
        f = FeasibilityAssessment(level=FeasibilityLevel.HIGH, rationale="all good")
        assert f.blockers == []
        assert f.mitigations == []

    def test_blocked_with_blockers(self) -> None:
        f = FeasibilityAssessment(
            level=FeasibilityLevel.BLOCKED,
            rationale="needs lab data we cannot produce",
            blockers=["no simulation engine"],
        )
        assert f.blockers == ["no simulation engine"]


class TestCompetitorProfile:
    def test_construction(self) -> None:
        c = CompetitorProfile(name="X", kind="digital")
        assert c.url is None
        assert c.strengths == []


class TestMarketSignal:
    def test_construction(self) -> None:
        s = MarketSignal(description="d", signal_type="survey")
        assert s.source_url is None


# ---------------------------------------------------------------------------
# Root artifacts
# ---------------------------------------------------------------------------


class TestProblemDefinition:
    def test_construction(self) -> None:
        p = _problem()
        assert p.artifact_type == "problem_definition"
        assert p.urgency == ProblemUrgency.MEDIUM
        assert p.scope == ProblemScope.FOCUSED
        assert p.evidence_source_ids == []

    def test_empty_pain_points_raises(self) -> None:
        with pytest.raises(ValidationError):
            ProblemDefinition(
                statement="s",
                subject="mathematics",
                level="secondary",
                learner_profile_id="lp1",
                pain_points=[],
            )

    def test_frozen(self) -> None:
        p = _problem()
        with pytest.raises(ValidationError):
            p.statement = "changed"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        p = _problem()
        assert ProblemDefinition.model_validate_json(p.model_dump_json()) == p

    def test_content_hash_stability(self) -> None:
        p = _problem()
        hashed = with_content_hash(p)
        assert hashed.content_hash != ""
        # Hashing must survive a JSON roundtrip unchanged.
        restored = ProblemDefinition.model_validate_json(hashed.model_dump_json())
        assert with_content_hash(restored).content_hash == hashed.content_hash

    def test_content_hash_sensitive_to_change(self) -> None:
        p = _problem()
        changed = p.model_copy(update={"statement": "A different problem entirely."})
        assert with_content_hash(p).content_hash != with_content_hash(changed).content_hash


class TestOutcomeDefinition:
    def test_construction(self) -> None:
        o = OutcomeDefinition(
            problem_id="prob1",
            outcomes=[LearningObjective(statement="Diagnose error causes")],
            target_bloom_level=BloomLevel.ANALYZE,
            mastery_criteria="80% correct diagnosis",
        )
        assert o.artifact_type == "outcome_definition"
        assert len(o.outcomes) == 1

    def test_empty_outcomes_raises(self) -> None:
        with pytest.raises(ValidationError):
            OutcomeDefinition(problem_id="prob1", outcomes=[])

    def test_frozen(self) -> None:
        o = OutcomeDefinition(problem_id="p", outcomes=[LearningObjective(statement="s")])
        with pytest.raises(ValidationError):
            o.problem_id = "x"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        o = OutcomeDefinition(
            problem_id="p",
            outcomes=[LearningObjective(statement="s")],
            target_bloom_level=BloomLevel.APPLY,
        )
        assert OutcomeDefinition.model_validate_json(o.model_dump_json()) == o


class TestProductOpportunity:
    def test_construction(self) -> None:
        o = _opportunity()
        assert o.artifact_type == "product_opportunity"
        assert o.segment == MarketSegment.SELF_LEARNER
        assert o.implied_outcomes

    def test_feasibility_required(self) -> None:
        with pytest.raises(ValidationError):
            ProductOpportunity(
                problem_id="p",
                title="t",
                value_proposition="v",
                differentiation="d",
            )

    def test_frozen(self) -> None:
        o = _opportunity()
        with pytest.raises(ValidationError):
            o.title = "x"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        o = _opportunity()
        assert ProductOpportunity.model_validate_json(o.model_dump_json()) == o


class TestMarketAnalysis:
    def test_construction(self) -> None:
        m = _market()
        assert m.artifact_type == "market_analysis"
        assert m.primary_segment == MarketSegment.SCHOOL
        assert m.confidence == 0.6

    def test_empty_segments_raises(self) -> None:
        with pytest.raises(ValidationError):
            MarketAnalysis(problem_id="p", segments=[], primary_segment=MarketSegment.SCHOOL)

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            MarketAnalysis(
                problem_id="p",
                segments=[MarketSegment.SCHOOL],
                primary_segment=MarketSegment.SCHOOL,
                confidence=1.5,
            )

    def test_json_roundtrip(self) -> None:
        m = _market()
        assert MarketAnalysis.model_validate_json(m.model_dump_json()) == m


class TestDiscoveryBrief:
    def test_construction(self) -> None:
        b = DiscoveryBrief(
            problem_id="prob1",
            outcome_ids=["o1"],
            opportunity_id="opp1",
            market_analysis_id="mkt1",
            summary="Learners need to see reasoning behind wrong answers.",
            priority_topics=["diagnosing errors"],
            research_questions=["How do learners currently detect error causes?"],
        )
        assert b.artifact_type == "discovery_brief"
        assert b.recommended_format is None

    def test_empty_outcome_ids_raises(self) -> None:
        with pytest.raises(ValidationError):
            DiscoveryBrief(
                problem_id="p",
                outcome_ids=[],
                opportunity_id="o",
                market_analysis_id="m",
                summary="s",
            )

    def test_frozen(self) -> None:
        b = DiscoveryBrief(
            problem_id="p",
            outcome_ids=["o1"],
            opportunity_id="o",
            market_analysis_id="m",
            summary="s",
        )
        with pytest.raises(ValidationError):
            b.summary = "x"  # type: ignore[misc]


class TestDiscoveryInputs:
    def test_minimal(self) -> None:
        d = DiscoveryInputs(request="Make a workbook for algebra")
        assert d.subject is None
        assert d.constraints == []

    def test_not_an_artifact(self) -> None:
        d = DiscoveryInputs(request="x")
        assert not hasattr(d, "artifact_type")

    def test_frozen(self) -> None:
        d = DiscoveryInputs(request="x")
        with pytest.raises(ValidationError):
            d.request = "y"  # type: ignore[misc]
