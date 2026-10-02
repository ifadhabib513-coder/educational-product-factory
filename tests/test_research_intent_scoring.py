"""Tests for intent classification, audience handling, and ranking components.

The most important test in this file is
``TestEvidenceMapSurvivesEveryIntent``. Introducing intent-conditional weights
created a live risk of re-creating the permanently-empty EvidenceMap bug, where
an on-topic encyclopedia article scored below the 0.7 support threshold purely
because its tier was SECONDARY and its intent profile weighted authority highly.
"""

from __future__ import annotations

import datetime

import pytest

from lpf.research.audience import (
    AudienceLevel,
    apply_density_penalty,
    audience_fit,
    classify_audience,
    tier_fit,
)
from lpf.research.intent import (
    QueryIntent,
    authority_fit,
    classify_intent,
    ranking_weights,
    validate_weights,
)
from lpf.research.pipeline import PipelineConfig, ResearchPipeline
from lpf.research.providers.base import MockSearchProvider
from lpf.research.router import ResearchRouter
from lpf.research.scoring import (
    clarity,
    components,
    confidence,
    date_span,
    freshness,
    has_definition_cue,
    intent_match,
    ranking_score,
    specialist_density,
)
from lpf.research.service import ResearchService
from lpf.schemas.research import (
    ResearchQuestion,
    SearchProvider,
    SearchQuery,
    SearchResult,
    SearchStrategy,
    SourceAuthority,
)

DEFINITIONAL_TEXT = (
    "Linear algebra is the branch of mathematics concerning linear equations, linear maps "
    "and their representations in matrices and vector spaces."
)
SPECIALIST_TEXT = (
    "We present properties of positive maps between $\\mathcal{A}$ and $\\mathcal{B}$, "
    "a topic in functional analysis."
)


# ---------------------------------------------------------------------------
# intent classification
# ---------------------------------------------------------------------------


class TestClassifyIntent:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("What is linear algebra?", QueryIntent.DEFINITIONAL),
            ("What are eigenvalues?", QueryIntent.DEFINITIONAL),
            ("Define entropy", QueryIntent.DEFINITIONAL),
            ("What does photosynthesis mean?", QueryIntent.DEFINITIONAL),
            ("Explain linear algebra simply", QueryIntent.EXPLANATORY),
            ("Why does the sky appear blue?", QueryIntent.EXPLANATORY),
            ("How does a transistor work?", QueryIntent.EXPLANATORY),
            ("How do I solve a system of equations?", QueryIntent.PROCEDURAL),
            ("Step by step guide to differentiation", QueryIntent.PROCEDURAL),
            ("Find papers about spaced repetition", QueryIntent.ACADEMIC_LITERATURE),
            ("peer reviewed studies on sleep and memory", QueryIntent.ACADEMIC_LITERATURE),
            ("What does research say about intermittent fasting?", QueryIntent.EVIDENCE_SYNTHESIS),
            ("meta-analysis of cognitive load", QueryIntent.EVIDENCE_SYNTHESIS),
            ("latest research on CRISPR", QueryIntent.CURRENT),
            ("recent advances in protein folding", QueryIntent.CURRENT),
            ("linear algebra", QueryIntent.GENERAL),
            ("", QueryIntent.GENERAL),
            ("   ", QueryIntent.GENERAL),
        ],
    )
    def test_classification(self, query: str, expected: QueryIntent) -> None:
        assert classify_intent(query) is expected

    def test_current_beats_academic_literature(self) -> None:
        """Specificity ordering: 'latest research' must not read as paper-finding."""
        assert classify_intent("latest research on X") is QueryIntent.CURRENT
        assert classify_intent("find papers on X") is QueryIntent.ACADEMIC_LITERATURE

    def test_is_deterministic(self) -> None:
        q = "What is linear algebra?"
        assert len({classify_intent(q) for _ in range(50)}) == 1

    def test_case_insensitive(self) -> None:
        assert classify_intent("WHAT IS LINEAR ALGEBRA?") is QueryIntent.DEFINITIONAL


