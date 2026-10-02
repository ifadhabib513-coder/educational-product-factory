# ADR-004: Practice, Assessment, Quality, and Enhanced ProductSpec

**Status:** Accepted
**Date:** 2026-09-27

## Context

Stage 2b-ii completes the domain schema layer by adding practice, assessment, quality, and verification models. It also enhances the product specification to match the Phase 1 North Star Architecture. The factory now has a complete schema foundation for all core artifacts.

## Decisions

### 1. Practice question taxonomy

Three StrEnum value objects define the practice domain:

- **QuestionType** (9 values): multiple_choice, short_answer, true_false, numerical, proof, explanation, matching, ordering, fill_blank. Covers the full range of educational question formats without over-engineering.
- **DifficultyLevel** (4 values): beginner, intermediate, advanced, challenge. Linear progression, not nested.
- **ScaffoldingType** (4 values): nudge, conceptual, procedural, worked_partial. Progression from subtle hint to partial solution.

### 2. PracticeQuestion links to both lesson and objectives

`PracticeQuestion` carries both `lesson_id` (which lesson this question belongs to) and `objective_ids` (which objectives it assesses). This dual linkage enables:
- Per-lesson exercise sets (pedagogical grouping)
- Per-objective coverage analysis (curriculum verification)
- Difficulty distribution analysis across objectives

### 3. Assessment as a question container

`Assessment` is a thin wrapper around `question_ids` with metadata (type, title, time limit, total points). It does not embed questions. This keeps questions reusable across assessments and avoids data duplication.

### 4. Rubric as a separate artifact

`Rubric` is linked to a question via `question_id`, not embedded. A single rubric can be shared across questions with similar evaluation criteria. `RubricCriterion` requires `min_length=2` on levels (must have at least two performance levels to be meaningful).

### 5. AnswerKey aggregates Answers

`AnswerKey` wraps a list of `Answer` objects with `min_length=1`. Each `Answer` links to a `question_id` and carries `answer_format` (exact, numeric, range, rubric, explanation) to guide evaluation. The `rubric_id` field on `Answer` optionally links to a `Rubric` for rubric-based scoring.

### 6. Quality gate as a two-level structure

- **QualityGate**: a single gate check (gate_name, status, score, findings). Each gate is an independent artifact.
- **VerificationResult**: aggregates multiple gates with `overall_status` and `overall_score`. Carries `iteration` and `max_iterations` to support the self-correction loop (Phase 12).

`Finding` is a value object (not a root artifact) because findings only exist within the context of a gate. It carries severity (critical/major/minor), location, problem, evidence, and suggested_fix.

### 7. GateStatus as a five-state enum

`passed | failed | warning | skipped | not_applicable`. The `warning` state is critical: it allows the factory to flag issues that don't block production but should be reviewed. `skipped` and `not_applicable` support partial verification (e.g., math gate skipped for a purely verbal product).

### 8. ProductSpec as the comprehensive specification

`ProductSpec` extends `ArtifactBase` with nested value objects:
- `TargetAudience`: level, age_range, exam_target, language
- `FormatSpec`: primary product type, page count, exercise/assessment counts, answer_key flag, citations flag
- `LearningSpec`: progression list, mastery criteria, bloom target
- `ConstraintsSpec`: evidence/citation requirements, calculator allowance, exam alignment, max pages
- `QualitySpec`: minimum score, required gates list

`ProductDefinition` is preserved for backward compatibility with Stage 2a tests and existing code.

### 9. ProductType as a 14-value taxonomy

Covers the full product spectrum from single artifacts (book, workbook) to compound systems (recovery_program, learning_system, product_suite). The `product_suite` type enables the factory to generate coordinated multi-artifact products from a single specification.

### 10. Cross-artifact validation functions

Six new validation functions enforce cross-artifact consistency:

| Function | Validates |
|----------|-----------|
| `check_question_references` | question.lesson_id ∈ known_lessons, question.objective_ids ⊆ known_objectives |
| `check_assessment_references` | assessment.question_ids ⊆ known_questions |
| `check_answer_references` | answer.question_id ∈ known_questions |
| `check_answer_key_references` | delegates to check_answer_references for all answers |
| `check_quality_gate_references` | required_gates ⊆ verification.gates |
| `check_prerequisite_chain` | prerequisite refs valid + DFS cycle detection |

All return `Result[T, ValidationError>` for explicit error handling, matching the pattern established in ADR-002.

### 11. Cycle detection in prerequisite chains

`check_prerequisite_chain` performs DFS-based cycle detection on the prerequisite graph. A cycle (e.g., A requires B requires C requires A) is a hard error because it makes the curriculum unsatisfiable. The function builds an adjacency list from prerequisites and detects gray-node back-edges.

### 12. Belt-and-suspenders for empty lists

Two tests use `model_construct()` to bypass Pydantic's `min_length=1` guard and test the validation function's handling of empty lists. This follows the pattern from Stage 2a (R1 repair) where `model_construct()` is the documented escape hatch for testing cross-artifact validators that must handle edge cases the schema guard would normally reject.

## Consequences

- The factory has a complete schema foundation for practice, assessment, quality, and verification
- ProductSpec is the single source of truth for what the factory produces
- Cross-artifact validation enforces referential integrity across the entire artifact graph
- Cycle detection prevents unsatisfiable prerequisite chains at validation time
- Backward compatibility is preserved: all 56 original tests still pass unchanged
- The schema layer is now complete enough to support Stage 3 (Workflow Engine) and Stage 4 (Mock Pipeline)
