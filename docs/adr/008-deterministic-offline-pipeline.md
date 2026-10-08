# ADR-008: Deterministic Offline Pipeline

**Status:** Accepted
**Date:** 2026-10-03

## Context

Until now the project had a complete *domain*, a complete *research engine*, and
a `lpf generate` command that printed `Not yet implemented`. The pieces had never
run together. Every module was tested in isolation, so no test could catch a
disagreement *between* stages.

The gap matters for a specific reason: this project's core claim is that a
product is **reproducible**. The model is never the verification authority;
ranking, dedupe, confidence, and quality verdicts are deterministic. That claim
is only meaningful if you can run the whole factory twice and diff the bytes. A
per-module test suite cannot demonstrate that.

This ADR describes the offline pipeline that closes the gap, and the three real
integration defects it immediately found.

## Decisions

### 1. One module per stage, driven by a linear state machine

Each stage is its own module (`discovery_stage`, `specification` inside it,
`research_stage`, `syllabus_stage`, `content_stage`, `assessment_stage`,
`qa_stage`, `packaging_stage`) and the orchestrator (`pipeline.py`) moves the run
through `RunState`.

The machine is deliberately linear: `created → discovery → specification →
research → syllabus → content → assessment → qa → packaging → complete`, with
`failed` reachable from every non-terminal stage. A linear machine makes two bugs
impossible by construction — running a stage before its inputs exist, and
silently skipping a stage. Branching, retry, and repair loops are out of scope
for this version (the Revision crew will need them; see Known Limitations).

> **Superseded in part by [ADR-010](010-bounded-qa-revision-loop.md).** QA now
> holds two backward edges — `qa → content` and `qa → assessment` — declared in
> `REVISION_TARGETS`. The forward-only property for every other stage, and both
> impossibility arguments above, still hold.

Illegal transitions raise `WorkflowError(code="ILLEGAL_TRANSITION")`. They are a
programming error, not an input error, so they must surface loudly.

### 2. Determinism is centralised in a `RunContext`

Artifacts default to `uuid4` ids and `datetime.now()`. Used directly, either
makes a run irreproducible. Every stage therefore builds artifacts through
`RunContext`:

- `id(kind)` returns `<run_id>-<kind>-<n>`, numbered **per kind** and monotonic.
  Per-kind counters matter: if ids shared one counter, adding an artifact of one
  kind would renumber every later artifact of another kind, and the run would
  stop being stable under unrelated changes.
- `now()` returns a fixed epoch (`2026-01-01T00:00:00Z`) advanced one second per
  call. Monotonic, so `created_at` ordering matches build order.

The alternative — seeding a global RNG — was rejected because timestamps still
come from the wall clock; you cannot seed `datetime.now()`.

### 3. The event log is the run's audit trail

`EventLog` records `run_started`, a `stage_started`/`stage_completed` pair per
stage, and `run_completed`/`run_failed`, each with a monotonic sequence number.
It is written next to the artifacts as `run_log.json`, so a finished product can
be traced back to the steps that made it.

### 4. The model is isolated behind `ModelProvider`

`DeterministicMockModel` implements the same `ModelProvider` Protocol the live
providers do. It returns prompt-derived text and ignores `temperature` and
`max_tokens`. It is used in exactly one place — lesson prose — because that is
the only place a model is genuinely required. Every decision that has to be
*right* is made by deterministic code.

Mock prose is a mock artifact. Its sentences are canned, so the conflict
detector finds eight "conflicts" that all share bucket words with differing
polarity. This is noise, not signal, and is documented rather than papered over.

### 5. The research stage runs the *real* `ResearchPipeline`

Only the search provider is swapped for an offline one. The offline run therefore
exercises the genuine dedupe, filter, rank, claim, conflict, and evidence-map
logic (ADR-006/007) end to end, instead of a mock that would prove nothing.

### 6. Nondeterministic values are fixed at the source, not normalised away

This is the most important decision, and it changed production code.

The first end-to-end determinism run differed on three artifacts
(`research_report`, `evidence_map`, `verification_result`). Two causes, both real
defects in production code, not merely in the new orchestration layer:

1. `ResearchPipeline._build_claims` called `claim_id=new_id()` — a fresh `uuid4`
   per claim. `run_id` was accepted by `run()` and then ignored.
2. `QualityGate.checked_at` defaulted to `datetime.now()`.

