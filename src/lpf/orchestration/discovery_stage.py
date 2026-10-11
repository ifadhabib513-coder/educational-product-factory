"""Discovery and specification stages.

Turns a raw caller request into the structured artifacts the rest of the factory
reads: who the learner is, what problem they have, what success looks like, the
product opportunity, and the product specification.

This is the deterministic offline implementation of the Discovery crew. The crew
contracts in ``lpf.crews.discovery`` describe the same responsibilities for the
model-backed path; the artifact shapes are identical, so a later version can swap
the implementation without changing anything downstream. See ADR-008.
"""

from __future__ import annotations

from dataclasses import dataclass

from lpf.domain.identity import with_content_hash
from lpf.domain.learner import LearnerProfile
from lpf.domain.objectives import BloomLevel, LearningObjective
from lpf.domain.product import (
    ConstraintsSpec,
    FormatSpec,
    LearningSpec,
    ProductSpec,
    ProductType,
    QualitySpec,
    TargetAudience,
)
from lpf.orchestration.context import RunContext
from lpf.schemas.discovery import (
    DiscoveryBrief,
    DiscoveryInputs,
    FeasibilityAssessment,
    FeasibilityLevel,
    MarketAnalysis,
    MarketSegment,
    OutcomeDefinition,
    PainPoint,
    PainPointCategory,
    ProblemBarrier,
    ProblemDefinition,
    ProblemScope,
    ProblemUrgency,
    ProductOpportunity,
)

# Required format defaults for the offline run. A real run would derive these
# from the problem and audience; kept explicit so the output is inspectable.
_DEFAULT_FORMAT = ProductType.LEARNING_SYSTEM


def _topic(inputs: DiscoveryInputs) -> str:
    """Best available short topic for prompts and titles.

    Falls back through request → subject → a neutral placeholder, so nothing later
    has to handle an empty string.
    """
    if inputs.subject:
        return inputs.subject
    first_line = inputs.request.strip().splitlines()[0] if inputs.request.strip() else ""
    return first_line[:80] or "the requested topic"


@dataclass(frozen=True)
class DiscoveryBundle:
    """Everything the Discovery stage produces."""

    learner: LearnerProfile
    problem: ProblemDefinition
    outcomes: OutcomeDefinition
    opportunity: ProductOpportunity
    market: MarketAnalysis
    brief: DiscoveryBrief


@dataclass(frozen=True)
class SpecificationBundle:
    """The ProductSpec plus the framing it was derived from."""

    spec: ProductSpec


