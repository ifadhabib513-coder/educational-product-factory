"""Tests for discovery validation functions."""

from __future__ import annotations

import pytest

from lpf.discovery.validation import (
    check_discovery_brief,
    check_discovery_chain,
    check_feasibility,
    check_outcome_references,
)
from lpf.domain.objectives import LearningObjective
from lpf.result import is_err, is_ok
from lpf.schemas.discovery import (
    DiscoveryBrief,
    FeasibilityAssessment,
    FeasibilityLevel,
    MarketAnalysis,
    MarketSegment,
    OutcomeDefinition,
    PainPoint,
    PainPointCategory,
    ProblemDefinition,
    ProductOpportunity,
)


def _problem(pid: str = "prob1") -> ProblemDefinition:
    return ProblemDefinition(
        id=pid,
        statement="Learners cannot diagnose why their answers are wrong.",
        subject="mathematics",
        level="secondary",
        learner_profile_id="lp1",
        pain_points=[
            PainPoint(
                description="No reasoning shown",
                category=PainPointCategory.UNDERSTANDING,
            )
        ],
    )


def _opportunity(
    pid: str = "prob1", implied: list[LearningObjective] | None = None
) -> ProductOpportunity:
    return ProductOpportunity(
        id="opp1",
        problem_id=pid,
        title="Error Diagnosis Workbook",
        value_proposition="Shows the reasoning behind each wrong answer.",
        differentiation="Existing workbooks mark wrong; this explains the gap.",
        implied_outcomes=(
            implied
            if implied is not None
            else [LearningObjective(id="obj1", statement="Diagnose error causes")]
        ),
        feasibility=FeasibilityAssessment(
            level=FeasibilityLevel.HIGH, rationale="All components exist."
        ),
    )


def _market(pid: str = "prob1") -> MarketAnalysis:
    return MarketAnalysis(
        id="mkt1",
        problem_id=pid,
        segments=[MarketSegment.SCHOOL],
        primary_segment=MarketSegment.SCHOOL,
    )


def _outcomes(
    prob_id: str = "prob1", objectives: list[LearningObjective] | None = None
) -> OutcomeDefinition:
    return OutcomeDefinition(
        id="out1",
        problem_id=prob_id,
        outcomes=(
            objectives
            if objectives is not None
            else [LearningObjective(id="obj1", statement="Diagnose error causes")]
        ),
    )


def _brief(
    outcome_ids: list[str] | None = None,
    problem_id: str = "prob1",
) -> DiscoveryBrief:
    return DiscoveryBrief(
        problem_id=problem_id,
        outcome_ids=outcome_ids if outcome_ids is not None else ["obj1"],
        opportunity_id="opp1",
        market_analysis_id="mkt1",
        summary="Learners need to see reasoning behind wrong answers.",
    )


# ---------------------------------------------------------------------------
# check_discovery_chain
# ---------------------------------------------------------------------------


class TestCheckDiscoveryChain:
    def test_ok_path(self) -> None:
        result = check_discovery_chain(_problem(), _opportunity(), _market())
        assert is_ok(result)

    def test_opportunity_wrong_problem(self) -> None:
        result = check_discovery_chain(_problem(), _opportunity(pid="other"), _market())
        assert is_err(result)
        assert result.error.code == "DISCOVERY_CHAIN_MISMATCH"

    def test_market_wrong_problem(self) -> None:
        result = check_discovery_chain(_problem(), _opportunity(), _market(pid="other"))
        assert is_err(result)
        assert result.error.code == "DISCOVERY_CHAIN_MISMATCH"

    def test_both_wrong_problem(self) -> None:
        result = check_discovery_chain(
            _problem(), _opportunity(pid="other"), _market(pid="another")
        )
        assert is_err(result)
        details = result.error.details["mismatches"]
        assert len(details) == 2


# ---------------------------------------------------------------------------
# check_outcome_references
# ---------------------------------------------------------------------------


