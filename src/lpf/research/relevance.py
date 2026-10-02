"""Deterministic lexical relevance scoring.

Only Tavily returns a native relevance score from its search backend. The other
providers return ranked-but-unscored results, leaving ``relevance_score`` at its
schema default of ``0.0``. That zero previously flowed straight into claim
confidence, capping it at ``authority_rank / 7 * authority_weight`` — at most
0.4, and 0.2857 for academic sources. Every real claim therefore fell below the
0.7 evidence-map support threshold and every report came back with an empty
EvidenceMap.

This module supplies a query-coverage score for those providers. It is plain
token overlap: no model, no network, and the same input always yields the same
number.
"""

from __future__ import annotations

import re
from typing import Final

_TOKEN_PATTERN: Final = re.compile(r"[a-z0-9]+")

# Deliberately small. A large stopword list would add maintenance cost without
# changing scores meaningfully, since coverage is computed against query terms.
_STOPWORDS: Final = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "there",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "will",
        "with",
    }
)


def _fold(token: str) -> str:
    """Crude singularisation: drop a plural trailing ``s``.

    Full stemming is out of scope, but without at least this, "seasons" does not
    match "Season" and definitional questions score zero against the very article
    that answers them. Words ending in ``ss`` are left alone.
    """
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric tokens, singularised, with stopwords removed."""
    return {
        folded
        for t in _TOKEN_PATTERN.findall(text.lower())
        if t not in _STOPWORDS and (folded := _fold(t))
    }


def lexical_relevance(query: str, title: str = "", snippet: str = "") -> float:
    """Fraction of meaningful query terms covered by the document.

    Returns 0.0 for an empty query or a query made entirely of stopwords, since
    there is nothing to match against.

    Title matches are weighted double: a term in the title is a stronger signal
    than the same term buried in a snippet.
    """
    query_terms = tokenize(query)
    if not query_terms:
        return 0.0

    title_terms = tokenize(title)
    snippet_terms = tokenize(snippet)

    matched_in_title = query_terms & title_terms
    matched_in_snippet = (query_terms & snippet_terms) - matched_in_title

    score = (len(matched_in_title) * 2 + len(matched_in_snippet)) / (len(query_terms) * 2)
    return round(min(1.0, score), 4)


def effective_relevance(
    query: str,
    *,
    provider_score: float,
    title: str = "",
    snippet: str = "",
) -> float:
    """Prefer a provider-supplied score; fall back to lexical coverage.

    Tavily supplies a real backend score, so it is trusted as-is. Providers that
    report nothing pass ``0.0`` and receive a derived score instead.
    """
    if provider_score > 0.0:
        return provider_score
    return lexical_relevance(query, title, snippet)
