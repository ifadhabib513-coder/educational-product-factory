"""Tests for the deterministic research pipeline."""

from __future__ import annotations

import pytest

from lpf.research.audience import AudienceLevel
from lpf.research.intent import QueryIntent
from lpf.research.pipeline import (
    PipelineConfig,
    ResearchPipeline,
    canonical_url,
)
from lpf.research.providers.base import MockSearchProvider
from lpf.research.router import ResearchRouter
from lpf.research.service import ResearchService
from lpf.schemas.research import (
    ResearchQuestion,
    SearchProvider,
    SearchQuery,
    SearchResult,
    SearchStrategy,
    SourceAuthority,
)

_LONG = "This is a sufficiently long snippet to pass the thin-content filter."


def _result(
    source_id: str,
    url: str,
    *,
    authority: SourceAuthority = SourceAuthority.ACADEMIC,
    relevance: float = 0.8,
    snippet: str = _LONG,
) -> SearchResult:
    from lpf.research.authority import extract_domain

    return SearchResult(
        source_id=source_id,
        title=f"Title {source_id}",
        url=url,
        snippet=snippet,
        domain=extract_domain(url),
        provider=SearchProvider.MOCK,
        authority=authority,
        relevance_score=relevance,
    )


def _question(qid: str = "q1", text: str = "What is algebra?") -> ResearchQuestion:
    return ResearchQuestion(
        question_id=qid,
        text=text,
        topic="algebra",
        strategy=SearchStrategy(
            providers=[SearchProvider.MOCK],
            queries=[SearchQuery(query=text, provider=SearchProvider.MOCK)],
        ),
    )


def _pipeline(results: list[SearchResult], config: PipelineConfig | None = None):
    provider = MockSearchProvider(results=results)
    router = ResearchRouter(providers={SearchProvider.MOCK: provider})
    return ResearchPipeline(ResearchService(router), config or PipelineConfig())


# ---------------------------------------------------------------------------
# canonical_url
# ---------------------------------------------------------------------------


class TestCanonicalUrl:
    def test_strips_www(self) -> None:
        assert canonical_url("https://www.example.com/a") == "https://example.com/a"

    def test_lowercases_host(self) -> None:
        assert canonical_url("https://EXAMPLE.com/a") == "https://example.com/a"

    def test_strips_fragment(self) -> None:
        assert canonical_url("https://example.com/a#frag") == "https://example.com/a"

    def test_strips_trailing_slash(self) -> None:
        assert canonical_url("https://example.com/a/") == "https://example.com/a"

    def test_preserves_query(self) -> None:
        """For some providers the query string is the identifier, not a filter."""
        assert "id=7" in canonical_url("https://example.com/a?id=7")

    def test_keeps_root_path(self) -> None:
        assert canonical_url("https://example.com/") == "https://example.com/"

    def test_empty(self) -> None:
        assert canonical_url("") == ""

    def test_collapses_equivalent_forms(self) -> None:
        assert canonical_url("https://www.example.com/a/") == canonical_url(
            "https://example.com/a#x"
        )


# ---------------------------------------------------------------------------
# deduplicate
# ---------------------------------------------------------------------------


class TestDeduplicate:
    def test_identical_urls_collapse(self) -> None:
        pipeline = _pipeline([])
        results = [
            _result("s1", "https://arxiv.org/a"),
            _result("s2", "https://arxiv.org/a"),
        ]
        deduped, removed = pipeline.deduplicate(results)
        assert len(deduped) == 1
        assert removed == 1

    def test_variants_collapse(self) -> None:
        pipeline = _pipeline([])
        results = [
            _result("s1", "https://www.example.com/a/"),
            _result("s2", "https://example.com/a"),
        ]
        deduped, removed = pipeline.deduplicate(results)
        assert len(deduped) == 1
        assert removed == 1

    def test_distinct_urls_survive(self) -> None:
        pipeline = _pipeline([])
        results = [
            _result("s1", "https://arxiv.org/a"),
            _result("s2", "https://arxiv.org/b"),
        ]
        deduped, removed = pipeline.deduplicate(results)
        assert len(deduped) == 2
        assert removed == 0

    def test_higher_authority_copy_wins(self) -> None:
        """When two providers return the same page, keep the citable one."""
        pipeline = _pipeline([])
        results = [
            _result("s1", "https://example.com/a", authority=SourceAuthority.GENERAL),
            _result("s2", "https://example.com/a", authority=SourceAuthority.INSTITUTIONAL),
        ]
        deduped, _ = pipeline.deduplicate(results)
        assert deduped[0].source_id == "s2"

    def test_result_without_url_falls_back_to_id(self) -> None:
        pipeline = _pipeline([])
        results = [
            _result("s1", ""),
            _result("s2", ""),
        ]
        deduped, removed = pipeline.deduplicate(results)
        assert len(deduped) == 2
        assert removed == 0