The temptation was to rewrite these fields in the orchestration layer after the
fact. That was rejected: patching a value after it is produced hides the defect
from every other caller and leaves a pipeline that cannot be reproduced on its
own.

Instead:

- `ResearchPipeline.run(run_id=...)` now uses the run id it already received:
  `<run_id>-claim-0001`, `<run_id>-research_report-0001`,
  `<run_id>-evidence_map-0001`. Without a run id, ids remain `uuid4`, so existing
  callers are unaffected.
- Every `QualityGate` is constructed with `checked_at=ctx.now()`.

A later diff still showed one gate differing. The cause was indentation: gate
constructions sit at three indentation levels, and a `replaceAll` had fixed two
of them. `research_evidence` kept the wall clock. This is exactly the kind of bug
the byte-diff catches and a per-field unit test does not.

### 7. QA gates delegate to the existing validators

`qa_stage` runs the real `check_*` validators (`check_objective_references`,
`check_misconception_objective_refs`, `check_question_references`,
`check_assessment_references`, `check_answer_references`,
`check_answer_key_references`) plus explicit coverage and evidence gates. QA
cannot pass by re-testing what construction already guaranteed.

`overall_status` is `failed > warning > passed`. A `failed` verdict aborts the
run before packaging: a run that chose failure and a run that wrote a manifest
must not be the same run. A run with no supported claims is a `warning`, not a
failure — a mock product with thin evidence is still a product.

### 8. Packaging persists the terminal snapshot

Packaging was initially placed *before* `state.advance(COMPLETE)`. The manifest
then recorded the run as still `packaging`, and `run_log.json` omitted the final
`run_completed` event. The manifest test caught it on the first run.

Packaging now runs after the run reaches `COMPLETE` and after the final event is
emitted, so the persisted snapshot agrees with the state it describes.

### 9. Expected failures are values; unexpected ones propagate

`LpfError` (and subclasses) mark the run `FAILED` and return a `FactoryRunResult`
with `succeeded == False`, no package, and whatever artifacts were produced
before the failure. Any other exception propagates untouched. A real bug must
never be flattened into a "failed product".

## Consequences

- `lpf generate --mock` now runs the full pipeline and writes
  `manifest.json`, `run_log.json`, `product.md`, and one JSON file per artifact
  under `projects/<run_id>/`.
- Two runs with the same inputs produce **byte-identical** output trees. This is
  asserted directly in `tests/test_e2e_pipeline.py`.
- The production research pipeline gained a real capability it was pretending to
  have (reproducible ids under a run id).

### Verification evidence

| Injected defect | Expected | Observed |
| --- | --- | --- |
| `claim_id=new_id()` in `_build_claims` | report/map differ across runs | E2E determinism test fails on 3 artifacts |
| `QualityGate.checked_at` left at `now()` | verification differs | E2E determinism test fails on `verification_result` |
| Packaging before `COMPLETE` | manifest stage `packaging`, no `run_completed` | manifest + run-log tests fail |
| QA `failed` no longer aborts | failed run still packages | QA-failure test fails |
| `LpfError` allowed to propagate | run value not returned | domain-failure test fails |

## Known Limitations

- **The machine was linear.** There is no retry and no repair loop. The Revision
  crew will require cycles; when it lands, the transition table grows edges and
  this ADR is superseded for that part. *Landed as [ADR-010](010-bounded-qa-revision-loop.md):
  QA may now rewind to content or assessment, bounded by `MAX_REVISIONS`.*
- **Mock content is canned.** Lesson prose is prompt-derived placeholder text.
  It proves the wiring, not the pedagogy.
- **Mock conflicts are noise.** Eight spurious conflicts come from shared bucket
  words in canned text.
- **Only the mock provider is wired.** Live providers are not selected by the
  pipeline yet.

## Alternatives Rejected

- **Seed an RNG for ids.** Does not make `datetime.now()` reproducible.
- **Normalise nondeterministic fields in the orchestration layer.** Hides real
  defects in `ResearchPipeline` from every other caller and leaves it
  irreproducible on its own.
- **Skip the pipeline and keep the stub until live providers exist.** No
  integration defects would have been found, and the determinism claim would
  remain unproven.
- **Use a branching graph now.** Speculative for a linear mock pipeline; adds a
  state-graph dependency before any stage needs to loop.
