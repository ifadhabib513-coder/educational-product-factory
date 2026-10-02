"""Tests for deterministic authority classification."""

from __future__ import annotations

import pytest

from lpf.research.authority import (
    authority_rank,
    classify_authority,
    extract_domain,
    is_known_domain,
)
from lpf.schemas.research import SourceAuthority


class TestExtractDomain:
    def test_https_url(self) -> None:
        assert extract_domain("https://arxiv.org/abs/1234") == "arxiv.org"

    def test_strips_www(self) -> None:
        assert extract_domain("https://www.example.com/page") == "example.com"

    def test_strips_port(self) -> None:
        assert extract_domain("http://localhost:8080/search") == "localhost"

    def test_lowercases(self) -> None:
        assert extract_domain("https://ARXIV.ORG/abs/1") == "arxiv.org"

    def test_bare_domain(self) -> None:
        assert extract_domain("arxiv.org") == "arxiv.org"

    def test_empty_string(self) -> None:
        assert extract_domain("") == ""

    def test_whitespace_trimmed(self) -> None:
        assert extract_domain("  https://example.com/a  ") == "example.com"

    def test_trailing_dot_stripped(self) -> None:
        assert extract_domain("https://example.com./a") == "example.com"

    def test_non_url_returns_empty(self) -> None:
        assert extract_domain("not a url at all") == ""


class TestClassifyAuthority:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.ietf.org/rfc/rfc9110",
            "https://www.w3.org/TR/html52/",
            "https://www.rfc-editor.org/rfc/rfc9110",
            "https://www.nist.gov/publications",
        ],
    )
    def test_primary(self, url: str) -> None:
        assert classify_authority(url) is SourceAuthority.PRIMARY

    @pytest.mark.parametrize(
        "url",
        [
            "https://en.wikipedia.org/wiki/Algebra",
            "https://www.britannica.com/science/algebra",
        ],
    )
    def test_secondary(self, url: str) -> None:
        assert classify_authority(url) is SourceAuthority.SECONDARY

    @pytest.mark.parametrize(
        "url",
        [
            "https://arxiv.org/abs/1234",
            "https://www.nature.com/articles/x",
            "https://link.springer.com/article/1",
        ],
    )
    def test_academic(self, url: str) -> None:
        assert classify_authority(url) is SourceAuthority.ACADEMIC

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.khanacademy.org/math/algebra",
            "https://openstax.org/details/books/algebra",
            "https://www.coursera.org/learn/algebra",
        ],
    )
    def test_educational(self, url: str) -> None:
        assert classify_authority(url) is SourceAuthority.EDUCATIONAL

    def test_textbook(self) -> None:
        assert (
            classify_authority("https://www.pearson.com/en-us/subject-catalog/x")
            is SourceAuthority.TEXTBOOK
        )

    def test_university_subdomain_is_institutional(self) -> None:
        assert classify_authority("https://csail.mit.edu/home") is SourceAuthority.INSTITUTIONAL

    def test_bare_tld_edu_is_institutional(self) -> None:
        assert classify_authority("https://mit.edu") is SourceAuthority.INSTITUTIONAL

    def test_government_is_institutional(self) -> None:
        assert classify_authority("https://www.nasa.gov/planets") is SourceAuthority.INSTITUTIONAL


class TestSpoofingResistance:
    """A lookalike domain must not inherit the tier of a longer domain entry.

    Each case genuinely *ends with* the target domain, which is what makes it an
    attack rather than an unrelated hostname. A domain like
    ``notmit.edu.evil.com`` is NOT a spoofing case for suffix matching, because
    it does not end with ``mit.edu`` at all.

    Scope note: this covers multi-label entries such as ``arxiv.org``. Restricted
    TLDs like ``.edu`` and ``.gov`` behave differently — see
    :class:`TestRestrictedTldCaveat`.
    """

    @pytest.mark.parametrize(
        ("url", "target"),
        [
            ("https://notarxiv.org/abs/1", "arxiv.org"),
            ("https://fakearxiv.org/abs/1", "arxiv.org"),
            ("https://notkhanacademy.org/math", "khanacademy.org"),
            ("https://fakeopenstax.org/books", "openstax.org"),
            ("https://fakenasa.gov.education/x", "nasa.gov.education"),
            ("https://notwikipedia.org/wiki/X", "wikipedia.org"),
            ("https://fakequora.com/x", "quora.com"),
        ],
    )
    def test_lookalike_domains_are_unknown(self, url: str, target: str) -> None:
        host = url.split("//", 1)[1].split("/", 1)[0]
        assert host.endswith(target), "fixture must genuinely end with the target domain"
        assert classify_authority(url) is SourceAuthority.UNKNOWN

    def test_subdomain_of_spoof_is_unknown(self) -> None:
        assert classify_authority("https://deep.notarxiv.org/abs/1") is SourceAuthority.UNKNOWN