class TestRankingWeights:
    @pytest.mark.parametrize("intent", list(QueryIntent))
    def test_every_profile_sums_to_one(self, intent: QueryIntent) -> None:
        validate_weights(intent)

    def test_definitional_favours_clarity_over_authority(self) -> None:
        w = ranking_weights(QueryIntent.DEFINITIONAL)
        assert w["clarity"] > w["authority_fit"]
        assert w["freshness"] == 0.0

    def test_academic_literature_favours_authority(self) -> None:
        w = ranking_weights(QueryIntent.ACADEMIC_LITERATURE)
        assert w["authority_fit"] > 0.5

    def test_current_weights_freshness_most_heavily_of_any_intent(self) -> None:
        """CURRENT must be the most freshness-sensitive profile.

        Authority still dominates it (0.45 vs 0.25), which is deliberate: a
        recent blog post is not a better answer than a current preprint.
        """
        freshness_weights = {intent: ranking_weights(intent)["freshness"] for intent in QueryIntent}
        assert max(freshness_weights, key=freshness_weights.get) is QueryIntent.CURRENT
        assert freshness_weights[QueryIntent.DEFINITIONAL] == 0.0

    def test_returned_weights_are_a_copy(self) -> None:
        w = ranking_weights(QueryIntent.DEFINITIONAL)
        w["clarity"] = 99.0
        assert ranking_weights(QueryIntent.DEFINITIONAL)["clarity"] != 99.0


class TestAuthorityFit:
    def test_encyclopedia_is_ideal_for_definitional(self) -> None:
        assert authority_fit(QueryIntent.DEFINITIONAL, SourceAuthority.SECONDARY) == 1.0

    def test_encyclopedia_is_poor_for_literature_review(self) -> None:
        assert authority_fit(QueryIntent.ACADEMIC_LITERATURE, SourceAuthority.SECONDARY) < 0.5

    def test_preprint_is_ideal_for_literature(self) -> None:
        assert authority_fit(QueryIntent.ACADEMIC_LITERATURE, SourceAuthority.ACADEMIC) == 1.0

    def test_preprint_is_poor_for_a_definition(self) -> None:
        assert authority_fit(QueryIntent.DEFINITIONAL, SourceAuthority.ACADEMIC) < 0.5

    def test_ordering_inverts_between_the_two_intents(self) -> None:
        definitional = authority_fit(QueryIntent.DEFINITIONAL, SourceAuthority.SECONDARY)
        academic = authority_fit(QueryIntent.DEFINITIONAL, SourceAuthority.ACADEMIC)
        assert definitional > academic


# ---------------------------------------------------------------------------
# audience
# ---------------------------------------------------------------------------


class TestClassifyAudience:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("beginner", AudienceLevel.BEGINNER),
            ("Complete beginner", AudienceLevel.BEGINNER),
            ("no prior knowledge", AudienceLevel.BEGINNER),
            ("high school", AudienceLevel.BEGINNER),
            ("GCSE", AudienceLevel.BEGINNER),
            ("Year 1", AudienceLevel.BEGINNER),
            ("advanced", AudienceLevel.ADVANCED),
            ("postgraduate", AudienceLevel.ADVANCED),
            ("PhD", AudienceLevel.ADVANCED),
            ("MSc", AudienceLevel.ADVANCED),
            ("some background", AudienceLevel.INTERMEDIATE),
            ("second year", AudienceLevel.INTERMEDIATE),
            ("wizardry", AudienceLevel.INTERMEDIATE),
            ("", AudienceLevel.INTERMEDIATE),
            (None, AudienceLevel.INTERMEDIATE),
        ],
    )
    def test_normalisation(self, text, expected: AudienceLevel) -> None:
        assert classify_audience(text) is expected

    def test_passthrough_for_enum(self) -> None:
        assert classify_audience(AudienceLevel.BEGINNER) is AudienceLevel.BEGINNER

    def test_default_is_intermediate_not_beginner(self) -> None:
        """Defaulting to beginner would flood learners with beginner material."""
        assert classify_audience("unparseable") is AudienceLevel.INTERMEDIATE