# ---------------------------------------------------------------------------
# filtering
# ---------------------------------------------------------------------------


class TestFilterSources:
    def test_thin_snippets_dropped(self) -> None:
        pipeline = _pipeline([])
        results = [_result("s1", "https://arxiv.org/a", snippet="short")]
        kept, low_auth, thin = pipeline.filter_sources(results)
        assert kept == []
        assert thin == 1
        assert low_auth == 0

    def test_unknown_authority_dropped_by_default(self) -> None:
        pipeline = _pipeline([])
        results = [_result("s1", "https://unknown.example/a", authority=SourceAuthority.UNKNOWN)]
        kept, low_auth, thin = pipeline.filter_sources(results)
        assert kept == []
        assert low_auth == 1

    def test_general_authority_kept_by_default(self) -> None:
        pipeline = _pipeline([])
        results = [_result("s1", "https://quora.com/a", authority=SourceAuthority.GENERAL)]
        kept, _, _ = pipeline.filter_sources(results)
        assert len(kept) == 1

    def test_min_authority_rank_is_configurable(self) -> None:
        config = PipelineConfig(min_authority_rank=3)
        pipeline = _pipeline([], config)
        results = [
            _result("s1", "https://arxiv.org/a", authority=SourceAuthority.SECONDARY),
            _result("s2", "https://mit.edu/a", authority=SourceAuthority.INSTITUTIONAL),
        ]
        kept, _, _ = pipeline.filter_sources(results)
        assert len(kept) == 1


# ---------------------------------------------------------------------------
# ranking
# ---------------------------------------------------------------------------


class TestRanking:
    def test_higher_authority_ranks_first(self) -> None:
        pipeline = _pipeline([])
        results = [
            _result("low", "https://quora.com/a", authority=SourceAuthority.GENERAL, relevance=0.9),
            _result(
                "high", "https://mit.edu/a", authority=SourceAuthority.INSTITUTIONAL, relevance=0.5
            ),
        ]
        ranked = pipeline.rank(results)
        assert ranked[0].source_id == "high"

    def test_higher_relevance_breaks_close_ties(self) -> None:
        pipeline = _pipeline([])
        results = [
            _result(
                "a", "https://mit.edu/1", authority=SourceAuthority.INSTITUTIONAL, relevance=0.5
            ),
            _result(
                "b", "https://mit.edu/2", authority=SourceAuthority.INSTITUTIONAL, relevance=0.9
            ),
        ]
        ranked = pipeline.rank(results)
        assert ranked[0].source_id == "b"

    def test_authority_dominance_is_intent_conditional(self) -> None:
        """Authority can be made to dominate, but only by choosing an intent.

        The old model exposed ``authority_weight``/``relevance_weight`` knobs.
        Weighting is now a property of the intent profile rather than a global
        dial, so the equivalent control is ``intent_override``.
        """
        results = [
            _result("low", "https://quora.com/a", authority=SourceAuthority.GENERAL, relevance=1.0),
            _result(
                "high",
                "https://mit.edu/a",
                authority=SourceAuthority.INSTITUTIONAL,
                relevance=0.0,
            ),
        ]

        definition_first = _pipeline(
            results,
            PipelineConfig(intent_override=QueryIntent.DEFINITIONAL),
        )
        literature_first = _pipeline(
            results,
            PipelineConfig(intent_override=QueryIntent.ACADEMIC_LITERATURE),
        )

        assert literature_first.resolve_intent([]) is QueryIntent.ACADEMIC_LITERATURE
        assert definition_first.resolve_intent([]) is QueryIntent.DEFINITIONAL

    def test_audience_level_is_configurable(self) -> None:
        pipeline = _pipeline([], PipelineConfig())
        assert pipeline._config.audience_level is AudienceLevel.INTERMEDIATE
        assert (
            ResearchPipeline(
                _pipeline([], PipelineConfig())._service, audience="beginner"
            )._config.audience_level
            is AudienceLevel.BEGINNER
        )


