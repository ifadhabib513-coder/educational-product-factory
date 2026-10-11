# ADR-003: Content Models

**Status:** Accepted
**Date:** 2026-09-17

## Context

Stage 2b-i adds content models: Lesson, WorkedExample, Misconception, and EvidenceRecord. These models must integrate with the planning spine from Stage 2a.

## Decisions

### 1. Evidence taxonomy — honesty, not prohibition

`EvidenceKind` is a `StrEnum` with seven values: `direct_source`, `model_generated`, `inference`, `hypothesis`, `example`, `illustrative`, `human_approved`. Model-generated content is allowed but must be honestly labeled. The factory does not prohibit LLM-generated evidence; it requires truthful provenance.

### 2. Direct-source schema guard

A `@model_validator(mode="after")` on `EvidenceRecord` enforces: if `evidence_kind == "direct_source"` then `source` must not be `None`. This is the type-level enforcement of "no fabricated citations." The guard rejects at construction time, not at release time.

### 3. source_refs vs source — naming distinction

These are different concepts that must not be merged:

- **`ArtifactBase.source_refs: list[str]`** — references to other artifact IDs (e.g., a lesson cites an evidence record by ID). These are intra-system provenance links.
- **`EvidenceRecord.source: SourceRef | None`** — reference to an external source (book, journal, website). This is extra-system provenance.

### 4. Scope of validators vs functions

- **Schema validators** (`@model_validator`) guard intra-model invariants: a direct_source claim must have a source. These enforce constraints within a single model.
- **Result-returning functions** (`check_misconception_objective_refs`) guard cross-artifact references: a misconception references an objective that exists. These enforce constraints across models. The bypass risk (e.g., `model_construct()`) is cross-artifact, not intra-model, so the function is the appropriate enforcement point.

### 5. min_length guards

- `Lesson.objective_ids`: `Field(min_length=1)` — a lesson must address at least one objective.
- `Misconception.objective_ids`: `Field(min_length=1)` — a misconception must relate to at least one objective.
- `WorkedExample.solution_steps`: `Field(min_length=1)` — a worked example must have at least one step.

These are the first line of defense. Validation functions provide the second line for cross-artifact references.

## Consequences

- Evidence records are self-documenting about their provenance
- Fabricated citations are caught at construction, not release
- Cross-artifact validation uses `Result` types for explicit error handling
- Naming is unambiguous: `source_refs` = artifact IDs, `source` = external reference

## Amendment — 2026-10-11 (TASK-016)

`EvidenceRecord`/`EvidenceKind`/`VerificationStatus` (`src/lpf/domain/evidence.py`) had no
reachable consumer — no stage or shipped path constructed or read one — so the module was
removed. The provenance-honesty principle above is unchanged: it now lives in the research
`EvidenceClaim`/`EvidenceMap` schemas (ADR-006) and the `factual_consistency` gate, which
is what the pipeline actually enforces. See the whole-codebase audit
(`docs/audits/codebase-gaps-and-bugs.md`, §5).