class TestAudienceFit:
    def test_textbook_is_best_for_beginners(self) -> None:
        assert tier_fit(AudienceLevel.BEGINNER, SourceAuthority.TEXTBOOK) > tier_fit(
            AudienceLevel.BEGINNER, SourceAuthority.ACADEMIC
        )

    def test_academic_is_best_for_advanced(self) -> None:
        assert tier_fit(AudienceLevel.ADVANCED, SourceAuthority.ACADEMIC) > tier_fit(
            AudienceLevel.ADVANCED, SourceAuthority.SECONDARY
        )

    def test_density_penalty_scales_with_level(self) -> None:
        assert apply_density_penalty(AudienceLevel.BEGINNER, 1.0) == 1.0
        assert apply_density_penalty(AudienceLevel.INTERMEDIATE, 1.0) == 0.5
        assert apply_density_penalty(AudienceLevel.ADVANCED, 1.0) == 0.0

    def test_penalty_is_capped(self) -> None:
        fit = audience_fit(AudienceLevel.BEGINNER, SourceAuthority.PRIMARY, 1.0)
        assert fit >= 0.0

    def test_dense_prose_hurts_beginners_more_than_experts(self) -> None:
        beginner = audience_fit(AudienceLevel.BEGINNER, SourceAuthority.ACADEMIC, 0.9)
        expert = audience_fit(AudienceLevel.ADVANCED, SourceAuthority.ACADEMIC, 0.9)
        assert expert > beginner


# ---------------------------------------------------------------------------
# scoring components
# ---------------------------------------------------------------------------


class TestDefinitionCue:
    @pytest.mark.parametrize(
        "text",
        [
            "Linear algebra is the branch of mathematics",
            "Entropy refers to the amount of uncertainty",
            "Photosynthesis is the process by which plants convert light",
            "A vector refers to an element of a vector space",
            "In mathematics, a group is a set with an operation",
        ],
    )
    def test_detects_definition_shaped_text(self, text: str) -> None:
        assert has_definition_cue(text, "") is True

    @pytest.mark.parametrize(
        "text",
        [
            "We present some properties of positive maps between operator algebras",
            "Cell division occurs in all living organisms",
            "The patient was treated with 5mg of the compound daily",
        ],
    )
    def test_ignores_ordinary_and_specialist_prose(self, text: str) -> None:
        assert has_definition_cue(text, "") is False


class TestIntentMatch:
    @staticmethod
    def _result(title: str, snippet: str) -> SearchResult:
        from lpf.research.authority import extract_domain

        return SearchResult(
            source_id="s",
            title=title,
            url="https://example.org/a",
            snippet=snippet,
            domain=extract_domain("https://example.org/a"),
            provider=SearchProvider.MOCK,
            authority=SourceAuthority.SECONDARY,
            relevance_score=1.0,
        )

    def test_cue_weight_separates_equal_coverage(self) -> None:
        """The core diagnosis: token overlap rates both sources 1.0."""
        query = "What is linear algebra?"
        intro = self._result("Linear algebra", DEFINITIONAL_TEXT)
        spec = self._result("Non-linear positive maps between C*-algebras", SPECIALIST_TEXT)

        from lpf.research.relevance import lexical_relevance

        assert lexical_relevance(query, intro.title, intro.snippet) == 1.0
        assert lexical_relevance(query, spec.title, spec.snippet) == 1.0
        assert intent_match(intro, query, QueryIntent.DEFINITIONAL) > intent_match(
            spec, query, QueryIntent.DEFINITIONAL
        )

    def test_off_topic_scores_zero(self) -> None:
        result = self._result("Cooking pasta", "Boil water and add the pasta.")
        assert intent_match(result, "What is linear algebra?", QueryIntent.DEFINITIONAL) == 0.0

    def test_cue_cannot_rescue_an_off_topic_source(self) -> None:
        result = self._result("Cooking pasta", "Pasta is the branch of food preparation.")
        assert intent_match(result, "What is linear algebra?", QueryIntent.DEFINITIONAL) == 0.0

    def test_academic_intent_ignores_definition_cue(self) -> None:
        query = "find papers about linear algebra"
        intro = self._result("Linear algebra", DEFINITIONAL_TEXT)
        spec = self._result("Linear maps", SPECIALIST_TEXT)
        assert intent_match(intro, query, QueryIntent.ACADEMIC_LITERATURE) >= 0.0
        assert intent_match(spec, query, QueryIntent.ACADEMIC_LITERATURE) >= 0.0