class TestRestrictedTldCaveat:
    """Restricted TLDs inherit their tier; this is intended, not a spoofing hole.

    ``.edu`` and ``.gov`` are restricted namespaces — only accredited institutions
    and government bodies can register under them. So ``fakemit.edu`` is
    INSTITUTIONAL because it sits under ``.edu``, not because it resembles
    ``mit.edu``. A domain that merely *resembles* an institution without holding
    the restricted TLD (``notmit.edu.evil.com``) is correctly UNKNOWN.

    Documented explicitly because the distinction is subtle enough to look like a
    bug during review.
    """

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://fakemit.edu/x", SourceAuthority.INSTITUTIONAL),
            ("https://anycollege.edu/x", SourceAuthority.INSTITUTIONAL),
            ("https://notmit.edu.evil.com/x", SourceAuthority.UNKNOWN),
            ("https://mit.edu.evil.com/x", SourceAuthority.UNKNOWN),
        ],
    )
    def test_tld_inheritance_versus_lookalike(self, url: str, expected: SourceAuthority) -> None:
        assert classify_authority(url) is expected


class TestUnknownAndEdgeCases:
    def test_unknown_domain(self) -> None:
        assert classify_authority("https://random-blog.example.org/post") is SourceAuthority.UNKNOWN

    def test_empty_url_is_unknown(self) -> None:
        assert classify_authority("") is SourceAuthority.UNKNOWN

    def test_explicitly_general_domain(self) -> None:
        assert classify_authority("https://www.quora.com/what-is-x") is SourceAuthority.GENERAL

    def test_is_known_domain_true(self) -> None:
        assert is_known_domain("https://arxiv.org/abs/1") is True

    def test_is_known_domain_false(self) -> None:
        assert is_known_domain("https://random.example") is False

    def test_classification_is_deterministic(self) -> None:
        url = "https://arxiv.org/abs/1"
        assert len({classify_authority(url) for _ in range(5)}) == 1


class TestTierPrecedence:
    """When a domain appears in several tiers, the most authoritative wins."""

    def test_academic_beats_educational(self) -> None:
        # arxiv.org is academic; it must not be downgraded to educational.
        assert classify_authority("https://arxiv.org/abs/1") is SourceAuthority.ACADEMIC

    def test_institutional_beats_general(self) -> None:
        assert classify_authority("https://www.nih.gov/study") is SourceAuthority.INSTITUTIONAL


class TestAuthorityRank:
    def test_primary_is_highest(self) -> None:
        assert authority_rank(SourceAuthority.PRIMARY) == 7

    def test_unknown_is_zero(self) -> None:
        assert authority_rank(SourceAuthority.UNKNOWN) == 0

    def test_ranks_are_strictly_ordered(self) -> None:
        order = [
            SourceAuthority.PRIMARY,
            SourceAuthority.INSTITUTIONAL,
            SourceAuthority.ACADEMIC,
            SourceAuthority.EDUCATIONAL,
            SourceAuthority.TEXTBOOK,
            SourceAuthority.SECONDARY,
            SourceAuthority.GENERAL,
            SourceAuthority.UNKNOWN,
        ]
        ranks = [authority_rank(a) for a in order]
        assert ranks == sorted(ranks, reverse=True)
        assert len(set(ranks)) == len(ranks)

    def test_every_tier_has_a_rank(self) -> None:
        for tier in SourceAuthority:
            assert isinstance(authority_rank(tier), int)
