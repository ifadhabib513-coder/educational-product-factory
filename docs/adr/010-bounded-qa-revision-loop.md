# ADR-010: Bounded QA Revision Loop

**Status:** Accepted
**Date:** 2026-10-08

## Context

ADR-008 made the stage machine strictly linear, and deliberately so: a run
could only move forward or fail, which made "run a stage before its inputs
exist" and "silently skip a stage" impossible. Its own Known Limitations
predicted that a repair loop would eventually be required.

That arrived as TASK-003 and TASK-004 landed QA gates that can genuinely fail:
`factual_consistency` and `numerical_consistency` read content artifacts, and a
failed gate previously meant the run died with no way to act on the finding.
"QA said the worked example is wrong" is only useful if the factory can go back
and fix the worked example.

Two failure modes had to be avoided:

1. **An infinite loop.** The offline pipeline is deterministic, so a defect that
   fails on the first pass fails on every pass. Unbounded retry would hang the
   run instead of reporting the defect.
2. **A plausible-looking wrong product.** Re-running a stage whose output was
   never the problem ships stale upstream inputs under a fresh timestamp.

## Decisions

### 1. QA owns exactly two backward edges

`LEGAL_TRANSITIONS[QA]` gains `CONTENT` and `ASSESSMENT`. Nothing else changes:
every other stage still has one successor plus `failed`, and the two revision
edges are declared in one place, `REVISION_TARGETS`, so the whole backward
surface of the machine is readable at a glance.

`qa → syllabus`, `qa → research`, and `qa → specification` were rejected. Those
stages sit behind inputs the revision cycle is not allowed to touch, and opening
them would turn "bounded repair" into "re-run the factory".

### 2. Gate ownership decides where a run rewinds

`lpf.orchestration.revision.route_failed_gates` maps a set of failed gates to a
stage, using an explicit ownership table (`OWNED_GATES`) rather than a guess:

- content-owned: `misconception_references`, `numerical_consistency`;
- assessment-owned: `question_references`, `assessment_references`,
  `answer_references`, `answer_key_references`;
- unowned: everything else, including `factual_consistency`,
  `curriculum_coverage`, `objective_references`, `research_evidence`,
  `required_gates_present`, and any gate name nobody has claimed.
  `factual_consistency` is unowned because its inputs (`evidence_map.claims`,
  `verified_source_ids`) are research artifacts the revision cycle never
  revisits — a content rebuild cannot clear it, so for a zero-supported-claims
  failure the run aborts immediately instead of burning the revision budget.
  `schema_validity` is not listed as a gate at all: schema conformance is
  enforced by pydantic at construction, so a decorative always-passed gate was
  removed (the original one could never fail).

Gate names live in `lpf.orchestration.gates` (TASK-013): one constant per gate,
emitted by the QA stage and referenced from here, so a name cannot drift between
what the stage emits and what the router owns. The catalog's equality with the
union of the ownership sets is locked by a cross-check test in
`tests/test_revision_loop.py`.

Ownership is **partial**. One unowned gate in the failure set aborts the run,
because no stage we are allowed to revisit can clear it. A mixed content +
assessment failure revisits content, since content rebuilds forward into
assessment anyway.

### 3. The budget is a property of the run, not a retry counter

`MAX_REVISIONS = 3` lives beside the transition table in `state.py`.
`RunState.begin_revision()` claims from it and raises
`WorkflowError(code="REVISION_BUDGET_EXHAUSTED")` when it is spent; the pipeline
checks `RunState.revisions_exhausted` first so it can fail with a message that
names the gates that never cleared. A run therefore ends in exactly one of three
ways: `COMPLETE`, "not repairable", or "budget exhausted".

Three is enough for a convergent defect and small enough that a deterministic
failure reports quickly. `VerificationResult.max_iterations` is set to
`MAX_REVISIONS + 1` so `iteration` and `max_iterations` describe the same cycle.

### 4. Superseded artifacts leave the run

On each cycle the pipeline calls `_discard(artifacts, <last pass's artifacts>)`
before rebuilding, matching by object identity. Without this the shipped product
would contain two sets of lessons — the ones QA rejected and the ones that
replaced them — and a manifest whose artifact count no longer matches what the
stage log says was produced.

### 5. The loop is announced

`EventType.REVISION_STARTED` records why a stage is about to run twice. It is
emitted only on a real revision, so a clean run's event log is unchanged.

## Consequences

- A content or assessment defect found by QA is repaired within three cycles and
  the run still completes, instead of failing outright.
- A defect whose fix is upstream still fails, with the owning gate named in
  `failure_reason`, rather than burning budget on a rebuild that cannot help.
- `stage_history` for a repaired run has more entries than `PIPELINE_STAGES`,
  so tests that assert a linear history must describe the linear *except QA
  revision* contract.
- `QA → CONTENT` means content artifacts are regenerated with new ids on a
  revision, which is correct but means the artifact list a run reports is the
  live set, not a log of everything ever built.

## Alternatives Rejected

- **Unbounded retry until QA passes.** The pipeline is deterministic; a
  persistent defect becomes an infinite loop, and the run's failure becomes a
  hang — strictly worse than a failed run.
- **No revision: fail and let a human re-run.** The factory has no human in the
  loop, so every repairable defect would be a lost run.
- **Revise on any QA failure.** Would route `research_evidence` and
  `curriculum_coverage` failures into rebuilds that provably cannot clear them.
- **Route by evidence artifact id.** More general, but every gate already knows
  the stage that produced what it reads; an ownership table is auditable in a
  way that an id lookup is not.
- **A state-graph library (e.g. LangGraph).** Still speculative for one
  two-edge cycle; adds a dependency the deterministic machine does not need.