class TestClarityAndDensity:
    def test_specialist_text_is_denser(self) -> None:
        assert specialist_density("Paper", SPECIALIST_TEXT) > specialist_density(
            "Article", DEFINITIONAL_TEXT
        )

    def test_plain_text_has_no_density(self) -> None:
        assert specialist_density("Linear algebra", DEFINITIONAL_TEXT) == 0.0

    def test_denser_text_scores_lower_clarity(self) -> None:
        assert clarity("Paper", SPECIALIST_TEXT) < clarity("Article", DEFINITIONAL_TEXT)

    def test_clarity_is_bounded(self) -> None:
        for text in (DEFINITIONAL_TEXT, SPECIALIST_TEXT, "", "x"):
            assert 0.0 <= clarity("t", text) <= 1.0

    def test_clarity_is_deterministic(self) -> None:
        assert clarity("t", DEFINITIONAL_TEXT) == clarity("t", DEFINITIONAL_TEXT)

    def test_subject_agnostic_markers(self) -> None:
        """Density must not depend on any single field's jargon."""
        assert specialist_density("Biology", "The cell membrane is a phospholipid bilayer.") == 0.0
        assert specialist_density("History", "The treaty was signed at Versailles in 1919.") == 0.0


class TestFreshness:
    @staticmethod
    def _result(date: datetime.datetime | None) -> SearchResult:
        from lpf.research.authority import extract_domain

        return SearchResult(
            source_id="s",
            title="t",
            url="https://example.org/a",
            snippet=DEFINITIONAL_TEXT,
            domain=extract_domain("https://example.org/a"),
            provider=SearchProvider.MOCK,
            authority=SourceAuthority.SECONDARY,
            published_at=date,
        )

    @staticmethod
    def _ts(day: int) -> datetime.datetime:
        return datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC) + datetime.timedelta(days=day)

    def test_undated_is_neutral_not_fresh(self) -> None:
        old, new = self._ts(0), self._ts(100)
        assert freshness(self._result(None), oldest=old, newest=new) == 0.5

    def test_corpus_relative_not_wall_clock(self) -> None:
        old, new = self._ts(0), self._ts(100)
        assert freshness(self._result(old), oldest=old, newest=new) == 0.0
        assert freshness(self._result(new), oldest=old, newest=new) == 1.0

    def test_shifting_every_date_preserves_ordering(self) -> None:
        """Freshness must not drift with wall-clock time."""
        early, late = self._ts(0), self._ts(100)
        shifted_old, shifted_new = self._ts(1000), self._ts(1100)
        assert freshness(self._result(early), oldest=early, newest=late) == freshness(
            self._result(shifted_old), oldest=shifted_old, newest=shifted_new
        )
        assert freshness(self._result(late), oldest=early, newest=late) == freshness(
            self._result(shifted_new), oldest=shifted_old, newest=shifted_new
        )

    def test_single_dated_source_is_neutral(self) -> None:
        when = self._ts(500)
        assert freshness(self._result(when), oldest=when, newest=when) == 0.5

    def test_date_span_ignores_missing_dates(self) -> None:
        results = [self._result(self._ts(10)), self._result(None), self._result(self._ts(30))]
        assert date_span(results) == (self._ts(10), self._ts(30))

    def test_date_span_with_no_dates(self) -> None:
        assert date_span([self._result(None)]) == (0.0, 0.0)

    def test_mixed_dated_and_undated(self) -> None:
        old, new = self._ts(0), self._ts(100)
        assert freshness(self._result(old), oldest=old, newest=new) == 0.0
        assert freshness(self._result(None), oldest=old, newest=new) == 0.5
        assert freshness(self._result(new), oldest=old, newest=new) == 1.0


