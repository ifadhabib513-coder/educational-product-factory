"""Benchmark: Beginner Definition Retrieval.

Query: "What is linear algebra?"
Expected: an introductory, on-topic source outranks a specialist research paper.
Failure: a specialist academic source outranks a clearly suitable introductory
source *solely because of authority*.

This benchmark exists because token-overlap relevance scored both sources at
1.0, and the old authority-first formula then handed rank 1 to the specialist
paper. It is a standing regression guard, not a one-off check.
"""

from __future__ import annotations

import pytest

from lpf.research.audience import AudienceLevel
from lpf.research.intent import QueryIntent, classify_intent
from lpf.research.pipeline import PipelineConfig, ResearchPipeline
from lpf.research.providers.base import MockSearchProvider
from lpf.research.router import ResearchRouter
from lpf.research.scoring import (
    clarity,
    confidence,
    intent_match,
    ranking_score,
    specialist_density,
)
from lpf.schemas.research import (
    ResearchQuestion,
    SearchProvider,
    SearchQuery,
    SearchResult,
    SearchStrategy,
    SourceAuthority,
)

QUERY = "What is linear algebra?"

INTRODUCTORY = SearchResult(
    source_id="intro",
    title="Linear algebra",
    url="https://en.wikipedia.org/wiki/Linear_algebra",
    snippet=(
        "Linear algebra is the branch of mathematics concerning linear equations, "
        "linear maps and their representations in matrices and vector spaces."
    ),
    domain="en.wikipedia.org",
    provider=SearchProvider.WIKIMEDIA,
    authority=SourceAuthority.SECONDARY,
    relevance_score=1.0,
)

SPECIALIST = SearchResult(
    source_id="specialist",
    title="Non-linear positive maps between C*-algebras",
    url="https://arxiv.org/abs/1811.03128",
    snippet=(
        "We present some properties of (not necessarily linear) positive maps between "
        "$\\mathcal{A}$ and $\\mathcal{B}$, a topic in functional analysis."
    ),
    domain="arxiv.org",
    provider=SearchProvider.ARXIV,
    authority=SourceAuthority.ACADEMIC,
    relevance_score=1.0,
)


def _service(router: ResearchRouter):
    from lpf.research.service import ResearchService

    return ResearchService(router)


def _pipeline(results: list[SearchResult]) -> ResearchPipeline:
    return ResearchPipeline(
        _service(
            ResearchRouter(providers={SearchProvider.MOCK: MockSearchProvider(results=results)})
        ),
        PipelineConfig(audience_level=AudienceLevel.BEGINNER),
    )


_INTRO_TEXT = (INTRODUCTORY.title, INTRODUCTORY.snippet)
_SPECIALIST_TEXT = (SPECIALIST.title, SPECIALIST.snippet)


def _definitional_authority_fit(result: SearchResult) -> float:
    from lpf.research.intent import authority_fit

    return authority_fit(QueryIntent.DEFINITIONAL, result.authority)


def _question() -> ResearchQuestion:
    return ResearchQuestion(
        question_id="q1",
        text=QUERY,
        topic="linear algebra",
        strategy=SearchStrategy(
            providers=[SearchProvider.MOCK],
            queries=[SearchQuery(query=QUERY, provider=SearchProvider.MOCK)],
        ),
    )


