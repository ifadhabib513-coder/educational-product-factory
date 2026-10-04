"""Regression tests for the derived-relevance fix.

Live smoke testing against the real internet showed that only Tavily populates
``SearchResult.relevance_score``. arXiv, Wikimedia and SearXNG left it at the
schema default of 0.0, which capped claim confidence at
``authority_rank / 7 * authority_weight`` -- always below the 0.7 evidence-map
support threshold. Every real report produced an empty EvidenceMap (0/20
supported). Mocked tests missed it because fixtures set relevance explicitly.
"""

from __future__ import annotations

import pytest

from lpf.research.pipeline import PipelineConfig, ResearchPipeline
from lpf.research.relevance import effective_relevance, lexical_relevance, tokenize
from lpf.schemas.research import ResearchQuestion


class TestTokenize:
    def test_lowercases_and_strips_punctuation(self) -> None:
        assert tokenize("Vector Spaces, and Linear Maps!") == {"vector", "space", "linear", "map"}

    def test_singularises_plurals(self) -> None:
        assert tokenize("seasons") == {"season"}
        assert tokenize("vectors and spaces") == {"vector", "space"}

    def test_does_not_strip_double_s(self) -> None:
        assert tokenize("class across") == {"class", "across"}

    def test_removes_stopwords(self) -> None:
        assert tokenize("what is the value of it") == {"value"}

    def test_empty_text_yields_empty_set(self) -> None:
        assert tokenize("") == set()
        assert tokenize("   ,,, ") == set()


class TestLexicalRelevance:
    def test_exact_topical_match_scores_high(self) -> None:
        score = lexical_relevance(
            "What is linear algebra?",
            "Linear algebra",
            "Linear algebra is the branch of mathematics concerning linear equations.",
        )
        assert score == 1.0

    def test_partial_overlap_scores_between_zero_and_one(self) -> None:
        score = lexical_relevance("linear algebra", "Non-linear positive maps", "positive maps")
        assert 0.0 < score < 1.0

    def test_unrelated_document_scores_zero(self) -> None:
        assert lexical_relevance("quantum gravity", "Cooking recipes", "A guide to pasta") == 0.0

    def test_empty_query_scores_zero(self) -> None:
        assert lexical_relevance("", "Linear algebra", "anything") == 0.0

    def test_all_stopword_query_scores_zero(self) -> None:
        assert lexical_relevance("the of and", "Linear algebra", "anything") == 0.0

    def test_title_match_outweighs_snippet_match(self) -> None:
        in_title = lexical_relevance("vector space", "Vector space", "unrelated words here")
        in_snippet = lexical_relevance("vector space", "Unrelated", "a vector space appears")
        assert in_title > in_snippet

    def test_score_never_exceeds_one(self) -> None:
        score = lexical_relevance(
            "linear algebra", "linear algebra", "linear algebra linear algebra algebra"
        )
        assert score <= 1.0

    def test_is_deterministic(self) -> None:
        args = ("what is entropy", "Entropy", "Entropy measures uncertainty")
        assert lexical_relevance(*args) == lexical_relevance(*args)


class TestEffectiveRelevance:
    def test_trusts_provider_score_when_present(self) -> None:
        assert effective_relevance("anything", provider_score=0.87, title="no match here") == 0.87

    def test_falls_back_to_lexical_when_provider_score_is_zero(self) -> None:
        derived = effective_relevance(
            "linear algebra", provider_score=0.0, title="Linear algebra", snippet="about vectors"
        )
        assert derived > 0.0


class TestPipelineDerivesRelevance:
    """The pipeline must fill in relevance that providers never supplied."""

    @staticmethod
    def _pipeline() -> ResearchPipeline:
        from lpf.research.providers.base import MockSearchProvider
        from lpf.research.router import ResearchRouter
        from lpf.research.service import ResearchService
        from lpf.schemas.research import SearchProvider

        provider = MockSearchProvider(results=[])
        service = ResearchService(ResearchRouter(providers={SearchProvider.MOCK: provider}))
        return ResearchPipeline(service, PipelineConfig())

    @staticmethod
    def _results(*relevance: float):
        from lpf.schemas.research import SearchProvider, SearchResult, SourceAuthority

        return [
            SearchResult(
                source_id=f"s{i}",
                title="Linear algebra" if i % 2 == 0 else "Unrelated cooking notes",
                url=f"https://example{i}.com/x",
                snippet="linear algebra concerns vector spaces"
                if i % 2 == 0
                else "how to boil pasta",
                domain=f"example{i}.com",
                provider=SearchProvider.MOCK,
                authority=SourceAuthority.SECONDARY,
                relevance_score=r,
            )
            for i, r in enumerate(relevance)
        ]

    @staticmethod
    def _question(text: str = "What is linear algebra?") -> ResearchQuestion:
        from lpf.schemas.research import SearchProvider, SearchQuery, SearchStrategy

        return ResearchQuestion(
            question_id="q1",
            text=text,
            topic="linear algebra",
            strategy=SearchStrategy(
                providers=[SearchProvider.MOCK],
                queries=[SearchQuery(query=text, provider=SearchProvider.MOCK)],
            ),
        )

    def test_zero_relevance_is_replaced_with_derived_score(self) -> None:
        pipe = self._pipeline()
        derived = pipe._derive_relevance(self._results(0.0, 0.0), self._question().text)
        on_topic, off_topic = derived[0], derived[1]
        assert on_topic.relevance_score > 0.0
        assert off_topic.relevance_score == 0.0

    def test_relevant_result_outscores_irrelevant_one(self) -> None:
        pipe = self._pipeline()
        derived = pipe._derive_relevance(self._results(0.0, 0.0), self._question().text)
        on_topic, off_topic = derived[0], derived[1]
        assert on_topic.relevance_score > off_topic.relevance_score

    def test_existing_provider_score_is_preserved(self) -> None:
        pipe = self._pipeline()
        out = pipe._derive_relevance(self._results(0.9), self._question().text)
        assert out[0].relevance_score == 0.9

    def test_no_query_leaves_results_untouched(self) -> None:
        pipe = self._pipeline()
        out = pipe._derive_relevance(self._results(0.0), "")
        assert out[0].relevance_score == 0.0

    @pytest.mark.parametrize(
        ("query", "title"),
        [
            ("What is a vector space?", "Vector space"),
            ("How does photosynthesis work?", "Photosynthesis"),
            ("What causes the seasons?", "Season"),
        ],
    )
    def test_realistic_questions_produce_positive_relevance(self, query: str, title: str) -> None:
        assert lexical_relevance(query, title, "") > 0.0