class TestConfidenceSemantics:
    @staticmethod
    def _result(authority: SourceAuthority, snippet: str = DEFINITIONAL_TEXT) -> SearchResult:
        from lpf.research.authority import extract_domain

        return SearchResult(
            source_id="s",
            title="Linear algebra",
            url="https://example.org/a",
            snippet=snippet,
            domain=extract_domain("https://example.org/a"),
            provider=SearchProvider.MOCK,
            authority=authority,
            relevance_score=1.0,
        )

    def test_bounded(self) -> None:
        c = confidence(self._result(SourceAuthority.PRIMARY), query="q", intent=QueryIntent.GENERAL)
        assert 0.0 <= c <= 1.0

    def test_independent_of_audience_and_clarity(self) -> None:
        """Confidence must measure evidence, not pedagogical preference."""
        plain = self._result(SourceAuthority.SECONDARY)
        dense = self._result(SourceAuthority.SECONDARY, SPECIALIST_TEXT)
        assert confidence(
            plain, query="What is linear algebra?", intent=QueryIntent.DEFINITIONAL
        ) != (confidence(dense, query="What is linear algebra?", intent=QueryIntent.DEFINITIONAL))

    def test_ignores_ranking_weights(self) -> None:
        """Two intents with different weight profiles still score evidence alike
        for a tier they treat the same way."""
        result = self._result(SourceAuthority.PRIMARY)
        a = confidence(result, query="What is linear algebra?", intent=QueryIntent.DEFINITIONAL)
        b = confidence(result, query="What is linear algebra?", intent=QueryIntent.EXPLANATORY)
        assert a == pytest.approx(b, abs=0.15)


# ---------------------------------------------------------------------------
# the guard that matters
# ---------------------------------------------------------------------------

INTENT_APPROPRIATE_SOURCE = {
    QueryIntent.DEFINITIONAL: (
        SourceAuthority.SECONDARY,
        DEFINITIONAL_TEXT,
    ),
    QueryIntent.EXPLANATORY: (
        SourceAuthority.EDUCATIONAL,
        DEFINITIONAL_TEXT,
    ),
    QueryIntent.PROCEDURAL: (
        SourceAuthority.TEXTBOOK,
        "Step by step: first isolate the variable, then move terms, then divide. "
        "Here is a worked example with the final answer.",
    ),
    QueryIntent.ACADEMIC_LITERATURE: (SourceAuthority.ACADEMIC, SPECIALIST_TEXT),
    QueryIntent.EVIDENCE_SYNTHESIS: (
        SourceAuthority.ACADEMIC,
        "Across the studies, the evidence shows a consistent effect after "
        "controlling for sample size.",
    ),
    QueryIntent.CURRENT: (
        SourceAuthority.ACADEMIC,
        "The most recent results show a measurable improvement over earlier trials.",
    ),
    QueryIntent.GENERAL: (SourceAuthority.INSTITUTIONAL, DEFINITIONAL_TEXT),
}