class TestBenchmarkConditions:
    """The preconditions that made this benchmark fail in the first place."""

    def test_query_is_classified_as_definitional(self) -> None:
        assert classify_intent(QUERY) is QueryIntent.DEFINITIONAL

    def test_token_overlap_alone_cannot_separate_the_sources(self) -> None:
        """Both sources score 1.0 on lexical relevance.

        This is the reason a cue-aware ``intent_match`` exists. If a future
        change makes raw relevance separate them, this test fails and the
        benchmark's original diagnosis needs revisiting.
        """
        from lpf.research.relevance import lexical_relevance

        intro = lexical_relevance(QUERY, INTRODUCTORY.title, INTRODUCTORY.snippet)
        specialist = lexical_relevance(QUERY, SPECIALIST.title, SPECIALIST.snippet)
        assert intro == specialist == 1.0

    def test_definition_cue_separates_the_sources(self) -> None:
        from lpf.research.scoring import has_definition_cue

        assert has_definition_cue(INTRODUCTORY.title, INTRODUCTORY.snippet) is True
        assert has_definition_cue(SPECIALIST.title, SPECIALIST.snippet) is False

    def test_intent_match_prefers_the_definitional_source(self) -> None:
        intent = QueryIntent.DEFINITIONAL
        intro = intent_match(INTRODUCTORY, QUERY, intent)
        specialist = intent_match(SPECIALIST, QUERY, intent)
        assert intro > specialist

    def test_specialist_text_scores_lower_clarity_for_beginners(self) -> None:
        assert clarity(*_INTRO_TEXT) > clarity(*_SPECIALIST_TEXT)

    def test_specialist_text_has_higher_notation_density(self) -> None:
        assert specialist_density(*_INTRO_TEXT) < specialist_density(*_SPECIALIST_TEXT)


class TestBenchmarkExpectation:
    """The failure condition, stated as an assertion."""

    def test_introductory_source_outranks_specialist_paper(self) -> None:
        kwargs = {
            "query": QUERY,
            "intent": QueryIntent.DEFINITIONAL,
            "audience": AudienceLevel.BEGINNER,
            "newest": 0.0,
            "oldest": 0.0,
        }
        intro = ranking_score(INTRODUCTORY, **kwargs)
        specialist = ranking_score(SPECIALIST, **kwargs)
        assert intro > specialist, (
            f"benchmark failure: introductory source scored {intro:.4f} but "
            f"specialist paper scored {specialist:.4f}"
        )

    def test_authority_alone_would_have_given_the_wrong_answer(self) -> None:
        """Pins the reason the benchmark exists.

        Flat authority rank does prefer the specialist paper; only
        intent-conditioned authority reverses it.
        """
        from lpf.research.authority import authority_rank

        assert authority_rank(SPECIALIST.authority) > authority_rank(INTRODUCTORY.authority)
        assert _definitional_authority_fit(SPECIALIST) < _definitional_authority_fit(INTRODUCTORY)


class TestEvidenceConfidenceUnaffected:
    """Confidence must stay comparable across intents.

    If an intent profile were allowed to change confidence, a definitional query
    could silently produce an empty EvidenceMap.
    """

    def test_definitional_source_is_confidently_supported(self) -> None:
        c = confidence(INTRODUCTORY, query=QUERY, intent=QueryIntent.DEFINITIONAL)
        assert c >= 0.7

    def test_specialist_source_is_not_confidently_supported_for_a_definition(self) -> None:
        c = confidence(SPECIALIST, query=QUERY, intent=QueryIntent.DEFINITIONAL)
        assert c < 0.7


@pytest.mark.asyncio
async def test_pipeline_end_to_end_ranks_introductory_first() -> None:
    provider = MockSearchProvider(results=[SPECIALIST, INTRODUCTORY])
    router = ResearchRouter(providers={SearchProvider.MOCK: provider})
    pipeline = ResearchPipeline(
        _service(router), PipelineConfig(audience_level=AudienceLevel.BEGINNER)
    )

    outcome = await pipeline.run("spec-bench", [_question()])

    assert len(outcome.results) == 2
    assert outcome.results[0].source_id == "intro", (
        "benchmark failure through the full pipeline: "
        f"ranked {[r.source_id for r in outcome.results]}"
    )


@pytest.mark.asyncio
async def test_pipeline_still_supports_claims_for_definitional_query() -> None:
    """The ranking change must not re-empty the EvidenceMap."""
    provider = MockSearchProvider(results=[SPECIALIST, INTRODUCTORY])
    router = ResearchRouter(providers={SearchProvider.MOCK: provider})
    pipeline = ResearchPipeline(
        _service(router), PipelineConfig(audience_level=AudienceLevel.BEGINNER)
    )

    outcome = await pipeline.run("spec-bench", [_question()])
    evidence_map = pipeline.to_evidence_map(outcome.report)

    assert evidence_map.supported_claims >= 1
