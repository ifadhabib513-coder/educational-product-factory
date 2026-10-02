"""Deterministic query-intent classification and intent-conditioned profiles.

A single universal ranking formula is wrong for educational retrieval. "What is
linear algebra?" and "find papers about linear algebra" want opposite sources.
Lowering arXiv's global weight fixes the first query and breaks the second, so
authority is made *conditional on intent* instead.

Classification is rule-based rather than model-based on purpose: it keeps the
property that the same query always yields the same intent, which is what makes
the ranking reproducible and the tests meaningful. A model could replace
``classify_intent`` later without changing anything downstream.

Ordering matters. ``CURRENT`` is checked before ``ACADEMIC_LITERATURE`` so that
"latest research on X" resolves to a freshness-sensitive intent rather than
falling into the paper-finding bucket.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final

from lpf.schemas.research import SourceAuthority


class QueryIntent(StrEnum):
    """What the learner is actually asking for."""

    DEFINITIONAL = "definitional"
    """What is X? Wants a definition or orientation."""

    EXPLANATORY = "explanatory"
    """Explain X simply. Wants understanding at a readable level."""

    PROCEDURAL = "procedural"
    """How do I solve X? Wants steps or a worked method."""

    ACADEMIC_LITERATURE = "academic_literature"
    """Find papers about X. Wants primary academic sources."""

    EVIDENCE_SYNTHESIS = "evidence_synthesis"
    """What does research say? Wants what the body of evidence concludes."""

    CURRENT = "current"
    """Latest/recent. Wants recent material above all."""

    GENERAL = "general"
    """No clear signal; fall back to a balanced profile."""


# Checked in order; first match wins. More specific intents precede broader ones.
_INTENT_PATTERNS: Final[tuple[tuple[QueryIntent, re.Pattern[str]], ...]] = (
    (
        QueryIntent.CURRENT,
        re.compile(
            r"\b(latest|recent|newest|this year|this month|current|up[- ]to[- ]date|"
            r"\b20[2-9]\d\b)\b",
            re.IGNORECASE,
        ),
    ),
    (
        QueryIntent.EVIDENCE_SYNTHESIS,
        re.compile(
            r"(what does (the )?research|research (say|show|shows|suggest|suggests)|"
            r"evidence (for|about|that)|consensus|meta[- ]analys|systematic review|"
            r"what do (we|studies) know)",
            re.IGNORECASE,
        ),
    ),
    (
        QueryIntent.ACADEMIC_LITERATURE,
        re.compile(
            r"(papers? (about|on|regarding)|research (papers?|articles?|literature)|"
            r"peer[- ]reviewed|preprint|publications? (about|on)|"
            r"scholarly|literature (about|on|review)|academic (papers?|sources?)|"
            r"\bstudies\b (about|on)|find (me )?(papers?|articles?|studies))",
            re.IGNORECASE,
        ),
    ),
    (
        QueryIntent.PROCEDURAL,
        re.compile(
            r"(how (do|can|to) (i|we|you)|step[- ]by[- ]step|walk me through|"
            r"tutorial|worked (example|problem)|solve (this|for|how)|"
            r"calculate|compute|deri?v?e|algorithm for)",
            re.IGNORECASE,
        ),
    ),
    (
        QueryIntent.DEFINITIONAL,
        re.compile(
            r"(what (is|are|was|were)\b|define\b|definition of|meaning of|"
            r"what does .{0,30} (mean|refer to)|introduction to)",
            re.IGNORECASE,
        ),
    ),
    (
        QueryIntent.EXPLANATORY,
        re.compile(
            r"(explain|understand|why (do|does|is|are)|how does .{0,30} work|"
            r"in simple terms|simply|eli5|eli5|overview of|describe)",
            re.IGNORECASE,
        ),
    ),
)


def classify_intent(query: str) -> QueryIntent:
    """Return the intent implied by ``query``.

    Deterministic and model-free: identical input always yields identical output.
    """
    text = query.strip()
    if not text:
        return QueryIntent.GENERAL

    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(text):
            return intent

    return QueryIntent.GENERAL


# --- intent-conditioned weight profiles ------------------------------------
# Weights sum to 1.0. These replace the single universal formula.

RankingWeights = dict[str, float]

_PROFILES: Final[dict[QueryIntent, RankingWeights]] = {
    QueryIntent.DEFINITIONAL: {
        "intent_match": 0.40,
        "audience_fit": 0.25,
        "clarity": 0.25,
        "authority_fit": 0.10,
        "freshness": 0.00,
    },
    QueryIntent.EXPLANATORY: {
        "intent_match": 0.25,
        "audience_fit": 0.35,
        "clarity": 0.30,
        "authority_fit": 0.10,
        "freshness": 0.00,
    },
    QueryIntent.PROCEDURAL: {
        "intent_match": 0.35,
        "audience_fit": 0.30,
        "clarity": 0.20,
        "authority_fit": 0.10,
        "freshness": 0.05,
    },
    QueryIntent.ACADEMIC_LITERATURE: {
        "intent_match": 0.20,
        "audience_fit": 0.05,
        "clarity": 0.05,
        "authority_fit": 0.65,
        "freshness": 0.05,
    },
    QueryIntent.EVIDENCE_SYNTHESIS: {
        "intent_match": 0.25,
        "audience_fit": 0.05,
        "clarity": 0.10,
        "authority_fit": 0.55,
        "freshness": 0.05,
    },
    QueryIntent.CURRENT: {
        "intent_match": 0.20,
        "audience_fit": 0.05,
        "clarity": 0.05,
        "authority_fit": 0.45,
        "freshness": 0.25,
    },
    QueryIntent.GENERAL: {
        "intent_match": 0.30,
        "audience_fit": 0.20,
        "clarity": 0.15,
        "authority_fit": 0.30,
        "freshness": 0.05,
    },
}

_RANKING_KEYS: Final = (
    "intent_match",
    "audience_fit",
    "clarity",
    "authority_fit",
    "freshness",
)


def ranking_weights(intent: QueryIntent) -> RankingWeights:
    """Weight profile for ``intent``. Returned as a copy to stay immutable."""
    return dict(_PROFILES[intent])


def validate_weights(intent: QueryIntent) -> None:
    """Raise if a profile does not sum to 1.0 or names an unknown component."""
    weights = ranking_weights(intent)
    unknown = set(weights) - set(_RANKING_KEYS)
    if unknown:
        raise ValueError(f"unknown ranking components for {intent}: {sorted(unknown)}")
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"weights for {intent} sum to {total}, expected 1.0")


# --- intent-conditioned authority fit --------------------------------------
# How appropriate is this authority tier *for this intent*?
#
# This is the core of intent-conditional authority. An encyclopedia article is
# ideal evidence for "What is X?" and nearly useless for "Find papers about X",
# while a preprint is the reverse. A flat authority rank cannot express that,
# and using one either buries good beginner sources or floods literature reviews
# with blogs.

_AUTHORITY_FIT: Final[dict[QueryIntent, dict[SourceAuthority, float]]] = {
    QueryIntent.DEFINITIONAL: {
        SourceAuthority.PRIMARY: 0.55,
        SourceAuthority.INSTITUTIONAL: 0.70,
        SourceAuthority.TEXTBOOK: 0.95,
        SourceAuthority.EDUCATIONAL: 1.00,
        SourceAuthority.SECONDARY: 1.00,
        SourceAuthority.ACADEMIC: 0.45,
        SourceAuthority.GENERAL: 0.35,
        SourceAuthority.UNKNOWN: 0.20,
    },
    QueryIntent.EXPLANATORY: {
        SourceAuthority.PRIMARY: 0.60,
        SourceAuthority.INSTITUTIONAL: 0.80,
        SourceAuthority.TEXTBOOK: 0.95,
        SourceAuthority.EDUCATIONAL: 1.00,
        SourceAuthority.SECONDARY: 0.95,
        SourceAuthority.ACADEMIC: 0.50,
        SourceAuthority.GENERAL: 0.40,
        SourceAuthority.UNKNOWN: 0.20,
    },
    QueryIntent.PROCEDURAL: {
        SourceAuthority.PRIMARY: 0.70,
        SourceAuthority.INSTITUTIONAL: 0.85,
        SourceAuthority.TEXTBOOK: 1.00,
        SourceAuthority.EDUCATIONAL: 1.00,
        SourceAuthority.SECONDARY: 0.80,
        SourceAuthority.ACADEMIC: 0.55,
        SourceAuthority.GENERAL: 0.45,
        SourceAuthority.UNKNOWN: 0.20,
    },
    QueryIntent.ACADEMIC_LITERATURE: {
        SourceAuthority.PRIMARY: 1.00,
        SourceAuthority.INSTITUTIONAL: 0.95,
        SourceAuthority.TEXTBOOK: 0.45,
        SourceAuthority.EDUCATIONAL: 0.35,
        SourceAuthority.SECONDARY: 0.30,
        SourceAuthority.ACADEMIC: 1.00,
        SourceAuthority.GENERAL: 0.25,
        SourceAuthority.UNKNOWN: 0.15,
    },
    QueryIntent.EVIDENCE_SYNTHESIS: {
        SourceAuthority.PRIMARY: 1.00,
        SourceAuthority.INSTITUTIONAL: 0.95,
        SourceAuthority.TEXTBOOK: 0.45,
        SourceAuthority.EDUCATIONAL: 0.40,
        SourceAuthority.SECONDARY: 0.45,
        SourceAuthority.ACADEMIC: 1.00,
        SourceAuthority.GENERAL: 0.30,
        SourceAuthority.UNKNOWN: 0.15,
    },
    QueryIntent.CURRENT: {
        SourceAuthority.PRIMARY: 0.95,
        SourceAuthority.INSTITUTIONAL: 0.90,
        SourceAuthority.TEXTBOOK: 0.30,
        SourceAuthority.EDUCATIONAL: 0.35,
        SourceAuthority.SECONDARY: 0.55,
        SourceAuthority.ACADEMIC: 0.95,
        SourceAuthority.GENERAL: 0.40,
        SourceAuthority.UNKNOWN: 0.15,
    },
    QueryIntent.GENERAL: {
        SourceAuthority.PRIMARY: 0.90,
        SourceAuthority.INSTITUTIONAL: 0.95,
        SourceAuthority.TEXTBOOK: 0.80,
        SourceAuthority.EDUCATIONAL: 0.85,
        SourceAuthority.SECONDARY: 0.70,
        SourceAuthority.ACADEMIC: 0.85,
        SourceAuthority.GENERAL: 0.50,
        SourceAuthority.UNKNOWN: 0.20,
    },
}


def authority_fit(intent: QueryIntent, authority: SourceAuthority) -> float:
    """How well ``authority`` serves ``intent``, in ``[0, 1]``.

    Falls back to the GENERAL profile for an unlisted combination so a newly
    added tier degrades gracefully instead of raising mid-ranking.
    """
    profile = _AUTHORITY_FIT.get(intent, _AUTHORITY_FIT[QueryIntent.GENERAL])
    return profile.get(authority, profile[SourceAuthority.UNKNOWN])
