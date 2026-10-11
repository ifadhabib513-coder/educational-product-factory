"""Intent-based retrieval routing.

Regression suite for TASK-010: retrieval is pruned per question intent. The
offence being tested away is a definitional "What is X?" being sent to arXiv and
returning preprints that the scorer can only reject — the question would not be
retrieval (*answerable*), the preprints are just noise, and the strategy told
them apart with constant authority.

The point of routing is that the provider is never even asked. These tests fail
if the router or plan builder stops filtering by intent, or if the offline mock
set is ever pruned away (determinism/suite-offline is a hard property).
"""

from __future__ import annotations

import pytest

from lpf.orchestration.context import RunContext
from lpf.orchestration.research_stage import build_research, default_providers
from lpf.research.intent import QueryIntent, classify_intent
from lpf.research.router import ResearchRouter
from lpf.research.routing import provider_suitability, prune_providers
from lpf.schemas.research import (
    ResearchQuestion,
    SearchProvider,
    SearchQuery,
    SearchResult,
    SearchStrategy,
    SourceAuthority,
)

_SNIPPET = (
    "This topic is defined here in plain language for the stated learner level, "
    "with one worked example and a note on the common mistake."
)

_ALL_NAMES = [
    SearchProvider.ARXIV,
    SearchProvider.WIKIMEDIA,
    SearchProvider.TAVILY,
    SearchProvider.SEARXNG,
    SearchProvider.MOCK,
    SearchProvider.OFFICIAL,
]


class RecordingProvider:
    """A search provider that records every query it was asked to run."""

    def __init__(self, name: SearchProvider, domain: str) -> None:
        self.provider_name = name
        self._domain = domain
        self.queries: list[str] = []

    async def search(self, query: str, *, max_results: int = 10) -> list[SearchResult]:
        self.queries.append(query)
        return [
            SearchResult(
                source_id=f"{self.provider_name.value}-source-1",
                title=f"{query} (reference)",
                url=f"https://{self._domain}/reference",
                snippet=_SNIPPET,
                domain=self._domain,
                provider=self.provider_name,
                authority=SourceAuthority.SECONDARY,
                relevance_score=0.9,
            )
        ]

    async def extract(self, url: str) -> str:
        return f"Extracted content for {url}."


class TestProviderSuitability:
    def test_definitional_excludes_preprints_and_keeps_encyclopedia(self) -> None:
        suitable = provider_suitability(QueryIntent.DEFINITIONAL)
        assert SearchProvider.ARXIV not in suitable
        assert SearchProvider.WIKIMEDIA in suitable

    def test_beginner_intents_exclude_preprints(self) -> None:
        for intent in (
            QueryIntent.DEFINITIONAL,
            QueryIntent.EXPLANATORY,
            QueryIntent.PROCEDURAL,
        ):
            assert SearchProvider.ARXIV not in provider_suitability(intent)

    def test_academic_intents_keep_preprints_and_drop_encyclopedia(self) -> None:
        for intent in (
            QueryIntent.ACADEMIC_LITERATURE,
            QueryIntent.EVIDENCE_SYNTHESIS,
            QueryIntent.CURRENT,
        ):
            suitable = provider_suitability(intent)
            assert SearchProvider.ARXIV in suitable
            assert SearchProvider.WIKIMEDIA not in suitable

    def test_general_keeps_everything(self) -> None:
        assert provider_suitability(QueryIntent.GENERAL) == set(_ALL_NAMES)


class TestPruneProviders:
    def test_mock_is_never_pruned_away_by_accident(self) -> None:
        for intent in QueryIntent:
            assert prune_providers(intent, [SearchProvider.MOCK]) == (SearchProvider.MOCK,)

    def test_never_returns_empty_when_nothing_is_suitable(self) -> None:
        # A single-provider offline set must keep retrieving even when that
        # provider is unsuitable for the intent.
        assert prune_providers(QueryIntent.DEFINITIONAL, [SearchProvider.ARXIV]) == (
            SearchProvider.ARXIV,
        )

    def test_preserves_input_order(self) -> None:
        selected = prune_providers(
            QueryIntent.DEFINITIONAL,
            [SearchProvider.TAVILY, SearchProvider.WIKIMEDIA],
        )
        assert selected == (SearchProvider.TAVILY, SearchProvider.WIKIMEDIA)

    def test_deduplicates_repeated_inputs(self) -> None:
        selected = prune_providers(
            QueryIntent.GENERAL,
            [SearchProvider.ARXIV, SearchProvider.ARXIV, SearchProvider.WIKIMEDIA],
        )
        assert selected == (SearchProvider.ARXIV, SearchProvider.WIKIMEDIA)

    @pytest.mark.parametrize(
        ("question", "expected_hits"),
        [
            ("What is a prime number?", {SearchProvider.WIKIMEDIA}),
            ("Explain photosynthesis simply.", {SearchProvider.WIKIMEDIA}),
            ("How do I solve a quadratic?", {SearchProvider.WIKIMEDIA}),
        ],
    )
    def test_beginner_texts_prune_arxiv(
        self, question: str, expected_hits: set[SearchProvider]
    ) -> None:
        selected = prune_providers(
            classify_intent(question),
            [SearchProvider.ARXIV, SearchProvider.WIKIMEDIA],
        )
        assert set(selected) == expected_hits


class _QuestionFactory:
    """Build plan-less questions with a default all-provider strategy."""

    def __call__(self, text: str) -> ResearchQuestion:
        return ResearchQuestion(
            question_id="q1",
            text=text,
            topic="linear algebra",
            strategy=SearchStrategy(
                use_web=True,
                providers=list(_ALL_NAMES),
                queries=[],
            ),
        )


