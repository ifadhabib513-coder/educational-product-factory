"""Validation for Discovery artifacts — referential and structural integrity."""

from __future__ import annotations

from lpf.errors import ValidationError
from lpf.result import Result, err, ok
from lpf.schemas.discovery import (
    DiscoveryBrief,
    FeasibilityLevel,
    MarketAnalysis,
    OutcomeDefinition,
    ProblemDefinition,
    ProductOpportunity,
)


def check_discovery_chain(
    problem: ProblemDefinition,
    opportunity: ProductOpportunity,
    market: MarketAnalysis,
) -> Result[DiscoveryBrief, ValidationError]:
    """Verify the three discovery artifacts reference one another correctly.

    All three are keyed to ``problem_id``. A mismatch means a stage was run
    against a different problem than the one in hand, which silently invalidates
    every downstream artifact.
    """
    mismatches: list[dict[str, str]] = []

    if opportunity.problem_id != problem.id:
        mismatches.append(
            {
                "artifact": "product_opportunity",
                "expected_problem_id": problem.id,
                "actual_problem_id": opportunity.problem_id,
            }
        )

    if market.problem_id != problem.id:
        mismatches.append(
            {
                "artifact": "market_analysis",
                "expected_problem_id": problem.id,
                "actual_problem_id": market.problem_id,
            }
        )

    if mismatches:
        return err(
            ValidationError(
                code="DISCOVERY_CHAIN_MISMATCH",
                message=(f"Discovery artifacts reference {len(mismatches)} different problem(s)"),
                details={"mismatches": mismatches},
            )
        )

    return ok(problem.id)


def check_outcome_references(
    outcomes: OutcomeDefinition,
    opportunity: ProductOpportunity,
) -> Result[OutcomeDefinition, ValidationError]:
    """Verify outcomes trace back to the opportunity that implied them.

    Every outcome must appear in the opportunity's ``implied_outcomes``. An
    outcome nobody implied is scope the Product Strategist never agreed to.
    """
    implied_ids = {o.id for o in opportunity.implied_outcomes}

    if not implied_ids:
        return err(
            ValidationError(
                code="NO_IMPLIED_OUTCOMES",
                message="Opportunity declares no implied outcomes to validate against",
                details={"opportunity_id": opportunity.id},
            )
        )

    if outcomes.problem_id != opportunity.problem_id:
        return err(
            ValidationError(
                code="OUTCOME_PROBLEM_MISMATCH",
                message="Outcome definition targets a different problem than the opportunity",
                details={
                    "outcome_problem_id": outcomes.problem_id,
                    "opportunity_problem_id": opportunity.problem_id,
                },
            )
        )

    missing = [
        {"outcome_id": o.id, "statement": o.statement}
        for o in outcomes.outcomes
        if o.id not in implied_ids
    ]

    if missing:
        return err(
            ValidationError(
                code="UNTRACEABLE_OUTCOMES",
                message=f"{len(missing)} outcome(s) not implied by the opportunity",
                details={"missing": missing},
            )
        )

    return ok(outcomes)


def check_discovery_brief(
    brief: DiscoveryBrief,
    problem: ProblemDefinition,
    opportunity: ProductOpportunity,
    market: MarketAnalysis,
    outcomes: OutcomeDefinition,
) -> Result[DiscoveryBrief, ValidationError]:
    """Verify the brief's five references resolve to the artifacts in hand."""
    known = {
        "problem_id": problem.id,
        "opportunity_id": opportunity.id,
        "market_analysis_id": market.id,
    }

    mismatches: list[dict[str, str]] = []
    for field, actual in known.items():
        referenced = getattr(brief, field)
        if referenced != actual:
            mismatches.append({"field": field, "expected": actual, "actual": referenced})

    outcome_ids = {o.id for o in outcomes.outcomes}
    for outcome_id in brief.outcome_ids:
        if outcome_id not in outcome_ids:
            mismatches.append(
                {
                    "field": "outcome_ids",
                    "expected": outcome_id,
                    "actual": "(not in outcome definition)",
                }
            )

    if mismatches:
        return err(
            ValidationError(
                code="BRIEF_REFERENCE_MISMATCH",
                message=f"Discovery brief has {len(mismatches)} unresolved reference(s)",
                details={"mismatches": mismatches},
            )
        )

    return ok(brief)


def check_feasibility(
    actionable: bool, opportunity: ProductOpportunity
) -> Result[ProductOpportunity, ValidationError]:
    """Gate the run on whether the factory can actually build the product.

    ``actionable`` lets the caller distinguish a BLOCKED product that was never
    meant to be built from one discovered by mistake. A BLOCKED opportunity is
    only an error when it was supposed to be buildable.
    """
    if opportunity.feasibility.level is not FeasibilityLevel.BLOCKED:
        return ok(opportunity)

    if not actionable:
        return ok(opportunity)

    return err(
        ValidationError(
            code="INFEASIBLE_PRODUCT",
            message="Product is blocked and was expected to be buildable",
            details={
                "opportunity_id": opportunity.id,
                "rationale": opportunity.feasibility.rationale,
                "blockers": opportunity.feasibility.blockers,
            },
        )
    )