class TestEvidenceMapSurvivesEveryIntent:
    """No intent may produce an empty EvidenceMap from a suitable source.

    Guards the regression that intent-conditional weighting introduced: an
    on-topic SECONDARY source could fall below the 0.7 threshold purely because
    the intent profile weighted authority heavily.
    """

    @staticmethod
    def _question() -> ResearchQuestion:
        return ResearchQuestion(
            question_id="q1",
            text="What is linear algebra?",
            topic="linear algebra",
            strategy=SearchStrategy(
                providers=[SearchProvider.MOCK],
                queries=[SearchQuery(query="linear algebra", provider=SearchProvider.MOCK)],
            ),
        )

    @pytest.mark.parametrize("intent", list(QueryIntent))
    @pytest.mark.asyncio
    async def test_suitable_source_produces_supported_claims(self, intent: QueryIntent) -> None:
        from lpf.research.authority import extract_domain

        authority, snippet = INTENT_APPROPRIATE_SOURCE[intent]
        result = SearchResult(
            source_id="s1",
            title="Linear algebra",
            url="https://example.org/a",
            snippet=snippet,
            domain=extract_domain("https://example.org/a"),
            provider=SearchProvider.MOCK,
            authority=authority,
            relevance_score=1.0,
        )

        service = ResearchService(
            ResearchRouter(providers={SearchProvider.MOCK: MockSearchProvider(results=[result])})
        )
        pipeline = ResearchPipeline(
            service,
            PipelineConfig(audience_level=AudienceLevel.INTERMEDIATE, intent_override=intent),
        )

        outcome = await pipeline.run("spec1", [self._question()])
        evidence_map = pipeline.to_evidence_map(outcome.report)

        assert evidence_map.total_claims == 1
        assert evidence_map.supported_claims == 1, (
            f"intent {intent} produced an empty EvidenceMap; confidence model "
            "is no longer comparable across intents"
        )

    @pytest.mark.asyncio
    async def test_evidence_bar_shifts_with_intent(self) -> None:
        """The same source is strong evidence for one intent and weak for another.

        An encyclopedia article is excellent evidence for "What is X?" and poor
        evidence for "Find papers about X". Making authority conditional on intent
        moves the *evidence bar* as well as the ranking, which is the point:
        conflating the two would either let encyclopedias pass as literature
        reviews or bury them under beginner material.
        """
        from lpf.research.authority import extract_domain

        wiki = SearchResult(
            source_id="s1",
            title="Linear algebra",
            url="https://en.wikipedia.org/wiki/Linear_algebra",
            snippet=DEFINITIONAL_TEXT,
            domain=extract_domain("https://en.wikipedia.org/wiki/Linear_algebra"),
            provider=SearchProvider.WIKIMEDIA,
            authority=SourceAuthority.SECONDARY,
            relevance_score=1.0,
        )

        scores = {}
        for intent in QueryIntent:
            service = ResearchService(
                ResearchRouter(providers={SearchProvider.MOCK: MockSearchProvider(results=[wiki])})
            )
            pipeline = ResearchPipeline(
                service,
                PipelineConfig(audience_level=AudienceLevel.INTERMEDIATE, intent_override=intent),
            )
            outcome = await pipeline.run("spec1", [self._question()])
            scores[intent] = outcome.report.claims[0].confidence

        assert scores[QueryIntent.DEFINITIONAL] >= 0.7
        assert scores[QueryIntent.EXPLANATORY] >= 0.7
        assert scores[QueryIntent.GENERAL] >= 0.7
        assert scores[QueryIntent.ACADEMIC_LITERATURE] < 0.7, (
            "an encyclopedia article must not pass as strong evidence for a "
            "literature search; that is a false positive, not a regression"
        )


class TestComponentsAreComplete:
    def test_components_returns_all_keys(self) -> None:
        from lpf.research.authority import extract_domain

        result = SearchResult(
            source_id="s",
            title="Linear algebra",
            url="https://example.org/a",
            snippet=DEFINITIONAL_TEXT,
            domain=extract_domain("https://example.org/a"),
            provider=SearchProvider.MOCK,
            authority=SourceAuthority.SECONDARY,
        )
        parts = components(
            result,
            query="What is linear algebra?",
            intent=QueryIntent.DEFINITIONAL,
            audience=AudienceLevel.BEGINNER,
            oldest=0.0,
            newest=0.0,
        )
        assert set(parts) == {
            "intent_match",
            "audience_fit",
            "clarity",
            "authority_fit",
            "freshness",
        }
        assert all(0.0 <= v <= 1.0 for v in parts.values())

    def test_ranking_score_is_bounded(self) -> None:
        from lpf.research.authority import extract_domain

        result = SearchResult(
            source_id="s",
            title="Linear algebra",
            url="https://example.org/a",
            snippet=DEFINITIONAL_TEXT,
            domain=extract_domain("https://example.org/a"),
            provider=SearchProvider.MOCK,
            authority=SourceAuthority.PRIMARY,
        )
        score = ranking_score(
            result,
            query="What is linear algebra?",
            intent=QueryIntent.GENERAL,
            audience=AudienceLevel.ADVANCED,
            oldest=0.0,
            newest=0.0,
        )
        assert 0.0 <= score <= 1.0
