"""Authority classification — deterministic domain → SourceAuthority mapping.

Source authority drives evidence ranking, so it must not be guessed. Every
provider that returns a raw URL routes it through :func:`classify_authority`
rather than deciding for itself, which keeps a preprint from outranking a
textbook because the preprint happened to score higher on relevance.
"""

from __future__ import annotations

from urllib.parse import urlparse

from lpf.schemas.research import SourceAuthority

# ---------------------------------------------------------------------------
# Domain tiers, most authoritative first.
#
# Matching is suffix-based: "mit.edu" and "csail.mit.edu" both resolve to
# INSTITUTIONAL via the ".mit.edu" entry, so entries are written with a leading
# dot to prevent "notmit.edu" from matching "mit.edu".
# ---------------------------------------------------------------------------

_PRIMARY_DOMAINS: frozenset[str] = frozenset(
    {
        # Standards bodies and specifications
        ".ietf.org",
        ".w3.org",
        ".iso.org",
        ".ieee.org",
        ".acm.org",
        ".ansi.org",
        ".nist.gov",
        ".oasis-open.org",
        ".rfc-editor.org",
    }
)

_INSTITUTIONAL_DOMAINS: frozenset[str] = frozenset(
    {
        # Universities and research institutions
        ".edu",
        ".ac.uk",
        ".ac.jp",
        ".edu.au",
        ".edu.cn",
        ".ac.in",
        ".ac.za",
        ".mit.edu",
        ".stanford.edu",
        ".harvard.edu",
        ".ox.ac.uk",
        ".cam.ac.uk",
        ".ethz.ch",
        ".epfl.ch",
        ".tudelft.nl",
        ".kth.se",
        ".tu-delft.nl",
        # Government and intergovernmental
        ".gov",
        ".gov.uk",
        ".gov.au",
        ".europa.eu",
        ".un.org",
        ".who.int",
        ".unesco.org",
        ".oecd.org",
        ".worldbank.org",
        ".nasa.gov",
        ".nih.gov",
        ".cdc.gov",
        ".noaa.gov",
        ".cmu.edu",
        # Museums and national bodies
        ".si.edu",
        ".britishmuseum.org",
        ".louvre.fr",
    }
)

_ACADEMIC_DOMAINS: frozenset[str] = frozenset(
    {
        # Preprint servers and academic publishers
        ".arxiv.org",
        ".biorxiv.org",
        ".medrxiv.org",
        ".ssrn.com",
        ".researchgate.net",
        ".semanticscholar.org",
        ".pubmed.ncbi.nlm.nih.gov",
        ".springer.com",
        ".sciencedirect.com",
        ".jstor.org",
        ".tandfonline.com",
        ".nature.com",
        ".science.org",
        ".plos.org",
        ".mdpi.com",
        ".frontiersin.org",
        ".ncbi.nlm.nih.gov",
        ".doi.org",
    }
)

_EDUCATIONAL_DOMAINS: frozenset[str] = frozenset(
    {
        # Learning platforms, museums, and open courseware
        ".khanacademy.org",
        ".coursera.org",
        ".edx.org",
        ".udemy.com",
        ".mit.edu.ocw",
        ".open.edu",
        ".openstax.org",
        ".ck12.org",
        ".oercommons.org",
        ".saylor.org",
        ".merlot.org",
        ".scholarpedia.org",
        ".explorable.com",
        ".ted.com",
        ".si.edu.learn",
        ".nasa.gov.education",
        ".ncb.edu",
    }
)

_TEXTBOOK_DOMAINS: frozenset[str] = frozenset(
    {
        ".pearson.com",
        ".pearson.co.uk",
        ".cambridge.org",
        ".oup.com",
        ".macmillan.com",
        ".mcgrawhill.com",
        ".cengage.com",
        ".schaum.com",
        ".oreilly.com",
        ".packtpub.com",
        ".informit.com",
    }
)

