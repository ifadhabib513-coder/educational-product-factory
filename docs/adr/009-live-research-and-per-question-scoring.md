# ADR-009: Live Research Providers and Per-Question Scoring

**Status:** Accepted
**Date:** 2026-10-03

## Context

ADR-008 made the pipeline reproducible but it was still entirely offline: the
research stage hardcoded `SearchProvider.MOCK` and `DeterministicSearchProvider`,
so the product's evidence was invented. Every downstream artifact — lessons,
misconceptions, the evidence map — was as good as canned text.

Two things had to change to make the research stage real:

1. There was **no seam**. `build_research` constructed its own provider, so live
   providers could not be substituted without editing the stage.
2. Real data then exposed a **scoring defect** that no unit test could have
   found, because every test used a single question.

The defect: the pipeline scored every source against **all the questions in the
run joined into one string**. A Wikipedia article retrieved for *"What is linear
algebra?"* was judged against a concatenation that also contained *"What common
mistakes do learners make…"*. Lexical coverage was diluted by questions that
source had nothing to do with.

Live effect, arXiv + Wikimedia, 52 sources:

- The correct Wikipedia article on linear algebra scored **0.746**, not 1.0.
- Only **2 of 52** claims cleared the 0.7 support threshold.
- Every `VerifiedSource.relevant` flag was `False` (0/52).
- Off-topic noise (*Sanskrit*, *Euclid's Elements*) passed the same authority
  floor as real sources.

Scored in isolation against its own question, that same article scores **1.0**
and *Sanskrit* scores **0.0**.

## Decisions

### 1. Providers are injected; the stage has one code path

`build_research(..., providers=None)` takes a mapping of
`SearchProvider -> SearchProviderProto`. With no argument it uses
`default_providers(ctx)`, the deterministic offline provider.

This is why the pipeline needed no second code path for live data: the same plan
builder, the same `ResearchPipeline`, the same ranking. Hardcoding a provider
back into the stage is caught by
`tests/test_research_provider_injection.py` — reverting the injection fails four
tests.

The default stays offline so `lpf generate` remains reproducible and the test
suite never touches the network.

### 2. `--live-research` is opt-in, and composes with the mock model

Real sources and mock prose are a legitimate pairing: `lpf generate --live-research`
produces a product whose *evidence* is real while its *prose* is still generated.
That is strictly better than the previous state, and it is honest about which
half is real.

### 3. Intent stays run-level; lexical relevance and confidence are per-question

This is the substantive fix, and it deliberately splits two things that ADR-006
had conflated into a single `_query` string:

- **Intent remains one per run.** ADR-007 decided this so ranking cannot depend
  on which question happened to be processed first. That reasoning still holds
  and is preserved unchanged.
- **Relevance and confidence are per-result.** A source is compared against the
  question it was actually retrieved for. This is not just more accurate — it is
  the only correct semantics, because a source answering question 1 has no
  relationship to question 3.

Implementation: `_derive_relevance` takes a single query string instead of the
question list, and `_query_for(result)` resolves a result's own question through
a `source_id -> question text` map built during collection. `_query` is retained
only as a fallback for results with no recorded provenance.

Live result, same 52 sources:

| metric | before | after |
| --- | --- | --- |
| correct article's confidence | 0.746 | **1.000** |
| claims above the 0.7 threshold | 2 / 52 | **4 / 52** |
| `VerifiedSource.relevant` | 0 / 52 | **17 / 52** |
| off-topic noise (*Gravitational-Wave Transient Catalog*, *what-if analysis*) | ~0.5 | 0.225 |

The remaining 4/52 is *correct behaviour*, not a defect — see Known Limitations.

## Consequences

- `lpf generate --live-research` retrieves real sources and the evidence map is
  built from them. 681 tests, still fully offline.
- One genuine correctness bug in production ranking was fixed and locked by
  three tests.

### Verification evidence

| Injected defect | Observed |
| --- | --- |
| `providers` argument ignored, offline provider forced | 4 tests fail |
| `_query_for` returns the joined query (ranking/confidence half) | 2 tests fail |
| `_derive_relevance` given the joined query (relevance half) | 3 tests fail |
| `lpf generate` default path changed to live providers | `test_pipeline_without_providers_stays_offline` fails |

The two mutations of the scoring fix are tracked separately because the fix has
two independent halves; each test class member guards a different one.

## Known Limitations

- **Provider selection is not intent-aware.** Every question is sent to every
  injected provider. For *"What is linear algebra?"* aimed at a year-10 learner,
  30 of 52 results were arXiv preprints, which under a DEFINITIONAL intent score
  an authority fit of ~0.30 and therefore *cannot* clear 0.7 — by design
  (ADR-007). They are correctly unsupported, but retrieving them was wasted
  effort. Routing questions to providers by intent is the clear next step.
- **Live runs are not byte-reproducible.** They depend on network responses. The
  reproducibility guarantee holds for identical provider responses — the same
  property ADR-006 already claims for ranking — and TASK-013 tightened that:
  `source_id` is now a seeded function of `(provider, url)` (no hidden uuid),
  and the stage normalises ids/timestamps, so *identical* responses produce
  *byte-identical* output. The remaining variance is the response content itself.
- **Tavily remains unverified** (no API key) and **SearXNG requires self-hosting**.
- **arXiv search is loose.** Plain keyword queries return tangential preprints;
  a field/category restriction is not yet applied.
- **Lesson prose is still mock.** This phase made the *evidence* real, not the
  writing.

## Alternatives Rejected

- **Edit the stage to hardcode live providers.** No seam, so no offline default
  and no network-free test suite.
- **Fix the diluted query in the orchestration layer only.** The defect is in
  production `ResearchPipeline`; patching it downstream would leave every other
  caller broken.
- **Score intent per result instead of per run.** Would make ranking depend on
  question order, undoing ADR-007.
- **Raise or lower the 0.7 support threshold to improve the supported count.**
  The threshold is comparable across intents precisely because it is not tuned.
  The supported count is low for a real reason — see provider routing.
