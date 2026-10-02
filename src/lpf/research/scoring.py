"""Ranking and confidence scoring for research results.

Two deliberately different numbers come out of this module:

``ranking_score``
    Intent-conditional and audience-aware. Answers "which source should the
    learner read first". This is a *preference* ordering and its absolute value
    means little.

``confidence``
    Compares evidence quality and on-topic-ness, and is deliberately
    *independent of the intent profile*. It answers "does this source actually
    support the claim", which has to mean the same thing across intents or the
    EvidenceMap support threshold would mean something different per query.

Collapsing these into one number is what would re-create the permanently-empty
EvidenceMap bug: an academic-only ranking profile scores an on-topic
encyclopedia article below threshold purely because its tier is SECONDARY.

Every component is deterministic. Freshness is measured *relative to the
newest source in the same run* rather than against wall-clock time, so the same
provider responses always produce the same scores.
"""

from __future__ import annotations

import re
from typing import Final

from lpf.research.audience import AudienceLevel
from lpf.research.audience import audience_fit as _audience_fit
from lpf.research.intent import QueryIntent, authority_fit, ranking_weights
from lpf.research.relevance import lexical_relevance
from lpf.schemas.research import SearchResult, SourceAuthority

# Phrases that mark a passage as *defining* or *explaining* its topic rather
# than merely mentioning it. Without these, token overlap rates a specialist
# paper and a definitional article identically (both 1.0), which is precisely
# the failure the Beginner Definition Retrieval benchmark exists to catch.
_DEFINITION_CUES: Final = (
    "is the branch of",
    "is a branch of",
    "is the study of",
    "is a field of",
    "refers to",
    "is defined as",
    "is defined by",
    "is the process",
    "is the theory",
    "is the mathematical",
    "is an area of",
    "in mathematics,",
    "in biology,",
    "in physics,",
    "in chemistry,",
    "is a method",
    "is a technique",
    "is a form of",
    "means that",
    "that is,",
    "is used to",
    "can be defined",
    "is usually defined",
    "describes",
)

# Jargon and notation density markers. Presence of these indicates the text is
# written for a specialist rather than a beginner. Deliberately subject-agnostic:
# LaTeX and standard mathematical notation rather than any one field's jargon,
# so the same weights work for a biology or history query.
_DENSITY_MARKERS: Final = (
    "$",
    "\\",
    "^{",
    "_{",
    "∈",
    "∀",
    "∃",
    "≤",
    "≥",
    "⊗",
    "≡",
    "ℂ",
    "ℝ",
    "et al",
    "theorem",
    "lemma",
    "we prove",
    "we show that",
)

# Weight given to lexical coverage within ``intent_match``; the remainder goes to
# the intent-specific cue. Coverage alone cannot separate a definitional article
# from a specialist paper that mentions the same terms.
_COVERAGE_WEIGHT: Final = 0.6

_SENTENCE_SPLIT: Final = re.compile(r"[.!?]+")
_WORD: Final = re.compile(r"[A-Za-z']+")

# Average words per sentence that reads comfortably. Used as a soft target
# rather than a hard cutoff, since terse entries can also be well written.
_IDEAL_SENTENCE_WORDS: Final = 18.0


def has_definition_cue(title: str, snippet: str) -> bool:
    """True when the text reads as a definition or explanation of its topic."""
    text = f"{title} {snippet}".lower()
    return any(cue in text for cue in _DEFINITION_CUES)


def intent_match(result: SearchResult, query: str, intent: QueryIntent) -> float:
    """How well a source answers the question that was asked.

    Blends lexical coverage with a definition-cue signal. The two are combined
    by weighted average rather than by adding a bonus: an additive bonus
    saturates, because a source that already covers every query term scores
    1.0 and stays 1.0 no matter what is added. That made a specialist paper and
    a definitional article tie at exactly 1.0.
    """
    coverage = lexical_relevance(query, result.title, result.snippet)
    if coverage <= 0.0:
        return 0.0

    if intent in (QueryIntent.DEFINITIONAL, QueryIntent.EXPLANATORY):
        cue = 1.0 if has_definition_cue(result.title, result.snippet) else 0.0
        return round(_COVERAGE_WEIGHT * coverage + (1.0 - _COVERAGE_WEIGHT) * cue, 4)

    if intent is QueryIntent.PROCEDURAL:
        steps = (
            1.0
            if re.search(
                r"\b(step|steps|first|then|next|finally|example)\b",
                result.snippet,
                re.IGNORECASE,
            )
            else 0.0
        )
        return round(0.85 * coverage + 0.15 * steps, 4)

    return coverage