def build_discovery(ctx: RunContext, inputs: DiscoveryInputs) -> DiscoveryBundle:
    """Construct the six Discovery artifacts deterministically from the request."""
    topic = _topic(inputs)
    level = inputs.level or "unspecified"
    constraints = list(inputs.constraints)

    learner = with_content_hash(
        LearnerProfile(
            id=ctx.id("learner"),
            created_at=ctx.now(),
            subject=inputs.subject or topic,
            level=level,
            goals=[f"Understand {topic} well enough to use it"],
            challenges=[f"Existing explanations of {topic} assume more than the learner has"],
            constraints=constraints,
        )
    )

    problem = with_content_hash(
        ProblemDefinition(
            id=ctx.id("problem"),
            created_at=ctx.now(),
            parent_id=learner.id,
            statement=inputs.request.strip(),
            subject=inputs.subject or topic,
            level=level,
            learner_profile_id=learner.id,
            pain_points=[
                PainPoint(
                    description=f"The learner cannot yet explain {topic} in their own words.",
                    category=PainPointCategory.UNDERSTANDING,
                    learner_voice=f"I keep reading about {topic} but it does not stick.",
                )
            ],
            barriers=[
                ProblemBarrier(
                    description=f"No worked example of {topic} at the learner's level.",
                    barrier_type="missing_scaffolding",
                )
            ],
            urgency=ProblemUrgency.MEDIUM,
            scope=ProblemScope.FOCUSED,
        )
    )

    objectives = [
        LearningObjective(
            id=ctx.id("objective"),
            created_at=ctx.now(),
            statement=f"Explain what {topic} is and why it matters.",
            bloom_level=BloomLevel.UNDERSTAND,
            mastery_criteria=f"Can define {topic} and give one example without notes.",
        ),
        LearningObjective(
            id=ctx.id("objective"),
            created_at=ctx.now(),
            statement=f"Apply {topic} to a standard problem.",
            bloom_level=BloomLevel.APPLY,
            mastery_criteria=f"Can complete a worked problem on {topic} with no hints.",
        ),
    ]
    outcomes = with_content_hash(
        OutcomeDefinition(
            id=ctx.id("outcomes"),
            created_at=ctx.now(),
            parent_id=problem.id,
            problem_id=problem.id,
            outcomes=objectives,
            target_bloom_level=BloomLevel.APPLY,
            mastery_criteria="Both objectives met without scaffolding.",
        )
    )

    opportunity = with_content_hash(
        ProductOpportunity(
            id=ctx.id("opportunity"),
            created_at=ctx.now(),
            parent_id=problem.id,
            problem_id=problem.id,
            title=f"{topic}: A Self-Study Learning System",
            value_proposition=(
                f"Teaches {topic} from the learner's current level with worked examples, "
                "practice, and sourced explanations."
            ),
            differentiation=(
                f"Unlike a generic textbook chapter on {topic}, every explanation is "
                "written for the stated level and checked against cited sources."
            ),
            implied_outcomes=objectives,
            segment=MarketSegment.SELF_LEARNER,
            feasibility=FeasibilityAssessment(
                level=FeasibilityLevel.HIGH,
                rationale="Subject-agnostic structure with no special-case dependencies.",
            ),
            product_suite_hint=["core_guide", "workbook", "answer_key"],
        )
    )

    market = with_content_hash(
        MarketAnalysis(
            id=ctx.id("market"),
            created_at=ctx.now(),
            parent_id=problem.id,
            problem_id=problem.id,
            segments=[MarketSegment.SELF_LEARNER],
            primary_segment=MarketSegment.SELF_LEARNER,
            gaps=[f"Few sources explain {topic} without assuming prior coursework."],
            confidence=0.5,
        )
    )

    brief = with_content_hash(
        DiscoveryBrief(
            id=ctx.id("brief"),
            created_at=ctx.now(),
            problem_id=problem.id,
            outcome_ids=[outcomes.id],
            opportunity_id=opportunity.id,
            market_analysis_id=market.id,
            summary=(
                f"Build a learning system that teaches {topic} to a "
                f"{level} learner, from definition through application."
            ),
            recommended_format=_DEFAULT_FORMAT.value,
            priority_topics=[topic],
            research_questions=[
                f"What is {topic}?",
                f"What are the core ideas a beginner must understand about {topic}?",
                f"What common mistakes do learners make with {topic}?",
            ],
            source_refs=[problem.id, outcomes.id, opportunity.id, market.id],
        )
    )

    return DiscoveryBundle(
        learner=learner,
        problem=problem,
        outcomes=outcomes,
        opportunity=opportunity,
        market=market,
        brief=brief,
    )


def build_specification(
    ctx: RunContext,
    inputs: DiscoveryInputs,
    discovery: DiscoveryBundle,
) -> SpecificationBundle:
    """Turn the Discovery brief into the ProductSpec the factory builds against."""
    topic = _topic(inputs)
    spec = with_content_hash(
        ProductSpec(
            id=ctx.id("spec"),
            created_at=ctx.now(),
            parent_id=discovery.brief.id,
            title=discovery.opportunity.title,
            product_type=_DEFAULT_FORMAT,
            subject=discovery.problem.subject,
            topic=topic,
            audience=TargetAudience(level=discovery.learner.level),
            format=FormatSpec(primary=_DEFAULT_FORMAT, include_citations=True),
            learning=LearningSpec(
                progression=["understand", "apply"],
                mastery_criteria=discovery.outcomes.mastery_criteria,
                bloom_target=BloomLevel.APPLY,
            ),
            constraints=ConstraintsSpec(evidence_required=True, citation_required=True),
            quality=QualitySpec(minimum_score=0.8, required_gates=[]),
            problem_statement=discovery.problem.statement,
            learner_profile_id=discovery.learner.id,
            source_refs=[discovery.brief.id, discovery.outcomes.id],
        )
    )
    return SpecificationBundle(spec=spec)