# ---------------------------------------------------------------------------
# claims
# ---------------------------------------------------------------------------


class TestClaimBuilding:
    def test_one_claim_per_source(self) -> None:
        pipeline = _pipeline([])
        results = [_result("s1", "https://arxiv.org/a"), _result("s2", "https://arxiv.org/b")]
        claims = pipeline._build_claims(results)
        assert len(claims) == 2

    def test_claim_carries_source_reference(self) -> None:
        pipeline = _pipeline([])
        claims = pipeline._build_claims([_result("s1", "https://arxiv.org/a")])
        assert claims[0].source_ids == ["s1"]

    def test_thin_sources_produce_no_claim(self) -> None:
        pipeline = _pipeline([])
        claims = pipeline._build_claims([_result("s1", "https://arxiv.org/a", snippet="x")])
        assert claims == []

    def test_confidence_is_bounded(self) -> None:
        pipeline = _pipeline([])
        results = [
            _result(
                "s1", "https://mit.edu/a", authority=SourceAuthority.INSTITUTIONAL, relevance=1.0
            )
        ]
        claims = pipeline._build_claims(results)
        assert 0.0 <= claims[0].confidence <= 1.0


# ---------------------------------------------------------------------------
# conflict detection
# ---------------------------------------------------------------------------


class TestConflictDetection:
    def test_identical_claims_agree(self) -> None:
        pipeline = _pipeline([])
        claims = pipeline._build_claims(
            [
                _result("s1", "https://arxiv.org/a", snippet=_LONG),
                _result("s2", "https://arxiv.org/b", snippet=_LONG),
            ]
        )
        assert pipeline.detect_conflicts(claims) == []

    def test_unrelated_claims_agree(self) -> None:
        pipeline = _pipeline([])
        claims = pipeline._build_claims(
            [
                _result(
                    "s1", "https://arxiv.org/a", snippet="Algebra studies symbols and operations."
                ),
                _result(
                    "s2", "https://arxiv.org/b", snippet="Volcanology studies volcanic activity."
                ),
            ]
        )
        assert pipeline.detect_conflicts(claims) == []

    def test_polarly_opposite_claims_conflict(self) -> None:
        pipeline = _pipeline([])
        claims = pipeline._build_claims(
            [
                _result(
                    "s1",
                    "https://arxiv.org/a",
                    snippet="Spaced practice sessions are consistently more effective for long term retention.",
                ),
                _result(
                    "s2",
                    "https://arxiv.org/b",
                    snippet="Spaced practice sessions never improve long term retention under any conditions.",
                ),
            ]
        )
        conflicts = pipeline.detect_conflicts(claims)
        assert len(conflicts) == 1
        # Conflicts reference claim ids, which are generated, so match by source.
        assert {claims[0].claim_id, claims[1].claim_id} == set(conflicts[0].claim_ids)

    def test_single_claim_never_conflicts(self) -> None:
        pipeline = _pipeline([])
        claims = pipeline._build_claims([_result("s1", "https://arxiv.org/a")])
        assert pipeline.detect_conflicts(claims) == []

    def test_detector_is_conservative(self) -> None:
        """Over-reporting conflicts would send Revision chasing non-disagreements."""
        pipeline = _pipeline([])
        claims = pipeline._build_claims(
            [
                _result(
                    "s1", "https://arxiv.org/a", snippet="Learning requires practice and feedback."
                ),
                _result(
                    "s2", "https://arxiv.org/b", snippet="Practice improves learning outcomes."
                ),
            ]
        )
        assert pipeline.detect_conflicts(claims) == []


# ---------------------------------------------------------------------------
# gaps
# ---------------------------------------------------------------------------