class TestCheckOutcomeReferences:
    def test_ok_path(self) -> None:
        result = check_outcome_references(_outcomes(), _opportunity())
        assert is_ok(result)

    def test_outcome_not_implied(self) -> None:
        outcome = _outcomes(
            objectives=[LearningObjective(id="obj9", statement="Untraceable outcome")]
        )
        result = check_outcome_references(outcome, _opportunity())
        assert is_err(result)
        assert result.error.code == "UNTRACEABLE_OUTCOMES"

    def test_no_implied_outcomes(self) -> None:
        result = check_outcome_references(_outcomes(), _opportunity(implied=[]))
        assert is_err(result)
        assert result.error.code == "NO_IMPLIED_OUTCOMES"

    def test_problem_mismatch(self) -> None:
        result = check_outcome_references(_outcomes(prob_id="other"), _opportunity())
        assert is_err(result)
        assert result.error.code == "OUTCOME_PROBLEM_MISMATCH"

    def test_partial_traceability_fails(self) -> None:
        objectives = [
            LearningObjective(id="obj1", statement="Diagnose error causes"),
            LearningObjective(id="obj9", statement="Invented scope"),
        ]
        result = check_outcome_references(_outcomes(objectives=objectives), _opportunity())
        assert is_err(result)
        assert len(result.error.details["missing"]) == 1


# ---------------------------------------------------------------------------
# check_discovery_brief
# ---------------------------------------------------------------------------


class TestCheckDiscoveryBrief:
    def test_ok_path(self) -> None:
        result = check_discovery_brief(_brief(), _problem(), _opportunity(), _market(), _outcomes())
        assert is_ok(result)

    def test_wrong_problem_reference(self) -> None:
        result = check_discovery_brief(
            _brief(problem_id="other"), _problem(), _opportunity(), _market(), _outcomes()
        )
        assert is_err(result)
        assert result.error.code == "BRIEF_REFERENCE_MISMATCH"

    def test_wrong_opportunity_reference(self) -> None:
        brief = _brief().model_copy(update={"opportunity_id": "nope"})
        result = check_discovery_brief(brief, _problem(), _opportunity(), _market(), _outcomes())
        assert is_err(result)

    def test_wrong_market_reference(self) -> None:
        brief = _brief().model_copy(update={"market_analysis_id": "nope"})
        result = check_discovery_brief(brief, _problem(), _opportunity(), _market(), _outcomes())
        assert is_err(result)

    def test_unknown_outcome_id(self) -> None:
        result = check_discovery_brief(
            _brief(outcome_ids=["obj1", "objX"]),
            _problem(),
            _opportunity(),
            _market(),
            _outcomes(),
        )
        assert is_err(result)
        assert result.error.code == "BRIEF_REFERENCE_MISMATCH"

    def test_multiple_mismatches_reported(self) -> None:
        brief = _brief(outcome_ids=["objX"]).model_copy(update={"market_analysis_id": "nope"})
        result = check_discovery_brief(brief, _problem(), _opportunity(), _market(), _outcomes())
        assert is_err(result)
        assert len(result.error.details["mismatches"]) == 2


# ---------------------------------------------------------------------------
# check_feasibility
# ---------------------------------------------------------------------------


class TestCheckFeasibility:
    def test_high_feasibility_actionable(self) -> None:
        result = check_feasibility(True, _opportunity())
        assert is_ok(result)

    def test_high_feasibility_not_actionable(self) -> None:
        result = check_feasibility(False, _opportunity())
        assert is_ok(result)

    @pytest.mark.parametrize("level", [FeasibilityLevel.LOW, FeasibilityLevel.MEDIUM])
    def test_non_blocked_levels_pass(self, level: FeasibilityLevel) -> None:
        opp = _opportunity().model_copy(
            update={
                "feasibility": FeasibilityAssessment(level=level, rationale="Doable with effort.")
            }
        )
        result = check_feasibility(True, opp)
        assert is_ok(result)

    def test_blocked_and_actionable_is_error(self) -> None:
        opp = _opportunity().model_copy(
            update={
                "feasibility": FeasibilityAssessment(
                    level=FeasibilityLevel.BLOCKED,
                    rationale="Needs a simulation engine we do not have.",
                    blockers=["no simulation engine"],
                )
            }
        )
        result = check_feasibility(True, opp)
        assert is_err(result)
        assert result.error.code == "INFEASIBLE_PRODUCT"
        assert result.error.details["blockers"] == ["no simulation engine"]

    def test_blocked_and_not_actionable_is_ok(self) -> None:
        """A blocked product discovered deliberately is a finding, not a failure."""
        opp = _opportunity().model_copy(
            update={
                "feasibility": FeasibilityAssessment(
                    level=FeasibilityLevel.BLOCKED,
                    rationale="Out of scope by design.",
                    blockers=["out of scope"],
                )
            }
        )
        result = check_feasibility(False, opp)
        assert is_ok(result)
