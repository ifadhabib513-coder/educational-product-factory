"""Discovery schemas — problem framing, outcomes, and product opportunity.

Subject-agnostic by construction: nothing here names a discipline. A discovery
artifact describes a learner problem, the outcomes that would resolve it, and the
product opportunity those outcomes imply.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from lpf.domain.artifact import ArtifactBase
from lpf.domain.learner import LearnerProfile
from lpf.domain.objectives import BloomLevel, LearningObjective

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProblemUrgency(StrEnum):
    """How pressing the learner problem is."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProblemScope(StrEnum):
    """Breadth of the problem the product must address."""

    NARROW = "narrow"
    FOCUSED = "focused"
    BROAD = "broad"


class PainPointCategory(StrEnum):
    """Category of learner pain, independent of subject matter."""

    UNDERSTANDING = "understanding"
    RETENTION = "retention"
    APPLICATION = "application"
    MOTIVATION = "motivation"
    STRUCTURE = "structure"
    ASSESSMENT = "assessment"
    CONFIDENCE = "confidence"


class MarketSegment(StrEnum):
    """Who the product is sold to."""

    SELF_LEARNER = "self_learner"
    SCHOOL = "school"
    UNIVERSITY = "university"
    PROFESSIONAL = "professional"
    PARENT = "parent"
    CORPORATE = "corporate"


class FeasibilityLevel(StrEnum):
    """How buildable the product is by this factory."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


class PainPoint(BaseModel):
    """A specific, learner-voiced difficulty.

    ``learner_voice`` should preserve the learner's own words. Framing a problem
    in the learner's language is what keeps later content readable at their level.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    description: str
    category: PainPointCategory
    learner_voice: str | None = None
    frequency: str | None = None
    severity: str | None = None


class ProblemBarrier(BaseModel):
    """An obstacle standing between the learner and the desired outcome."""

    model_config = {"frozen": True, "extra": "forbid"}

    description: str
    barrier_type: str
    addressed_by: list[str] = Field(default_factory=list)


class CompetitorProfile(BaseModel):
    """An existing product addressing the same problem."""

    model_config = {"frozen": True, "extra": "forbid"}

    name: str
    kind: str
    url: str | None = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    price_point: str | None = None


class MarketSignal(BaseModel):
    """Observed evidence that a market exists for the problem."""

    model_config = {"frozen": True, "extra": "forbid"}

    description: str
    source_url: str | None = None
    signal_type: str
    strength: str | None = None


class FeasibilityAssessment(BaseModel):
    """Whether the factory can build this, and what would block it."""

    model_config = {"frozen": True, "extra": "forbid"}

    level: FeasibilityLevel
    rationale: str
    blockers: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Root artifacts
# ---------------------------------------------------------------------------


class ProblemDefinition(ArtifactBase):
    """Root artifact: the learner problem, stated precisely.

    Output of the Learner Researcher. This is the problem the whole factory
    exists to solve; every downstream stage traces back to it.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["problem_definition"] = "problem_definition"

    statement: str
    subject: str
    level: str
    learner_profile_id: str

    pain_points: list[PainPoint] = Field(min_length=1)
    barriers: list[ProblemBarrier] = Field(default_factory=list)

    urgency: ProblemUrgency = ProblemUrgency.MEDIUM
    scope: ProblemScope = ProblemScope.FOCUSED

    evidence_source_ids: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class OutcomeDefinition(ArtifactBase):
    """Root artifact: what success looks like once the problem is resolved.

    Each outcome names the observable change, the Bloom level it targets, and
    how mastery will be judged. Outcomes are the contract the curriculum and
    assessment crews must satisfy.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["outcome_definition"] = "outcome_definition"

    problem_id: str
    outcomes: list[LearningObjective] = Field(min_length=1)
    target_bloom_level: BloomLevel | None = None
    mastery_criteria: str | None = None
    assessment_strategy: str | None = None


class ProductOpportunity(ArtifactBase):
    """Root artifact: the product the problem and outcomes imply.

    Output of the Product Strategist. Names the product shape, who it serves,
    why it is differentiated, and whether the factory can actually build it.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["product_opportunity"] = "product_opportunity"

    problem_id: str

    title: str
    value_proposition: str
    differentiation: str

    implied_outcomes: list[LearningObjective] = Field(default_factory=list)

    segment: MarketSegment = MarketSegment.SELF_LEARNER
    feasibility: FeasibilityAssessment
    product_suite_hint: list[str] = Field(default_factory=list)

    competitor_ids: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class MarketAnalysis(ArtifactBase):
    """Root artifact: market context for the problem and product.

    Output of the Market Analyst. Kept separate from the opportunity itself so
    a weak market read can be revised without discarding product reasoning.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["market_analysis"] = "market_analysis"

    problem_id: str
    segments: list[MarketSegment] = Field(min_length=1)
    primary_segment: MarketSegment

    signals: list[MarketSignal] = Field(default_factory=list)
    competitors: list[CompetitorProfile] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_ids: list[str] = Field(default_factory=list)


class DiscoveryBrief(ArtifactBase):
    """Root artifact: the Discovery crew's combined handoff to the next stage.

    Aggregates problem, outcomes, opportunity, and market analysis into the single
    artifact the Research crew consumes. Reference-only: it carries IDs, not
    copied bodies, so the artifacts of record cannot drift apart.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["discovery_brief"] = "discovery_brief"

    problem_id: str
    outcome_ids: list[str] = Field(min_length=1)
    opportunity_id: str
    market_analysis_id: str

    summary: str
    recommended_format: str | None = None
    priority_topics: list[str] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list)


class DiscoveryInputs(BaseModel):
    """The raw request that starts the Discovery crew.

    Not an artifact: this is caller-supplied intent, free to be partial or vague.
    The crew's job is to turn it into structured artifacts.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    request: str
    subject: str | None = None
    level: str | None = None
    learner_profile: LearnerProfile | None = None
    constraints: list[str] = Field(default_factory=list)
