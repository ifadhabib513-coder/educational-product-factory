"""Research router — question → SearchPlan → provider execution."""

from __future__ import annotations

import logging
from collections import defaultdict

from lpf.research.intent import classify_intent
from lpf.research.providers.base import SearchProviderProto
from lpf.research.routing import prune_providers
from lpf.schemas.research import (
    ResearchQuestion,
    SearchProvider,
    SearchQuery,
    SearchStrategy,
)

logger = logging.getLogger(__name__)


def _max_results_for(strategy: SearchStrategy, provider: SearchProvider) -> int:
    """Preserve a plan's per-provider result budget when rebuilding queries."""
    for query in strategy.queries:
        if query.provider is provider:
            return query.max_results
    return 10


class ResearchRouter:
    """Routes research questions to appropriate search providers.

    Creates a SearchPlan for each question, then executes searches
    across configured providers. Each question's strategy is rebuilt so only
    providers suitable for its intent are queried.
    """

    def __init__(
        self,
        providers: dict[SearchProvider, SearchProviderProto] | None = None,
    ) -> None:
        self._providers = providers or {}

    def plan(self, question: ResearchQuestion) -> SearchStrategy:
        """Create a search strategy for a research question.

        The strategy is rebuilt per question: providers are pruned to those
        suitable for the question's intent (see :mod:`lpf.research.routing`),
        and queries are regenerated for the surviving providers. A question
        arriving with a pre-pruned strategy is a no-op, so plan artifacts and
        plan-less execution agree on which providers ran.
        """
        strategy = question.strategy

        # Ensure at least one provider is configured
        available = [p for p in strategy.providers if p in self._providers]
        if not available:
            # Fall back to any available provider
            available = list(self._providers.keys())[:1]

        selected = prune_providers(classify_intent(question.text), available)
        queries = [
            SearchQuery(
                query=question.text,
                provider=provider,
                max_results=_max_results_for(strategy, provider),
            )
            for provider in selected
        ]

        return SearchStrategy(
            use_web=strategy.use_web,
            use_academic=strategy.use_academic,
            use_wikipedia=strategy.use_wikipedia,
            use_official=strategy.use_official,
            providers=list(selected),
            queries=queries,
        )

    async def execute(
        self,
        questions: list[ResearchQuestion],
    ) -> dict[str, list]:
        """Execute searches for all questions.

        Returns mapping of question_id → list of SearchResult.
        """
        results: dict[str, list] = defaultdict(list)

        for question in questions:
            strategy = self.plan(question)
            for query in strategy.queries:
                provider = self._providers.get(query.provider)
                if provider is None:
                    logger.warning(
                        "Provider %s not available for query: %s",
                        query.provider.value,
                        query.query,
                    )
                    continue

                try:
                    search_results = await provider.search(
                        query.query, max_results=query.max_results
                    )
                    results[question.question_id].extend(search_results)
                    logger.info(
                        "Provider %s returned %d results for question %s",
                        query.provider.value,
                        len(search_results),
                        question.question_id,
                    )
                except Exception as e:
                    logger.error(
                        "Provider %s failed for question %s: %s",
                        query.provider.value,
                        question.question_id,
                        e,
                    )

        return dict(results)

    def register_provider(self, provider: SearchProviderProto) -> None:
        """Register a search provider."""
        self._providers[provider.provider_name] = provider

    @property
    def available_providers(self) -> list[SearchProvider]:
        return list(self._providers.keys())
