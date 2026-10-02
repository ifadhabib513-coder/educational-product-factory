"""Audience level and audience fit.

The audience is decided upstream in Discovery (``LearnerProfile.level``) and
threaded down, rather than re-inferred from the query text. Discovery already
knows who the learner is, so inferring it again per question would be both less
accurate and harder to test.

``LearnerProfile.level`` is free text ("beginner", "Year 2", "advanced"), so
normalisation maps it onto a small closed set.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final

from lpf.schemas.research import SourceAuthority


class AudienceLevel(StrEnum):
    """How much background the reader is assumed to have."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


_LEVEL_PATTERNS: Final[tuple[tuple[AudienceLevel, re.Pattern[str]], ...]] = (
    (
        AudienceLevel.BEGINNER,
        re.compile(
            r"\b(beginner|begining|novice|new to|introduct|elementary|primary|"
            r"secondary|high school|gcse|ks3|ks4|alevel|a[- ]level|intro|"
            r"first year|1st year|year (1|one)\b|complete beginner|no (prior|background)|"
            r"zero experience|start(ing)? from scratch|child|kids?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        AudienceLevel.ADVANCED,
        re.compile(
            r"\b(advanced|expert|postgraduate|post[- ]grad|graduate|phd|"
            r"doctoral|master'?s|msc|m\.?sc\.?|ma\b|third year|3rd year|"
            r"final year|undergraduate|college|university level|specialist|"
            r"practitioner|professional)\b",
            re.IGNORECASE,
        ),
    ),
    (
        AudienceLevel.INTERMEDIATE,
        re.compile(
            r"\b(intermediate|second year|2nd year|year two|some (background|"
            r"experience|knowledge)|basic|working knowledge)\b",
            re.IGNORECASE,
        ),
    ),
)


def classify_audience(level: str | AudienceLevel | None) -> AudienceLevel:
    """Normalise a free-text learner level onto a closed set.

    Unknown or missing levels become ``INTERMEDIATE``: the middle choice is
    less damaging than defaulting beginners to material written for specialists.
    """
    if isinstance(level, AudienceLevel):
        return level
    if not level or not level.strip():
        return AudienceLevel.INTERMEDIATE

    text = level.strip()
    for candidate, pattern in _LEVEL_PATTERNS:
        if pattern.search(text):
            return candidate

    return AudienceLevel.INTERMEDIATE


# --- audience fit ----------------------------------------------------------
# Two signals: is the authority tier appropriate for this reader, and does the
# text read at their level.

_TIER_FIT: Final[dict[AudienceLevel, dict[SourceAuthority, float]]] = {
    AudienceLevel.BEGINNER: {
        SourceAuthority.PRIMARY: 0.55,
        SourceAuthority.INSTITUTIONAL: 0.70,
        SourceAuthority.TEXTBOOK: 0.95,
        SourceAuthority.EDUCATIONAL: 1.00,
        SourceAuthority.SECONDARY: 0.95,
        SourceAuthority.ACADEMIC: 0.25,
        SourceAuthority.GENERAL: 0.60,
        SourceAuthority.UNKNOWN: 0.30,
    },
    AudienceLevel.INTERMEDIATE: {
        SourceAuthority.PRIMARY: 0.70,
        SourceAuthority.INSTITUTIONAL: 0.85,
        SourceAuthority.TEXTBOOK: 0.95,
        SourceAuthority.EDUCATIONAL: 0.90,
        SourceAuthority.SECONDARY: 0.85,
        SourceAuthority.ACADEMIC: 0.60,
        SourceAuthority.GENERAL: 0.65,
        SourceAuthority.UNKNOWN: 0.35,
    },
    AudienceLevel.ADVANCED: {
        SourceAuthority.PRIMARY: 0.95,
        SourceAuthority.INSTITUTIONAL: 0.95,
        SourceAuthority.TEXTBOOK: 0.70,
        SourceAuthority.EDUCATIONAL: 0.60,
        SourceAuthority.SECONDARY: 0.60,
        SourceAuthority.ACADEMIC: 1.00,
        SourceAuthority.GENERAL: 0.45,
        SourceAuthority.UNKNOWN: 0.30,
    },
}

# Density penalty applied to specialist prose for less-advanced readers.
_DENSITY_PENALTY: Final[dict[AudienceLevel, float]] = {
    AudienceLevel.BEGINNER: 1.0,
    AudienceLevel.INTERMEDIATE: 0.5,
    AudienceLevel.ADVANCED: 0.0,
}


def tier_fit(level: AudienceLevel, authority: SourceAuthority) -> float:
    """How appropriate this authority tier is for ``level``."""
    profile = _TIER_FIT[level]
    return profile.get(authority, profile[SourceAuthority.UNKNOWN])


def apply_density_penalty(level: AudienceLevel, density: float) -> float:
    """Scale a 0-1 specialist-density measure down by reader level.

    A paper dense in notation is penalised fully for a beginner, not at all for
    an expert, because for them the notation is the content rather than a barrier.
    """
    return density * _DENSITY_PENALTY[level]


def audience_fit(
    level: AudienceLevel,
    authority: SourceAuthority,
    density: float,
) -> float:
    """Blend tier appropriateness with a readability penalty.

    The penalty is capped at 0.35 so that a highly authoritative source can
    still rank for an advanced audience without density erasing it entirely.
    """
    base = tier_fit(level, authority)
    penalty = min(0.35, apply_density_penalty(level, density))
    return round(max(0.0, base - penalty), 4)
