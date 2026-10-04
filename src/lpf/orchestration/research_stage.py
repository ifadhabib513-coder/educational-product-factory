"""Research stage — runs the real ResearchPipeline against a deterministic provider.

The pipeline itself is production code (ADR-006/007); only the search provider is
swapped for an offline one. That is the point: the offline run exercises the real
dedupe, filter, rank, claim, conflict and evidence-map logic end to end.

Normalisation note: ``ResearchPipeline.run`` stamps report and evidence-map ids
with ``uuid4`` and sources with ``datetime.now``. Those are the only two
nondeterministic values in the whole research stage, so this module rewrites them
from the ``RunContext`` before hashing. Without this the run would not be
reproducible — see ADR-008.
"""

from __future__ import annotations

from dataclasses import dataclass

from lpf.domain.identity import with_content_hash
from lpf.orchestration.context import RunContext
from lpf.research.audience import AudienceLevel
from lpf.research.pipeline import PipelineConfig, PipelineResult, ResearchPipeline
from lpf.research.router import ResearchRouter
from lpf.research.service import ResearchService
from lpf.schemas.research import (
    EvidenceMap,
    ResearchPlan,
    ResearchQuestion,
    ResearchReport,
    SearchProvider,
    SearchQuery,
    SearchResult,
    SearchStrategy,
    SourceAuthority,
)


@dataclass(frozen=True)
class ResearchBundle:
    """Everything the Research stage produces."""

    plan: ResearchPlan
    report: ResearchReport
    evidence_map: EvidenceMap
    results: tuple[SearchResult, ...]
    duplicates_removed: int
    dropped_low_authority: int
    dropped_thin: int


class DeterministicSearchProvider:
    """A search provider whose results are a pure function of the query.

    Distinct queries yield distinct sources, so the pipeline's dedupe and claim
    mapping do real work instead of collapsing a single repeated result.
    """

    provider_name: SearchProvider = SearchProvider.MOCK

    def __init__(self, ctx: RunContext, *, results_per_query: int = 2) -> None:
        self._ctx = ctx
        self._results_per_query = results_per_query

    async def search(self, query: str, *, max_results: int = 10) -> list[SearchResult]:
        return [
            self._make_result(query, rank)
            for rank in range(min(self._results_per_query, max_results))
        ]

    async def extract(self, url: str) -> str:
        return f"Extracted content for {url}."

    def _make_result(self, query: str, rank: int) -> SearchResult:
        slug = query.lower().replace(" ", "-")[:40].strip("-") or "topic"
        return SearchResult(
            source_id=self._ctx.id("source"),
            title=f"{query.rstrip('?')} (reference {rank + 1})",
            url=f"https://reference.example/{slug}/{rank + 1}",
            snippet=(
                f"{query.rstrip('?')} is defined here in plain language for the stated "
                f"learner level, with one worked example and a note on the common mistake."
            ),
            domain="reference.example",
            provider=SearchProvider.MOCK,
            retrieved_at=self._ctx.now(),
            authority=SourceAuthority.SECONDARY,
            relevance_score=0.9,
        )


def _build_plan(
    ctx: RunContext, product_spec_id: str, questions_text: list[str], topic: str
) -> ResearchPlan:
    questions = [
        ResearchQuestion(
            question_id=ctx.id("rq"),
            text=text,
            topic=topic,
            strategy=SearchStrategy(
                use_web=True,
                providers=[SearchProvider.MOCK],
                queries=[SearchQuery(query=text, provider=SearchProvider.MOCK)],
            ),
        )
        for text in questions_text
    ]
    return with_content_hash(
        ResearchPlan(
            id=ctx.id("research_plan"),
            created_at=ctx.now(),
            product_spec_id=product_spec_id,
            questions=questions,
            required_evidence=[topic],
        )
    )


def _normalise_report(ctx: RunContext, report: ResearchReport) -> ResearchReport:
    """Replace pipeline-generated ids and timestamps with deterministic ones."""
    verified = [
        source.model_copy(update={"verified_at": ctx.now()}) for source in report.verified_sources
    ]
    frozen = report.model_copy(
        update={
            "id": ctx.id("research_report"),
            "created_at": ctx.now(),
            "verified_sources": verified,
        }
    )
    return with_content_hash(frozen)


def _normalise_evidence_map(
    ctx: RunContext, evidence_map: EvidenceMap, report: ResearchReport
) -> EvidenceMap:
    frozen = evidence_map.model_copy(
        update={
            "id": ctx.id("evidence_map"),
            "created_at": ctx.now(),
            "research_report_id": report.id,
        }
    )
    return with_content_hash(frozen)


async def build_research(
    ctx: RunContext,
    *,
    product_spec_id: str,
    research_questions: list[str],
    topic: str,
    audience: AudienceLevel = AudienceLevel.INTERMEDIATE,
) -> ResearchBundle:
    """Run the real research pipeline over the deterministic offline provider."""
    plan = _build_plan(ctx, product_spec_id, research_questions, topic)

    provider = DeterministicSearchProvider(ctx)
    service = ResearchService(ResearchRouter(providers={SearchProvider.MOCK: provider}))
    pipeline = ResearchPipeline(service, PipelineConfig(audience_level=audience))

    result: PipelineResult = await pipeline.run(
        product_spec_id, list(plan.questions), run_id=ctx.run_id
    )

    report = _normalise_report(ctx, result.report)
    evidence_map = _normalise_evidence_map(ctx, pipeline.to_evidence_map(report), report)

    return ResearchBundle(
        plan=plan,
        report=report,
        evidence_map=evidence_map,
        results=tuple(result.results),
        duplicates_removed=result.duplicates_removed,
        dropped_low_authority=result.dropped_low_authority,
        dropped_thin=result.dropped_thin,
    )
