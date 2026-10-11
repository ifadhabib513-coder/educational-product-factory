"""Intent-aware provider selection for research retrieval.

Retrieval was unrefined: every question was sent to every provider regardless of
what the learner was asking. arXiv can only return preprints, so a beginner's
"What is X?" pulled in papers the scorer rejects by design — plausible sources
that rank nowhere and add noise.

This module answers "which providers are *suitable* for this intent". It is a
prune, deliberately: a provider that cannot serve an intent is not asked at all,
which is cheaper and cleaner than scraping its returns and hoping the ranker
buries them. ``prune_providers`` never returns an empty set — when nothing
suitable is configured the caller's providers are kept, because an offline run
that injects only one provider must not silently stop retrieving.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from lpf.research.intent import QueryIntent
from lpf.schemas.research import SearchProvider

__all__ = ["provider_suitability", "prune_providers"]

#: The provider set each intent actually wants.
#:
#: * Beginner intents (definitional/explanatory/procedural) exclude ``ARXIV``:
#:   preprints cannot serve "what is X" teaching and only add rejected noise.
#: * Academic/synthesis/current intents keep ``ARXIV`` and drop encyclopedic
#:   ``WIKIMEDIA`` — a paper hunt is not served by encyclopedia articles.
#: * ``GENERAL`` keeps everything; it is the no-signal fallback.
#: * ``MOCK`` and ``OFFICIAL`` are inert entries present in every set so the
#:   deterministic offline provider is never pruned away by accident.
_INTENT_PROVIDER_SUITABILITY: Final[dict[QueryIntent, frozenset[SearchProvider]]] = {
    QueryIntent.DEFINITIONAL: frozenset(
        {
            SearchProvider.WIKIMEDIA,
            SearchProvider.TAVILY,
            SearchProvider.SEARXNG,
            SearchProvider.MOCK,
            SearchProvider.OFFICIAL,
        }
    ),
    QueryIntent.EXPLANATORY: frozenset(
        {
            SearchProvider.WIKIMEDIA,
            SearchProvider.TAVILY,
            SearchProvider.SEARXNG,
            SearchProvider.MOCK,
            SearchProvider.OFFICIAL,
        }
    ),
    QueryIntent.PROCEDURAL: frozenset(
        {
            SearchProvider.TAVILY,
            SearchProvider.SEARXNG,
            SearchProvider.WIKIMEDIA,
            SearchProvider.MOCK,
            SearchProvider.OFFICIAL,
        }
    ),
    QueryIntent.ACADEMIC_LITERATURE: frozenset(
        {
            SearchProvider.ARXIV,
            SearchProvider.SEARXNG,
            SearchProvider.TAVILY,
            SearchProvider.MOCK,
            SearchProvider.OFFICIAL,
        }
    ),
    QueryIntent.EVIDENCE_SYNTHESIS: frozenset(
        {
            SearchProvider.ARXIV,
            SearchProvider.SEARXNG,
            SearchProvider.TAVILY,
            SearchProvider.MOCK,
            SearchProvider.OFFICIAL,
        }
    ),
    QueryIntent.CURRENT: frozenset(
        {
            SearchProvider.ARXIV,
            SearchProvider.SEARXNG,
            SearchProvider.TAVILY,
            SearchProvider.MOCK,
            SearchProvider.OFFICIAL,
        }
    ),
    QueryIntent.GENERAL: frozenset(
        {
            SearchProvider.WIKIMEDIA,
            SearchProvider.TAVILY,
            SearchProvider.SEARXNG,
            SearchProvider.ARXIV,
            SearchProvider.MOCK,
            SearchProvider.OFFICIAL,
        }
    ),
}

_GENERAL_SUITABLE: Final = _INTENT_PROVIDER_SUITABILITY[QueryIntent.GENERAL]


def provider_suitability(intent: QueryIntent) -> frozenset[SearchProvider]:
    """The providers that can actually serve ``intent``."""
    return _INTENT_PROVIDER_SUITABILITY.get(intent, _GENERAL_SUITABLE)


def prune_providers(
    intent: QueryIntent,
    providers: Iterable[SearchProvider],
) -> tuple[SearchProvider, ...]:
    """Prune ``providers`` down to those suitable for ``intent``.

    Returns the input order-preserving, and never returns empty: when none of
    the configured providers are suitable the full list is returned so a
    single-provider offline set (``MOCK``) keeps retrieving.
    """
    seen: dict[SearchProvider, None] = {}
    for provider in providers:
        if provider in seen:
            continue
        seen[provider] = None
    unique = list(seen)

    suitable = provider_suitability(intent)
    selected = [provider for provider in unique if provider in suitable]
    if not selected:
        return tuple(unique)
    return tuple(selected)
