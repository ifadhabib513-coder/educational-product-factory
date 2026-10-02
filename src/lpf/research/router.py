"""Research router — question → SearchPlan → provider execution."""

from __future__ import annotations

import logging
from collections import defaultdict

from lpf.research.providers.base import SearchProviderProto
from lpf.schemas.research import (
    ResearchQuestion,
    SearchProvider,
    SearchQuery,
    SearchStrategy,
)

logger = logging.getLogger(__name__)


class ResearchRouter:
    """Routes research questions to appropriate search providers.

    Creates a SearchPlan for each question, then executes searches
    across configured providers.
    """

    def __init__(
        self,
        providers: dict[SearchProvider, SearchProviderProto] | None = None,
    ) -> None:
        self._providers = providers or {}

    def plan(self, question: ResearchQuestion) -> SearchStrategy:
        """Create a search strategy for a research question."""
        strategy = question.strategy

        # Ensure at least one provider is configured
        available = [p for p in strategy.providers if p in self._providers]
        if not available:
            # Fall back to any available provider
            available = list(self._providers.keys())[:1]
            strategy = SearchStrategy(
                use_web=True,
                providers=available,
                queries=[SearchQuery(query=question.text, provider=p) for p in available],
            )

        return strategy

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