class TestRouterPrunesByQuestionIntent:
    def _router(self) -> tuple[ResearchRouter, dict[SearchProvider, RecordingProvider]]:
        fakes = {
            SearchProvider.ARXIV: RecordingProvider(SearchProvider.ARXIV, "arxiv.example"),
            SearchProvider.WIKIMEDIA: RecordingProvider(SearchProvider.WIKIMEDIA, "wiki.example"),
            SearchProvider.TAVILY: RecordingProvider(SearchProvider.TAVILY, "tavily.example"),
        }
        return ResearchRouter(providers=fakes), fakes

    def test_definitional_question_is_not_routed_to_arxiv(self) -> None:
        router, _ = self._router()
        strategy = router.plan(_QuestionFactory()("What is linear algebra?"))
        assert {query.provider for query in strategy.queries} == {
            SearchProvider.WIKIMEDIA,
            SearchProvider.TAVILY,
        }

    def test_academic_question_is_not_routed_to_encyclopedia(self) -> None:
        router, _ = self._router()
        strategy = router.plan(_QuestionFactory()("find papers about linear algebra"))
        assert {query.provider for query in strategy.queries} == {
            SearchProvider.ARXIV,
            SearchProvider.TAVILY,
        }

    def test_general_question_uses_every_available_provider(self) -> None:
        router, _ = self._router()
        strategy = router.plan(_QuestionFactory()("Who wrote the BLAS notes?"))
        assert {query.provider for query in strategy.queries} == {
            SearchProvider.ARXIV,
            SearchProvider.WIKIMEDIA,
            SearchProvider.TAVILY,
        }

    def test_query_budgets_survive_the_rebuild(self) -> None:
        router, _ = self._router()
        question = _QuestionFactory()("find papers about linear algebra")
        rebuilt = question.model_copy(
            update={
                "strategy": question.strategy.model_copy(
                    update={
                        "queries": [
                            SearchQuery(
                                query=question.text,
                                provider=SearchProvider.ARXIV,
                                max_results=3,
                            ),
                            SearchQuery(
                                query=question.text,
                                provider=SearchProvider.TAVILY,
                                max_results=7,
                            ),
                        ]
                    }
                )
            }
        )
        strategy = router.plan(rebuilt)
        budgets = {q.provider: q.max_results for q in strategy.queries}
        assert budgets[SearchProvider.ARXIV] == 3
        assert budgets[SearchProvider.TAVILY] == 7

    async def test_execution_never_calls_a_pruned_provider(self) -> None:
        router, fakes = self._router()
        question = _QuestionFactory()("What is linear algebra?")
        await router.execute([question])
        assert fakes[SearchProvider.ARXIV].queries == []
        assert fakes[SearchProvider.WIKIMEDIA].queries == ["What is linear algebra?"]


class TestBeginnerRunsHaveNoPreprintNoise:
    """End-to-end: a beginner run never retrieves preprint-type sources."""

    @pytest.mark.parametrize(
        "question",
        [
            "What is linear algebra?",
            "Explain linear algebra simply.",
            "How do I solve a linear equation?",
        ],
    )
    async def test_arxiv_is_never_asked(self, question: str) -> None:
        arxiv = RecordingProvider(SearchProvider.ARXIV, "arxiv.example")
        wiki = RecordingProvider(SearchProvider.WIKIMEDIA, "wiki.example")
        bundle = await build_research(
            RunContext(run_id="beginner"),
            product_spec_id="spec-1",
            research_questions=[question],
            topic="linear algebra",
            providers={SearchProvider.ARXIV: arxiv, SearchProvider.WIKIMEDIA: wiki},
        )
        assert arxiv.queries == []
        assert wiki.queries == [question]
        assert all(result.provider is SearchProvider.WIKIMEDIA for result in bundle.results)
        assert all("wiki.example" in claim.notes for claim in bundle.report.claims)

    async def test_academic_literature_question_still_finds_papers(self) -> None:
        arxiv = RecordingProvider(SearchProvider.ARXIV, "arxiv.example")
        wiki = RecordingProvider(SearchProvider.WIKIMEDIA, "wiki.example")
        bundle = await build_research(
            RunContext(run_id="academic"),
            product_spec_id="spec-1",
            research_questions=["find papers about linear algebra"],
            topic="linear algebra",
            providers={SearchProvider.ARXIV: arxiv, SearchProvider.WIKIMEDIA: wiki},
        )
        assert arxiv.queries == ["find papers about linear algebra"]
        assert wiki.queries == []
        assert all(result.provider is SearchProvider.ARXIV for result in bundle.results)

    async def test_current_question_still_finds_recent_work(self) -> None:
        arxiv = RecordingProvider(SearchProvider.ARXIV, "arxiv.example")
        await build_research(
            RunContext(run_id="current"),
            product_spec_id="spec-1",
            research_questions=["latest research on linear algebra"],
            topic="linear algebra",
            providers={SearchProvider.ARXIV: arxiv},
        )
        assert arxiv.queries == ["latest research on linear algebra"]

    async def test_offline_mock_definitional_run_is_unchanged(self) -> None:
        bundle = await build_research(
            RunContext(run_id="offline-def"),
            product_spec_id="spec-1",
            research_questions=["What is linear algebra?"],
            topic="linear algebra",
            providers=default_providers(RunContext(run_id="offline-def")),
        )
        assert {result.provider for result in bundle.results} == {SearchProvider.MOCK}
        assert {result.domain for result in bundle.results} == {"reference.example"}
