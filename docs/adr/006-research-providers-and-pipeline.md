# ADR-006: Research Providers, Authority Classification, and the Deterministic Pipeline

**Status:** Accepted
**Date:** 2026-10-02

## Context

Phase 1 built the research *schemas* and a mock provider. This phase makes research real: four live provider adapters, plus the deterministic stage that turns raw provider responses into citable evidence.

Two properties constrain every decision here, both inherited from the North Star Architecture:

- **The model is never the verification authority.** Source authority, deduplication, ranking, and filtering must be reproducible without a model.
- **A source that cannot be classified must stay visibly unclassified.** Silently defaulting an unknown domain to a mid tier inflates weak evidence into looking citable.

## Decisions

### 1. Authority classification is deterministic and lives in one place

`research/authority.py` maps a URL to a `SourceAuthority` via ordered domain tiers. Every provider routes its results through it, so a preprint found by SearXNG and the same preprint found by Tavily receive the same authority.

This is the core of the design. When each provider classified for itself, authority would vary with which provider happened to win a race — and evidence ranking would become non-reproducible.

**Unknown domains return `UNKNOWN`, not a default tier.** A caller that wants a default must apply it explicitly, so "we checked and could not classify this" stays distinguishable from "we classified this as general" in the evidence map.

### 2. Domain entries use a leading dot to resist spoofing

Entries are written `".mit.edu"`, not `"mit.edu"`. Without the dot, `notmit.edu.evil.com` ends with `mit.edu` and would inherit `INSTITUTIONAL`.

Exact equality is *also* accepted, so a bare `arxiv.org` entry still matches. Five spoofing cases are pinned in tests — a lookalike domain must never inherit the tier of the domain it mimics.

### 3. `extract_domain` rejects whitespace

`urlsplit` happily parses `//not a url` as a netloc, so a prose string would otherwise classify as a domain. Whitespace is rejected before parsing. This was a real bug caught by tests, not a hypothetical.

### 4. One HTTP transport owns retry and rate limiting

`research/transport.py` centralises policy:

- **4xx other than 429 is never retried.** A 404 or 401 will not become a 200; retrying only burns the provider's rate limit.
- **429/5xx are retried** with exponential backoff, capped.
- **Backoff has no jitter.** Jitter would make provider behaviour non-reproducible under test.
- **`RateLimiter` serialises call starts** so N concurrent tasks cannot burst past a published limit.

Per-provider intervals: arXiv 3.0s (it is strict), Tavily 1.0s, Wikimedia 0.5s, SearXNG 0.2s.

### 5. Provider degradation is silent, not fatal

Malformed XML from arXiv, a missing `results` key from SearXNG, an unexpected payload type from Tavily — all yield an empty result list rather than raising. One broken feed must not abort research that already has other sources.

The exception is a *payload shape* mismatch (`TransportError`), which is a contract break rather than bad content and should surface.

### 6. Tavily scores are coerced, not trusted

Tavily returns a `score` that may be absent or non-numeric. `_score` maps missing and malformed values to `0.0` rather than a mid-range default, so an unscored result cannot outrank a scored one.

### 7. One claim per source, never a merged claim

`_build_claims` promotes each retained source into exactly one `EvidenceClaim`. A claim spanning several sources would merge statements that may not agree, and the conflict detector operates on claim granularity — a merged claim cannot be flagged against the source it disagrees with.

### 8. Deduplication keeps the higher-authority copy

When two providers return the same page under URL variants, the copy with the better authority/relevance score survives. The retained result is the one worth citing.

`canonical_url` strips fragments, lowercases scheme and host, drops `www.`, and removes trailing slashes — but **preserves query strings**, because for some providers the query is the identifier rather than a filter.

### 9. Conflict detection is deliberately conservative

A conflict requires **both** substantial lexical overlap (≥50% of the smaller token set) **and** differing polarity. Low overlap means unrelated text, not disagreement.

Polarity is coarse: negation tokens minus affirmation tokens. Two factual statements containing neither resolve to `neutral` and are treated as *agreeing*.