def specialist_density(title: str, snippet: str) -> float:
    """Fraction of specialist markers present, in ``[0, 1]``.

    A crude, deterministic readability proxy. It is not a measure of
    difficulty; it measures whether the text *looks* like it was written for
    someone who already knows the field.
    """
    text = f"{title} {snippet}".lower()
    if not text.strip():
        return 0.0

    hits = sum(text.count(marker.lower()) for marker in _DENSITY_MARKERS)
    # Saturating: a handful of markers already signals specialist prose.
    return round(min(1.0, hits / 6.0), 4)


def clarity(title: str, snippet: str) -> float:
    """Readability proxy combining sentence length and notation density.

    Deterministic and cheap. Long sentences and heavy notation both reduce the
    score; there is no model and no vocabulary database involved.
    """
    text = f"{title}. {snippet}".strip()
    if not text:
        return 0.0

    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    words = _WORD.findall(text)
    if not words:
        return 0.0

    avg_words = len(words) / max(1, len(sentences))

    # Full marks near the ideal, decaying as sentences get longer.
    length_score = max(0.0, 1.0 - abs(avg_words - _IDEAL_SENTENCE_WORDS) / _IDEAL_SENTENCE_WORDS)

    density = specialist_density(title, snippet)
    density_score = 1.0 - density

    return round(max(0.0, min(1.0, 0.5 * length_score + 0.5 * density_score)), 4)


def freshness(result: SearchResult, oldest: float, newest: float) -> float:
    """Corpus-relative freshness in ``[0, 1]``.

    Argument order matches ``date_span``'s ``(oldest, newest)`` return so the two
    compose without transposition.

    The freshest source in the run scores 1.0 and the oldest 0.0, so scores do
    not drift with wall-clock time. An undated source scores a neutral 0.5:
    ``published_at`` is populated by arXiv and Tavily only, and treating a
    missing date as fresh would silently reward the providers that omit it.
    """
    if result.published_at is None or newest <= oldest:
        return 0.5
    span = newest - oldest
    return round(min(1.0, max(0.0, (result.published_at - oldest) / span)), 4)


def audience_fit_for(result: SearchResult, level: AudienceLevel) -> float:
    """Audience appropriateness for a single result."""
    density = specialist_density(result.title, result.snippet)
    return _audience_fit(level, result.authority, density)


def components(
    result: SearchResult,
    *,
    query: str,
    intent: QueryIntent,
    audience: AudienceLevel,
    oldest: float,
    newest: float,
) -> dict[str, float]:
    """All five ranking components for one result, each in ``[0, 1]``."""
    return {
        "intent_match": intent_match(result, query, intent),
        "audience_fit": audience_fit_for(result, audience),
        "clarity": clarity(result.title, result.snippet),
        "authority_fit": authority_fit(intent, result.authority),
        "freshness": freshness(result, oldest, newest),
    }


def ranking_score(
    result: SearchResult,
    *,
    query: str,
    intent: QueryIntent,
    audience: AudienceLevel,
    oldest: float,
    newest: float,
) -> float:
    """Intent-weighted preference score used for ordering results."""
    weights = ranking_weights(intent)
    parts = components(
        result,
        query=query,
        intent=intent,
        audience=audience,
        oldest=oldest,
        newest=newest,
    )
    return round(sum(weights[key] * parts[key] for key in weights), 6)


def confidence(
    result: SearchResult,
    *,
    query: str,
    intent: QueryIntent,
) -> float:
    """Evidence support in ``[0, 1]``, comparable across intents.

    Intentionally excludes audience fit, clarity and freshness: those express
    pedagogical preference, not whether a source backs the claim. Including
    them would let an intent profile change how much evidence counts as
    sufficient.
    """
    on_topic = intent_match(result, query, intent)
    fit = authority_fit(intent, result.authority)
    return round(0.5 * on_topic + 0.5 * fit, 4)


def date_span(results: list[SearchResult]) -> tuple[float, float]:
    """Newest and oldest known timestamps across ``results``.

    Returns ``(0.0, 0.0)`` when no source carries a date, which makes
    ``freshness`` return its neutral 0.5 for every result.
    """
    dates = [r.published_at for r in results if r.published_at is not None]
    if not dates:
        return 0.0, 0.0
    return min(dates), max(dates)


__all__ = [
    "QueryIntent",
    "AudienceLevel",
    "SourceAuthority",
    "authority_fit",
    "audience_fit_for",
    "clarity",
    "components",
    "confidence",
    "date_span",
    "freshness",
    "has_definition_cue",
    "intent_match",
    "ranking_score",
    "specialist_density",
]
