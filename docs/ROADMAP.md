# AI Educational Product Factory — Roadmap

## Stage 0 — Repository Audit

**Status: COMPLETE**
**Completed:** 2026-09-17

- Inspected empty repository
- Documented environment (Python 3.14.5, Git 2.55.0, available packages)
- Identified missing foundations
- Identified known risk: Manim may not yet support Python 3.14; if Stage 12 is blocked, plan a Python 3.12 fallback via `uv`

## Stage 1 — Project Foundation

**Status: COMPLETE**
**Completed:** 2026-09-17

- Python project setup (pyproject.toml, hatchling)
- Configuration (frozen dataclass, env-var loading)
- Logging setup
- Error model (LpfError hierarchy)
- Result type (Result[T, E])
- CLI skeleton (click-based)
- CI pipeline (GitHub Actions)
- Test structure
- ADR-001

## Stage 2a — Domain Schemas (Planning Spine)

**Status: COMPLETE**
**Completed:** 2026-09-17

- Pydantic v2 BaseModel for all domain models (frozen, extra="forbid")
- Identity utilities: new_id(), compute_content_hash(), with_content_hash()
- ArtifactBase with schema_version, id, artifact_type, status, created_at, content_hash, parent_id, generator, source_refs
- GeneratorInfo (provider, model, prompt_version)
- LearnerProfile (subject, level, goals, challenges, prior_knowledge, constraints) — fully subject-agnostic, inherits ArtifactBase
- ProductDefinition (title, subject, topic, level, problem_statement, learner_profile_id)
- LearningObjective (statement, bloom_level, mastery_criteria) with BloomLevel enum
- Prerequisite (prerequisite_objective_id, objective_id, rationale)
- CurriculumUnit (unit_id, title, objective_ids [min_length=1], order) and CurriculumBlueprint (required title)
- check_objective_references() validation function (two-layer: schema guard + validation function)
- ADR-002 documenting schema decisions
- 39 tests passing

**Repairs (post-commit):**
- R1: Restored `Field(min_length=1)` on `CurriculumUnit.objective_ids`; test uses `model_construct()` to bypass Pydantic validation; ADR-002 documents two-layer design
- R2: Made `CurriculumBlueprint.title` required (no default)
- R3: Promoted `LearnerProfile` to inherit `ArtifactBase` (gains `id`, `created_at`); test determinism uses `model_copy()` instead of constructing twice; `_make_product` uses `profile.id`
- R4: Narrowed exception assertions from `pytest.raises(Exception)` to `pytest.raises(ValidationError)`

## Stage 2b-i — Domain Schemas (Content Models)

**Status: COMPLETE**
**Completed:** 2026-09-17

- SolutionStep, SourceRef value objects (content.py)
- Lesson (artifact_type="lesson") with objective_ids min_length=1
- WorkedExample (artifact_type="worked_example") with solution_steps min_length=1
- Misconception (artifact_type="misconception") with MisconceptionSeverity StrEnum
- EvidenceRecord (artifact_type="evidence_record") with EvidenceKind StrEnum
  - model_validator: direct_source requires source (no fabricated citations)
  - model_generated is a first-class kind (honesty, not prohibition)
- check_misconception_objective_refs() validation function
- Refactored validation.py with _check_id_refs helper (check_objective_references signature unchanged)
- ADR-003 documenting evidence taxonomy, source_refs vs source, two-layer validation scope
- 56 tests passing

## Stage 2b-ii — Domain Schemas (Practice, Assessment, Quality)

**Status: PENDING**

- PracticeQuestion
- Hint
- AnswerKey
- Rubric
- Assessment
- VisualSpecification
- QualityGateResult
- VerificationResult

## Stage 3 — Workflow Engine

**Status: PENDING**

- Workflow state machine
- Legal transitions
- Events
- Persistence abstraction
- Failure handling
- Retry and repair

## Stage 4 — Mock End-to-End Pipeline

**Status: PENDING**

- Deterministic demo using mock data and mock LLM
- Must generate all core artifacts end-to-end
- No real LLM integration until this works

## Stage 5 — Subject Adapter System

**Status: PENDING**

- Adapter protocol and registry
- Mathematics adapter
- Physics adapter
- Chemistry adapter
- Biology adapter
- English adapter

## Stage 6 — Learning Design Engine

**Status: PENDING**

- Objective generation
- Prerequisite mapping
- Curriculum planning
- Misconception modeling
- Alignment checking

## Stage 7 — LLM Provider Layer

**Status: PENDING**

- Mock provider
- Ollama provider
- OpenAI-compatible provider
- Structured output validation
- Retry and timeout handling

## Stage 8 — Content Generation

**Status: PENDING**

- Lesson generation
- Explanation generation
- Worked examples
- Summaries
- Misconception explanations

## Stage 9 — Practice and Assessment

**Status: PENDING**

- Question generation
- Difficulty classification
- Hint generation
- Answer-key generation
- Rubrics
- Diagnostic assessment
- Final assessment

## Stage 10 — Verification Engine

**Status: PENDING**

- Structural validation
- Numerical/symbolic validation
- Factual/evidence validation
- Linguistic validation
- Alignment validation
- Answer-key validation

## Stage 11 — Static Visual System

**Status: PENDING**

- Visual specification schema
- SVG renderer
- Matplotlib renderer
- Mermaid renderer
- Layout and label validation

## Stage 12 — Manim Plugin

**Status: PENDING**

- Manim availability detection
- Approved scene templates
- Sandboxed execution
- Preview generation
- Validation
- Failure recovery
- **Known risk:** Manim may not yet support Python 3.14; if blocked, plan Python 3.12 fallback via `uv`

## Stage 13 — Rendering and Packaging

**Status: PENDING**

- Markdown output
- HTML output
- PDF output
- ZIP bundle
- Manifest generation

## Stage 14 — Human Review

**Status: PENDING**

- Review queue
- Review checklist
- Approve/reject/request-repair workflow
- Release blocking

## Stage 15 — Public GitHub Release

**Status: PENDING**

- Documentation
- Examples
- Contribution guide
- Security policy
- License
- CI quality checks
- Demo projects
