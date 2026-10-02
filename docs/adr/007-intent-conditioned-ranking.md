# ADR-007: Intent-Conditioned Ranking and Audience Fit

**Status:** Accepted
**Date:** 2026-10-03

## Context

The authority-first ranking formula in ADR-006 produced the wrong answer for a
central educational query. Live testing of `"What is linear algebra?"` ranked
`Non-linear positive maps between C*-algebras` (an arXiv preprint) above the
Wikipedia article on linear algebra.

The cause was not retrieval. Both sources scored **1.0** on lexical relevance.
Authority merely broke the tie, and authority rank is the wrong criterion for an
introductory question.

A second problem sits underneath: the naive fix of lowering authority's weight
globally. `"Find papers about linear algebra"` wants the *opposite* source mix.
One global weight dial cannot serve both, so the intent of the query has to
enter the scoring function itself.

## Decisions

### 1. Authority becomes a fit, not a rank

`authority_fit(intent, tier)` asks "is this tier appropriate *for this intent*"
rather than "is this tier high". An encyclopedia is `1.00` for DEFINITIONAL and
`0.30` for ACADEMIC_LITERATURE; a preprint is the mirror image.

This is the change that makes the rest work. Flat rank cannot express "the right
source depends on the question", and any attempt to approximate it with weights
either buries encyclopedias or floods literature reviews with blogs.

### 2. IntentMatch blends coverage with a cue, because coverage saturates

Token overlap rated both candidate sources `1.0`, so it could not separate
*defining* a topic from *mentioning* it. `intent_match` therefore combines
lexical coverage with a **definition-cue** signal (`is the branch of`, `refers
to`, `is defined as`).

Combined by weighted average (`0.6 × coverage + 0.4 × cue`), **not** by adding a
bonus. The additive version was implemented first and failed: a source already
covering every query term scores `1.0`, so `min(1.0, coverage + bonus)` leaves
it at `1.0` and the cue can do nothing. Both sources tied at exactly `1.0`.

A cue cannot rescue an off-topic source either — zero coverage short-circuits to
zero before the cue is consulted.

### 3. Ranking score and confidence are different numbers

`ranking_score` is intent-conditional: it answers *"which should the learner read
first"*, a preference ordering whose absolute value means little.

`confidence` is deliberately **independent of the ranking weights**, and answers
*"does this source support the claim"*. It uses `0.5 × intent_match + 0.5 ×
authority_fit`.

Collapsing them would have re-created the permanently-empty EvidenceMap bug from
ADR-006: an academic-only profile scores an on-topic encyclopedia article below
the support threshold purely because its tier is SECONDARY. The threshold has to
mean the same thing every run.

`TestEvidenceMapSurvivesEveryIntent` pins this for all seven intents, because the
failure is silent — the pipeline reports success with no supported claims.

### 4. The evidence bar shifts with intent, and that is correct

A Wikipedia article scores `1.00` confidence for DEFINITIONAL and `0.65` for
ACADEMIC_LITERATURE. The second number is *supposed* to fall below the `0.7`
threshold: an encyclopedia is not adequate evidence for "find papers about X",
and letting it pass would be a false positive.

The invariant is therefore "each intent has an appropriate source that is
supported", **not** "every source is supported under every intent". Getting this
backwards is how a tuning pass quietly destroys evidence quality.

### 5. Audience is threaded from Discovery, not inferred

`classify_audience` normalises `LearnerProfile.level` (free text like "Year 2")
onto a closed set. Discovery already determines who the learner is, so
re-inferring it per question would be less accurate and harder to test.

Unknown levels default to `INTERMEDIATE`. Defaulting to `BEGINNER` would flood an
advanced learner with introductory material — the more damaging error.

### 6. Freshness is corpus-relative, not wall-clock

Freshness scores against the newest source *in the same run*, so identical
provider responses always produce identical scores. Using `now()` would break the
reproducibility guarantee that the rest of the pipeline depends on.

An undated source scores a neutral `0.5`. `published_at` is populated by arXiv
and Tavily only, so treating a missing date as fresh would silently reward
whichever providers happen to omit it. Plumbing dates into Wikipedia and SearXNG
is future work.

`freshness(result, oldest, newest)` takes its arguments in `date_span`'s return
order. It originally took them newest-first, and the mismatch immediately
produced a wrong-ordering test — kept as a note because it is an easy trap.

### 7. Clarity and density are proxies, and labelled as such

Both are crude deterministic measures: average sentence length against a soft
target, and a count of LaTeX/notation markers. They measure what text *looks*
like, not how well it teaches.

The markers are deliberately subject-agnostic — LaTeX and standard notation
rather than any field's jargon — so the same weights work for a biology or
history query. Pinned by a test asserting plain prose in other subjects scores
zero density.

## Consequences

- `"What is linear algebra?"` now surfaces encyclopedia sources; `"Find papers
  about linear algebra"` surfaces preprints. Verified live, both directions.
- Ranking is still reproducible: intent classification and every component are
  deterministic and model-free.
- Rule-based intent classification will misread unusual phrasings. A model could
  replace `classify_intent` without changing anything downstream; the interface
  was kept narrow for that reason.
- A source can be confidently *unsupported* evidence, by design (§4). Reports
  need to present confidence relative to intent, not in isolation.

## Alternatives Rejected

**Lower the global authority weight.** Rejected — fixes beginner queries by
breaking literature queries. This was the rejected alternative from the original
proposal, for good reason.

**Add a model-based intent classifier.** Rejected for now — it would make ranking
irreproducible and the tests meaningless. Cheap to swap in later.

**Reuse `relevance_score` as IntentMatch.** Rejected — it is the lexical signal
that already failed to separate the two candidate sources.

**Let the weight profile influence confidence.** Rejected — that is precisely
what makes the EvidenceMap threshold drift per intent (§3).

**Score freshness against the current date.** Rejected — reintroduces
wall-clock dependence into a stage that is otherwise reproducible.

## Verification

Every fix was re-checked by mutating the source and confirming named tests fail,
the practice established in ADR-006.

| Mutation | Result |
|---|---|
| `authority_fit` ignores intent (flat table) | 3 failures |
| Definition cue forced on | 4 failures |
| DEFINITIONAL profile made authority-dominated | 1 failure |
| `authority_fit` reverted to pre-tuning flat rank | **9 failures, 3 of them in the benchmark** |

## Known Limitations

- **A narrow page whose title is the exact query term can outrank the canonical
  definitional article.** Live: `Basic Linear Algebra Subprograms` outranked
  `Linear algebra`. An exact-title phrase signal would fix this; not implemented.
- Density detection keys on notation, so a specialist paper with plain prose and
  a non-specialist text with heavy LaTeX are both mis-scored.
- Rule-based intent classification does not handle multi-intent questions, e.g.
  "What is X and where did the research on it stand in 2026?"