This asymmetry is deliberate. A false conflict sends the Revision crew chasing a disagreement that does not exist, which is far more expensive than missing a real one that a later gate would likely catch.

### 10. The pipeline reports what it dropped

`PipelineResult` carries `duplicates_removed`, `dropped_low_authority`, and `dropped_thin` alongside the report. Silent filtering hides the fact that a question was answered from three weak sources.

### 11. Relevance is derived when a provider reports none

Only Tavily returns a backend relevance score. arXiv, Wikimedia and SearXNG return ranked-but-unscored results, leaving `relevance_score` at its schema default of `0.0`.

That zero flowed directly into claim confidence (`authority × 0.4 + relevance × 0.6`), capping an ACADEMIC source at **0.2857 — permanently below the 0.7 support threshold**. A live pipeline run produced `EvidenceMap: 0/20 supported`: every real claim unsupported. No mocked test caught this, because the fixtures set relevance explicitly.

`research/relevance.py` supplies a deterministic query-coverage score for those providers: token overlap with title matches weighted double, crude plural folding (`seasons` → `season`), and a small stopword list. A provider score above zero is always trusted; `0.0` means "unknown" and triggers derivation.

Still no model involved, still reproducible. After the fix the same query yields `17/20 supported`.

**Lesson recorded deliberately:** an assertion that only *passes* proves little. Every fix here was re-checked by mutating the source and confirming named tests fail. That process caught both a fake test and an untested wiring path.

### 12. Providers must satisfy Wikimedia's robot policy

Wikimedia rejects requests whose User-Agent carries no contactable URL or email, answering `403 Please respect our robot policy`. A User-Agent ending in the prose "contact via repo" is refused; one containing a URL is accepted. Verified live across five User-Agent variants.

Because provider degradation is quiet (§5), this would have surfaced as "Wikipedia never returns results" — nearly undiagnosable. `LPF_RESEARCH_CONTACT` overrides the contact; the default is a placeholder that must be replaced before real deployment.

## Consequences

- Evidence ranking is reproducible: same provider responses in, same ranking out. Two tests pin this.
- A run that produced almost nothing is visible in the result rather than looking like a clean run with no findings.
- The conflict detector will under-report real disagreements that share little vocabulary. Accepted trade-off; noted here so it is not mistaken for a bug.
- arXiv results are `ACADEMIC` by construction when an entry lacks a URL — the tier is a property of the provider, not of the (absent) URL.

## Alternatives Rejected

**Let each provider set authority inline.** Rejected — authority would depend on which provider won a race, making ranking non-reproducible.

**Use an LLM to judge source credibility.** Rejected — directly violates the rule that the model is never the verification authority, and would put a per-call cost and latency on the hot path.

**Merge multiple sources into one claim.** Rejected — destroys claim-level conflict detection and traceability.

**Retry all 4xx.** Rejected — wastes rate limit on requests that cannot succeed.

**Add jitter to backoff.** Rejected — makes tests non-deterministic and buys nothing for a single-instance factory. Revisit if throughput becomes a concern.

**Trust provider-supplied relevance exclusively.** Rejected — three of four providers report nothing at all, so trust-with-no-fallback silently zeroes the entire evidence map. See §11.

## Verified Against Live Services

Mocked tests cannot confirm that a provider's real response matches the shape assumed in the parser. Each free provider was therefore exercised live.

| Provider | Result |
|---|---|
| arXiv | **Working.** Real Atom feed parsed, URLs and summaries correct, `ACADEMIC` tier as designed. |
| Wikimedia | **Broken, now fixed.** 403 robot-policy rejection from a non-contactable User-Agent. |
| SearXNG | **Not verifiable publicly.** Public instances disable the JSON API (`searx.be` returned HTML), rate-limit aggressively (`priv.au` 429), or block scripted clients. Self-hosting is the intended deployment; the `localhost:8080` default is correct. |
| Tavily | **Not verifiable.** Requires a paid API key; no key available. Contract remains mock-tested only. |

The full pipeline was then run end-to-end against arXiv plus Wikimedia with no mocks: 20 real sources collected, deduplicated, filtered, ranked, and turned into `17/20` supported claims with working provenance URLs.