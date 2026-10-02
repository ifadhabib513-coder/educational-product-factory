"""Research schemas — SearchResult, SearchPlan, ResearchReport, EvidenceMap."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from lpf.domain.artifact import ArtifactBase

# ---------------------------------------------------------------------------
# Search & Research
# ---------------------------------------------------------------------------


class SearchProvider(StrEnum):
    """Which search provider produced a result."""

    SEARXNG = "searxng"
    TAVILY = "tavily"
    ARXIV = "arxiv"
    WIKIMEDIA = "wikimedia"
    OFFICIAL = "official"
    MOCK = "mock"


class SourceAuthority(StrEnum):
    """Authority level of a source."""

    PRIMARY = "primary"
    INSTITUTIONAL = "institutional"
    ACADEMIC = "academic"
    EDUCATIONAL = "educational"
    TEXTBOOK = "textbook"
    SECONDARY = "secondary"
    GENERAL = "general"
    UNKNOWN = "unknown"


class SearchResult(BaseModel):
    """Normalized search result from any provider."""

    model_config = {"frozen": True, "extra": "forbid"}

    source_id: str
    title: str
    url: str
    snippet: str
    domain: str
    provider: SearchProvider
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    authority: SourceAuthority = SourceAuthority.UNKNOWN
    relevance_score: float = 0.0


class SearchQuery(BaseModel):
    """A single search query with strategy."""

    model_config = {"frozen": True, "extra": "forbid"}

    query: str
    provider: SearchProvider
    max_results: int = 10
    category: str | None = None


class SearchStrategy(BaseModel):
    """How to search for a research question."""

    model_config = {"frozen": True, "extra": "forbid"}

    use_web: bool = True
    use_academic: bool = False
    use_wikipedia: bool = False
    use_official: bool = False
    providers: list[SearchProvider] = Field(default_factory=list)
    queries: list[SearchQuery] = Field(default_factory=list)


class ResearchQuestion(BaseModel):
    """A decomposed research question."""

    model_config = {"frozen": True, "extra": "forbid"}

    question_id: str
    text: str
    topic: str
    strategy: SearchStrategy
    priority: int = 1


class ResearchPlan(ArtifactBase):
    """Root artifact: the complete research plan."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["research_plan"] = "research_plan"
    product_spec_id: str
    questions: list[ResearchQuestion] = Field(min_length=1)
    required_evidence: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


class EvidenceClaim(BaseModel):
    """A single evidence claim traced to sources."""

    model_config = {"frozen": True, "extra": "forbid"}

    claim_id: str
    claim: str
    source_ids: list[str] = Field(min_length=1)
    evidence_text: str
    confidence: float = 0.0
    claim_type: str = "factual"
    is_conflicting: bool = False
    notes: str | None = None


class VerifiedSource(BaseModel):
    """A source that has been verified."""

    model_config = {"frozen": True, "extra": "forbid"}

    source_id: str
    url: str
    title: str
    domain: str
    authority: SourceAuthority
    exists: bool = True
    accessible: bool = True
    relevant: bool = True
    duplicate_of: str | None = None
    metadata_plausible: bool = True
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = None


class ConflictReport(BaseModel):
    """Conflicting evidence found during research."""

    model_config = {"frozen": True, "extra": "forbid"}

    claim_ids: list[str]
    description: str
    severity: str = "info"


class KnowledgeGap(BaseModel):
    """An identified gap in available evidence."""

    model_config = {"frozen": True, "extra": "forbid"}

    topic: str
    description: str
    impact: str = "medium"


# ---------------------------------------------------------------------------
# Root artifacts
# ---------------------------------------------------------------------------


class AcademicEvidenceSet(ArtifactBase):
    """Root artifact: academic evidence collected."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["academic_evidence"] = "academic_evidence"
    research_question_id: str
    papers: list[dict] = Field(default_factory=list)
    claims: list[EvidenceClaim] = Field(default_factory=list)


class ResearchReport(ArtifactBase):
    """Root artifact: complete research output."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["research_report"] = "research_report"
    product_spec_id: str
    claims: list[EvidenceClaim] = Field(default_factory=list)
    verified_sources: list[VerifiedSource] = Field(default_factory=list)
    conflicts: list[ConflictReport] = Field(default_factory=list)
    knowledge_gaps: list[KnowledgeGap] = Field(default_factory=list)


class EvidenceMap(ArtifactBase):
    """Root artifact: structured evidence graph for content generation."""

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_type: Literal["evidence_map"] = "evidence_map"
    research_report_id: str
    claims: list[EvidenceClaim] = Field(default_factory=list)
    total_claims: int = 0
    supported_claims: int = 0
    conflicting_claims: int = 0
    confidence_threshold: float = 0.7