class TestGapIdentification:
    def test_question_with_no_results_is_a_gap(self) -> None:
        pipeline = _pipeline([])
        gaps = pipeline.identify_gaps([_question("q1")], {"q1": []})
        assert len(gaps) == 1
        assert gaps[0].impact == "high"
        assert "algebra" in gaps[0].topic

    def test_question_with_results_is_not_a_gap(self) -> None:
        pipeline = _pipeline([])
        gaps = pipeline.identify_gaps(
            [_question("q1")], {"q1": [_result("s1", "https://arxiv.org/a")]}
        )
        assert gaps == []

    def test_missing_key_counts_as_gap(self) -> None:
        pipeline = _pipeline([])
        assert len(pipeline.identify_gaps([_question("q1")], {})) == 1


# ---------------------------------------------------------------------------
# full run
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# relevance derivation (live-smoke-test regression)
# ---------------------------------------------------------------------------


class TestRelevanceIsDerivedDuringRun:
    """Providers that report no relevance must still yield supportable claims.

    Live smoke testing found that only Tavily populates
    ``SearchResult.relevance_score``; arXiv, Wikimedia and SearXNG leave it at
    0.0. Claim confidence is ``authority * 0.4 + relevance * 0.6``, so a 0.0
    relevance caps an ACADEMIC source at 0.2857 -- permanently below the 0.7
    evidence-map threshold. The live pipeline produced 0/20 supported claims;
    after the fix it produces 13/20.

    These tests drive ``run()`` rather than calling ``_derive_relevance``
    directly, because wiring the call into ``run()`` is exactly what a mutation
    of the real code removed.
    """

    @staticmethod
    def _unscored(source_id: str, url: str, title: str, snippet: str) -> SearchResult:
        from lpf.research.authority import extract_domain

        return SearchResult(
            source_id=source_id,
            title=title,
            url=url,
            snippet=snippet,
            domain=extract_domain(url),
            provider=SearchProvider.MOCK,
            authority=SourceAuthority.ACADEMIC,
            relevance_score=0.0,
        )

    @pytest.mark.asyncio
    async def test_unscored_on_topic_result_gets_positive_relevance(self) -> None:
        pipeline = _pipeline(
            [
                self._unscored(
                    "s1",
                    "https://arxiv.org/abs/1",
                    "Linear algebra",
                    "Linear algebra studies vector spaces and linear transformations.",
                )
            ]
        )
        outcome = await pipeline.run("spec1", [_question()])
        assert outcome.results[0].relevance_score > 0.0

    @pytest.mark.asyncio
    async def test_unscored_academic_source_can_reach_support_threshold(self) -> None:
        """The exact live failure: confidence must clear 0.7 without a provider score."""
        pipeline = _pipeline(
            [
                self._unscored(
                    "s1",
                    "https://arxiv.org/abs/1",
                    "Algebra",
                    "Algebra is the branch of mathematics dealing with equations.",
                )
            ]
        )
        outcome = await pipeline.run("spec1", [_question("q1", "What is algebra?")])
        claim = outcome.report.claims[0]
        assert claim.confidence >= 0.7
        evidence_map = pipeline.to_evidence_map(outcome.report)
        assert evidence_map.supported_claims == 1

    @pytest.mark.asyncio
    async def test_live_run_produces_supported_claims(self) -> None:
        """Mirrors the live run shape: several sources, some unsupported."""
        pipeline = _pipeline(
            [
                self._unscored(
                    "s1",
                    "https://arxiv.org/abs/1",
                    "Algebra",
                    "Algebra is the branch of mathematics that deals with equations.",
                ),
                self._unscored(
                    "s2",
                    "https://arxiv.org/abs/2",
                    "Algebra groups",
                    "Groups in algebra are sets with an associative binary operation.",
                ),
                self._unscored(
                    "s3", "https://other.example/x", "Unrelated cooking notes", "How to boil pasta."
                ),
            ]
        )
        outcome = await pipeline.run("spec1", [_question("q1", "What is algebra?")])
        evidence_map = pipeline.to_evidence_map(outcome.report)
        assert evidence_map.supported_claims >= 1
        assert evidence_map.total_claims >= 1

    @pytest.mark.asyncio
    async def test_provider_supplied_score_is_not_overwritten(self) -> None:
        pipeline = _pipeline([_result("s1", "https://arxiv.org/a", relevance=0.42)])
        outcome = await pipeline.run("spec1", [_question()])
        assert outcome.results[0].relevance_score == 0.42

    @pytest.mark.asyncio
    async def test_irrelevant_source_is_still_marked_irrelevant(self) -> None:
        pipeline = _pipeline(
            [
                self._unscored(
                    "s1",
                    "https://other.example/x",
                    "Cooking pasta",
                    "Boil a large pot of water, add salt, then the pasta.",
                )
            ]
        )
        outcome = await pipeline.run("spec1", [_question("q1", "What is algebra?")])
        assert outcome.results[0].relevance_score == 0.0
        assert outcome.report.verified_sources[0].relevant is False

    @pytest.mark.asyncio
    async def test_ranking_still_prefers_authority_then_relevance(self) -> None:
        on_topic = self._unscored(
            "s1",
            "https://quora.com/a",
            "Algebra",
            "Algebra involves equations, identities, and abstract structures.",
        )
        off_topic = self._unscored(
            "s2",
            "https://arxiv.org/b",
            "Pasta chemistry",
            "Starch gelatinisation determines the cooking quality of pasta.",
        )
        pipeline = _pipeline([off_topic, on_topic])
        outcome = await pipeline.run("spec1", [_question("q1", "What is algebra?")])
        assert outcome.results[0].source_id == "s1"