_SECONDARY_DOMAINS: frozenset[str] = frozenset(
    {
        # Encyclopedias and reference works
        ".wikipedia.org",
        ".wikibooks.org",
        ".wikidata.org",
        ".britannica.com",
        ".encyclopedia.com",
    }
)

# Domains explicitly classified as low-value. Ranked as GENERAL rather than
# UNKNOWN so the pipeline can distinguish "we checked and judged it general"
# from "we have never heard of this domain".
_GENERAL_DOMAINS: frozenset[str] = frozenset(
    {
        ".quora.com",
        ".reddit.com",
        ".medium.com",
        ".substack.com",
        ".blogspot.com",
        ".wordpress.com",
        ".pinterest.com",
        ".tiktok.com",
        ".facebook.com",
        ".instagram.com",
        ".linkedin.com",
        ".x.com",
        ".twitter.com",
    }
)

# Ordered most-authoritative-first: the first tier that matches wins.
_TIERS: tuple[tuple[SourceAuthority, frozenset[str]], ...] = (
    (SourceAuthority.PRIMARY, _PRIMARY_DOMAINS),
    (SourceAuthority.INSTITUTIONAL, _INSTITUTIONAL_DOMAINS),
    (SourceAuthority.ACADEMIC, _ACADEMIC_DOMAINS),
    (SourceAuthority.EDUCATIONAL, _EDUCATIONAL_DOMAINS),
    (SourceAuthority.TEXTBOOK, _TEXTBOOK_DOMAINS),
    (SourceAuthority.SECONDARY, _SECONDARY_DOMAINS),
    (SourceAuthority.GENERAL, _GENERAL_DOMAINS),
)


def extract_domain(url: str) -> str:
    """Return the lowercase host of a URL, without a leading ``www.``.

    Returns an empty string when the input has no parseable host, so callers can
    treat a malformed URL as unclassifiable rather than crashing. Whitespace is
    rejected explicitly: ``urlsplit`` happily parses ``//not a url`` as a netloc,
    which would otherwise classify arbitrary prose as a domain.
    """
    if not url:
        return ""

    candidate = url.strip()
    if not candidate or any(ch.isspace() for ch in candidate):
        return ""

    if "//" not in candidate:
        candidate = f"//{candidate}"

    try:
        host = urlparse(candidate).hostname or ""
    except ValueError:
        return ""

    host = host.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def _matches(host: str, domains: frozenset[str]) -> bool:
    """Suffix match a host against a domain set.

    Exact equality is allowed too, so a bare "arxiv.org" entry matches even if
    written without a leading dot.
    """
    for domain in domains:
        if host == domain.lstrip("."):
            return True
        if host.endswith(domain):
            return True
    return False


def classify_authority(url_or_domain: str) -> SourceAuthority:
    """Classify a URL or bare domain into a SourceAuthority tier.

    Unrecognised domains fall back to UNKNOWN rather than GUESSING a tier. A
    caller that wants a default should apply it explicitly, so that "unknown"
    stays visible in the evidence map instead of being silently inflated.
    """
    host = extract_domain(url_or_domain)
    if not host:
        return SourceAuthority.UNKNOWN

    for authority, domains in _TIERS:
        if _matches(host, domains):
            return authority

    return SourceAuthority.UNKNOWN


def is_known_domain(url_or_domain: str) -> bool:
    """Whether the classifier recognises this domain at any tier."""
    return classify_authority(url_or_domain) is not SourceAuthority.UNKNOWN


def authority_rank(authority: SourceAuthority) -> int:
    """Numeric rank for an authority tier, highest tier = 7.

    Used for ordering and for the weighted relevance score in
    :mod:`lpf.research.pipeline`.
    """
    return {
        SourceAuthority.PRIMARY: 7,
        SourceAuthority.INSTITUTIONAL: 6,
        SourceAuthority.ACADEMIC: 5,
        SourceAuthority.EDUCATIONAL: 4,
        SourceAuthority.TEXTBOOK: 3,
        SourceAuthority.SECONDARY: 2,
        SourceAuthority.GENERAL: 1,
        SourceAuthority.UNKNOWN: 0,
    }[authority]