class TestPipelineRun:
    @pytest.mark.asyncio
    async def test_builds_report(self) -> None:
        pipeline = _pipeline([_result("s1", "https://arxiv.org/a")])
        outcome = await pipeline.run("spec1", [_question()])
        assert outcome.report.product_spec_id == "spec1"
        assert len(outcome.report.verified_sources) == 1
        assert len(outcome.report.claims) == 1

    @pytest.mark.asyncio
    async def test_records_drop_counts(self) -> None:
        pipeline = _pipeline(
            [
                _result("s1", "https://arxiv.org/a"),
                _result("s2", "https://arxiv.org/a"),
                _result("s3", "https://quora.com/b"),
                _result("s4", "https://quora.com/c"),
            ]
        )
        outcome = await pipeline.run("spec1", [_question()])
        assert outcome.duplicates_removed == 1
        assert outcome.dropped_thin == 0

    @pytest.mark.asyncio
    async def test_max_sources_is_enforced(self) -> None:
        config = PipelineConfig(max_sources=1)
        pipeline = _pipeline(
            [_result("s1", "https://arxiv.org/a"), _result("s2", "https://arxiv.org/b")],
            config,
        )
        outcome = await pipeline.run("spec1", [_question()])
        assert len(outcome.results) == 1

    @pytest.mark.asyncio
    async def test_no_results_still_produces_report(self) -> None:
        pipeline = _pipeline([])
        outcome = await pipeline.run("spec1", [_question()])
        assert outcome.report.claims == []
        assert outcome.report.verified_sources == []
        assert len(outcome.report.knowledge_gaps) == 1

    @pytest.mark.asyncio
    async def test_report_sources_are_referenced(self) -> None:
        pipeline = _pipeline([_result("s1", "https://arxiv.org/a")])
        outcome = await pipeline.run("spec1", [_question()])
        assert outcome.report.source_refs == ["s1"]

    @pytest.mark.asyncio
    async def test_results_without_url_are_not_verified(self) -> None:
        pipeline = _pipeline([_result("s1", "")])
        outcome = await pipeline.run("spec1", [_question()])
        assert outcome.report.verified_sources == []


# ---------------------------------------------------------------------------
# evidence map
# ---------------------------------------------------------------------------


class TestEvidenceMap:
    @pytest.mark.asyncio
    async def test_counts_supported_claims(self) -> None:
        pipeline = _pipeline(
            [
                _result(
                    "s1",
                    "https://mit.edu/a",
                    authority=SourceAuthority.INSTITUTIONAL,
                    relevance=1.0,
                ),
                _result(
                    "s2", "https://quora.com/b", authority=SourceAuthority.GENERAL, relevance=0.1
                ),
            ]
        )
        outcome = await pipeline.run("spec1", [_question()])
        evidence_map = pipeline.to_evidence_map(outcome.report)
        assert evidence_map.total_claims == 2
        assert 0 <= evidence_map.supported_claims <= 2

    @pytest.mark.asyncio
    async def test_references_report(self) -> None:
        pipeline = _pipeline([_result("s1", "https://arxiv.org/a")])
        outcome = await pipeline.run("spec1", [_question()])
        evidence_map = pipeline.to_evidence_map(outcome.report)
        assert evidence_map.research_report_id == outcome.report.id

    @pytest.mark.asyncio
    async def test_threshold_is_recorded(self) -> None:
        pipeline = _pipeline([_result("s1", "https://arxiv.org/a")])
        outcome = await pipeline.run("spec1", [_question()])
        evidence_map = pipeline.to_evidence_map(outcome.report, confidence_threshold=0.9)
        assert evidence_map.confidence_threshold == 0.9


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    @pytest.mark.asyncio
    async def test_same_inputs_produce_same_selection(self) -> None:
        results = [
            _result("s1", "https://quora.com/a", authority=SourceAuthority.GENERAL, relevance=0.9),
            _result(
                "s2", "https://mit.edu/b", authority=SourceAuthority.INSTITUTIONAL, relevance=0.5
            ),
        ]
        first = await _pipeline(list(results)).run("spec1", [_question()])
        second = await _pipeline(list(results)).run("spec1", [_question()])
        assert [r.source_id for r in first.results] == [r.source_id for r in second.results]

    @pytest.mark.asyncio
    async def test_claim_confidence_is_stable(self) -> None:
        results = [_result("s1", "https://arxiv.org/a")]
        first = await _pipeline(list(results)).run("spec1", [_question()])
        second = await _pipeline(list(results)).run("spec1", [_question()])
        assert first.report.claims[0].confidence == second.report.claims[0].confidence


# ---------------------------------------------------------------------------


class TestQuestionsAreScoredIndividually:
    """A result must be scored against the question it was retrieved for.

    Live testing against arXiv and Wikimedia exposed this: the pipeline joined
    every question in a run into one query string and scored each source against
    that concatenation. Lexical coverage was diluted by unrelated questions, so a
    correct source retrieved for one question fell below the 0.7 support
    threshold purely because other questions existed in the same run. A live run
    produced 2 supported claims out of 52; the correct Wikipedia article scored
    0.746 instead of 1.0.
    """

    class _EchoProvider:
        """Returns one on-topic, unscored result per query."""

        provider_name = SearchProvider.MOCK

        async def search(self, query: str, *, max_results: int = 10) -> list[SearchResult]:
            topic = query.rstrip("?")
            slug = topic.lower().replace(" ", "-")[:30]
            return [
                SearchResult(
                    source_id=f"s-{slug}",
                    title=topic,
                    url=f"https://example.org/{slug}",
                    snippet=(
                        f"{topic} is defined here in plain language for the learner, "
                        "with one worked example."
                    ),
                    domain="example.org",
                    provider=SearchProvider.MOCK,
                    authority=SourceAuthority.SECONDARY,
                    relevance_score=0.0,
                )
            ]

        async def extract(self, url: str) -> str:
            return ""

    QUESTIONS = (
        ("q1", "What is linear algebra?"),
        ("q2", "What is machine learning?"),
        ("q3", "What is the Roman Republic?"),
    )

    def _pipeline(self):
        router = ResearchRouter(providers={SearchProvider.MOCK: self._EchoProvider()})
        return ResearchPipeline(ResearchService(router), PipelineConfig())

    def _questions(self):
        return [_question(qid, text) for qid, text in self.QUESTIONS]

    @pytest.mark.asyncio
    async def test_each_result_keeps_its_own_question(self) -> None:
        pipeline = self._pipeline()
        outcome = await pipeline.run("spec1", self._questions())
        for result in outcome.results:
            assert pipeline._query_for(result) in [text for _, text in self.QUESTIONS]

    @pytest.mark.asyncio
    async def test_relevance_is_not_diluted_by_other_questions(self) -> None:
        pipeline = self._pipeline()
        outcome = await pipeline.run("spec1", self._questions())
        assert all(result.relevance_score >= 0.5 for result in outcome.results)

    @pytest.mark.asyncio
    async def test_every_on_topic_source_reaches_the_support_threshold(self) -> None:
        """The live symptom: a correct source scored below 0.7 because the run
        contained other questions."""
        pipeline = self._pipeline()
        outcome = await pipeline.run("spec1", self._questions())
        evidence_map = pipeline.to_evidence_map(outcome.report)
        assert evidence_map.total_claims == len(self.QUESTIONS)
        assert evidence_map.supported_claims == len(self.QUESTIONS)
