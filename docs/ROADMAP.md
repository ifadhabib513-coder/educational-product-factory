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

**Status: COMPLETE**
**Completed:** 2026-09-27

- QuestionType (9 values), DifficultyLevel (4 values), ScaffoldingType (4 values)
- PracticeQuestion (artifact_type="practice_question") with min_length=1 on objective_ids
- Hint (artifact_type="hint") with ScaffoldingType enum
- AnswerFormat (5 values), AssessmentType (4 values)
- Answer (artifact_type="answer") with solution_steps and optional rubric_id
- AnswerKey (artifact_type="answer_key") with min_length=1 on answers
- RubricCriterion with min_length=2 on levels, RubricLevel value object
- Rubric (artifact_type="rubric") with min_length=1 on criteria
- Assessment (artifact_type="assessment") with min_length=1 on question_ids
- GateStatus (5 values), Severity (3 values)
- Finding value object with severity/location/problem/evidence/suggested_fix
- QualityGate (artifact_type="quality_gate") with findings list
- VerificationResult (artifact_type="verification_result") with min_length=1 on gates
- Enhanced ProductSpec (Phase 1 alignment):
  - ProductType (14 values including product_suite)
  - TargetAudience, FormatSpec, LearningSpec, ConstraintsSpec, QualitySpec
  - ProductSpec root artifact with full specification
  - ProductDefinition preserved for backward compatibility
- New validation functions:
  - check_question_references() — validates lesson_id and objective_ids
  - check_assessment_references() — validates question_ids
  - check_answer_references() — validates question_id
  - check_answer_key_references() — validates all answers in key
  - check_quality_gate_references() — validates required gates present
  - check_prerequisite_chain() — validates refs + cycle detection via DFS
- 103 new tests (159 total), all passing
- Lint clean, format clean
- ADR-004 documenting design decisions

## Stage 3 — Workflow Engine

**Status: PARTIAL** (see ADR-008)

- Workflow state machine — COMPLETE (`orchestration/state.py`, forward-linear machine with two bounded QA revision edges; see ADR-010)
- Legal transitions — COMPLETE (`ILLEGAL_TRANSITION` on illegal advance)
- Events — COMPLETE (`orchestration/events.py`, `run_log.json`, `revision_started`)
- Failure handling — COMPLETE (`LpfError` → failed run value; unexpected errors propagate)
- Persistence abstraction — PENDING (filesystem only; no DB/memory store yet)
- Retry and repair — COMPLETE (QA rewinds to content or assessment for repairable gates, bounded by `MAX_REVISIONS = 3`)

## Stage 4 — Mock End-to-End Pipeline

**Status: COMPLETE** (see ADR-008)

- Deterministic demo using mock data and mock LLM — COMPLETE (`FactoryPipeline`)
- Must generate all core artifacts end-to-end — COMPLETE (23 artifacts: discovery → specification → research → syllabus → content → assessment → QA → packaging)
- No real LLM integration until this works — upheld (only the mock provider is wired)
- Byte-identical output across runs — COMPLETE (asserted in `tests/test_e2e_pipeline.py`)
- `lpf generate` wired to the real pipeline — COMPLETE
- Found and fixed 3 production defects on first integration run: nondeterministic `claim_id`, nondeterministic `QualityGate.checked_at`, and packaging before the run reached `complete`
- Real sources reachable via `lpf generate --live-research` — COMPLETE (ADR-009)

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

---

# Full Factory Roadmap (31 Phases)

The following phases represent the complete vision for the AI Product Factory, mapped from the North Star Architecture. Build order follows the recommended stage sequence below.

## Phase 1 — Product Specification

**Status: PARTIAL** (ProductSpec schema complete)

Define the Product Contract. Create ProductSpec as the source of truth.

- ProductType enum (14 values) — COMPLETE
- TargetAudience, FormatSpec, LearningSpec, ConstraintsSpec, QualitySpec — COMPLETE
- ProductSpec root artifact — COMPLETE
- ProductDefinition preserved for backward compatibility

## Phase 2 — Product Taxonomy

**Status: PENDING**

- Product types and combinations
- Product suite generation (e.g., Recovery Protocol = Core Guide + Diagnostic + Workbook + ...)
- Automatic format selection based on problem + audience

## Phase 3 — Learner & Problem Discovery

**Status: COMPLETE**

- Discovery Agent
- LearnerProfile, ProblemDefinition, OutcomeDefinition, ProductOpportunity — COMPLETE
- Problem analysis pipeline
- MarketAnalysis, DiscoveryBrief, DiscoveryInputs — COMPLETE
- 5 enums: ProblemUrgency, ProblemScope, PainPointCategory, MarketSegment, FeasibilityLevel — COMPLETE
- 4 validation functions: check_discovery_chain, check_outcome_references, check_discovery_brief, check_feasibility — COMPLETE
- Discovery crew contracts for agents 01, 02, 03 — COMPLETE
- Discovery prompt templates (versioned) — COMPLETE
- See ADR-005

## Phase 4 — Research Engine

**Status: COMPLETE** (see ADR-006, ADR-007, ADR-009)

- Research pipeline: Search → Source collection → Classification → Evidence extraction → Claim mapping → Confidence — COMPLETE
- ResearchItem schema — COMPLETE (SearchResult, VerifiedSource, EvidenceClaim, EvidenceMap, KnowledgeGap)
- Source hierarchy (primary → university → academic → educational → textbook → secondary → general) — COMPLETE (SourceAuthority, 8 values)
- Web search integration — COMPLETE: SearXNG, Tavily, arXiv, Wikimedia, Mock
- ResearchRouter (question → SearchStrategy → provider execution) — COMPLETE
- ResearchService (search_web, search_academic, search_wiki, extract_url) — COMPLETE
- Authority-weighted source ranking — COMPLETE
- Deterministic authority classifier with spoofing resistance — COMPLETE
- Shared HTTP transport (retry, backoff, rate limiting) — COMPLETE
- ResearchPipeline (dedupe → filter → rank → claims → conflicts → gaps → EvidenceMap) — COMPLETE
- Provider injection seam (offline default, live providers opt-in) — COMPLETE (ADR-009)
- Per-question relevance and confidence scoring — COMPLETE (ADR-009)
- Intent-aware provider routing — PENDING (definitional queries still hit arXiv and correctly score as unsupported)

## Phase 5 — Syllabus & Knowledge Graph

**Status: PENDING** (CurriculumBlueprint exists, needs knowledge graph)

- Subject → Domain → Topic → Concept → Subconcept → Skill → Prerequisite → Misconception
- Knowledge graph storage (start with PostgreSQL relationships)
- Prerequisite chain validation (check_prerequisite_chain exists)

## Phase 6 — Curriculum Engine

**Status: PENDING** (CurriculumBlueprint exists, needs progression logic)

- Learning progression model: Understand → Recognize → Apply → Analyze → Solve → Transfer → Master
- Dependency enforcement
- Bloom's taxonomy integration (BloomLevel enum exists)

## Phase 7 — Product Architecture Engine

**Status: PENDING**

- Convert curriculum into book/product structure
- Chapter schema (id, title, objectives, prerequisites, concepts, examples, exercises, assessment, mastery_criteria, sources)
- Book structure: Front Matter → Diagnostic → Parts → Assessment → Answer Key → Reference

## Phase 8 — Content Generation Engine

**Status: PENDING** (Lesson, WorkedExample models exist)

- Specialized generators: Explanation, Example, Exercise, Hint, Answer, Summary, Misconception, Assessment
- Concept → Explanation → Example → Exercise → Answer → Verification pipeline
- Model abstraction (ModelProvider interface)

## Phase 9 — Deterministic Verification

**Status: PENDING** (QualityGate, VerificationResult schemas exist)

- Python/SymPy for math verification
- Domain validators for chemistry (conservation of mass, element counting)
- Structural validation (every objective has content, every exercise has answer, etc.)

## Phase 10 — QA Engine

**Status: PENDING** (Finding, QualityGate schemas exist)

- 11 QA categories: Factual, Mathematical, Scientific, Pedagogical, Curriculum, Exam-alignment, Coverage, Consistency, Language, Formatting, Safety
- Structured findings per category
- Independent QA agents

## Phase 11 — Quality Gate System

**Status: PARTIAL** (gate runner implemented in the offline pipeline; see ADR-008)

- Gate runner delegating to real validators — COMPLETE (`orchestration/qa_stage.py`)
- Curriculum completeness gate (every objective covered) — COMPLETE
- Research/evidence gate (at least one supported claim) — COMPLETE
- Required-gates presence check — COMPLETE
- BUILD FAILED on critical failure — COMPLETE (a `failed` verdict aborts before packaging)
- 10 hard gates: Schema validity, Research validity, Curriculum completeness, Factual accuracy, Mathematical correctness, Exercise-answer consistency, Learning objective coverage, Internal consistency, Citation coverage, Rendering validity — 6 of 10 wired; factual/numerical/linguistic/rendering gates PENDING
- GateStatus enum (passed/failed/warning/skipped/not_applicable) — COMPLETE

## Phase 12 — Self-Correction Loop

**Status: PENDING**

- Generate → Verify → Fail? → Fix → Verify → Fail?
- Max iteration limit (max_iterations field exists on VerificationResult)
- Regression test suite

## Phase 13 — Root-Cause Revision

**Status: PENDING**

- Failure schema with type, chapter, concept, issue, evidence
- Revision agent with targeted fixes (add prerequisite, move concept, change exercise)
- Replace generic regeneration with precise repair

## Phase 14 — Rendering Engine

**Status: PENDING**

- Separate content from presentation
- Structured JSON → Template Engine → Document → PDF → Visual Inspection
- HTML/Markdown renderer
- PDF renderer (WeasyPrint or similar)

## Phase 15 — Visual QA

**Status: PENDING**

- Page overflow detection
- Broken table detection
- Equation rendering validation
- Font consistency, margins, headers, footers
- PDF → images → vision QA pipeline

## Phase 16 — Product Assembly

**Status: PENDING**

- Generate commercial product bundle: Main Book, Workbook, Answer Key, Diagnostic, Cheat Sheet, Planner, Flashcards, AI Prompt Pack, Sources
- Auto-generate metadata (title, subtitle, description, TOC, manifest, version)
- ZIP bundle generation

## Phase 17 — Human Review

**Status: PENDING**

- Review queue with checklist
- Approve/reject/request-repair workflow
- Human sees: summary, critical findings, QA results, uncertain claims, sources, changes, preview
- Release blocking

## Phase 18 — Product Memory

**Status: PENDING**

- Store: Product, Research, Curriculum, Prompts, Errors, QA findings, Revisions, Human corrections, User feedback
- SQLite start → PostgreSQL later
- Product history and versioning

## Phase 19 — Experience → Policy

**Status: PENDING**

- Failure pattern detection from product memory
- Policy extraction (e.g., "15% of exercises flagged → avoid pattern")
- Apply policies to future generation
- Experience → Failure analysis → Pattern → Policy → Future generation

## Phase 20 — Product Evaluation From Real Users

**Status: PENDING**

- Collect: Downloads, completion, exercise accuracy, drop-off points, reviews, refunds, questions, corrections, support requests
- Connect to product graph for targeted improvement
- Chapter 6 abandonment → analyze exercises → difficulty too high → curriculum adjustment

## Phase 21 — Market Discovery

**Status: PENDING**

- Market signals → Student problems → Demand analysis → Competition → Opportunity candidates → Product proposals
- Automated opportunity discovery (not publishing yet)

## Phase 22 — Product Portfolio Engine

**Status: PENDING**

- Multi-product management
- Per-product: version, status, quality, research, audience, performance, feedback, revision history
- Cross-product analytics

## Phase 23 — Full Agent Architecture

**Status: PENDING**

- Factory Controller → Product Manager + Quality Manager
- Research, Curriculum, Content, Fact QA, Math QA, Pedagogy QA agents
- Verification → Revision Loop → Rendering → Final QA
- Agents as replaceable plugins

## Phase 24 — Technical Stack

**Status: PARTIAL** (Python, Pydantic, pytest, ruff complete)

- Orchestration: LangGraph (state, workflow, branching, loops, interrupts, checkpoints, human approval)
- Specialist execution: CrewAI (where multi-agent collaboration helps)
- Data contracts: Pydantic (COMPLETE)
- Database: SQLite → PostgreSQL
- Vector memory: pgvector (later)
- Knowledge graph: PostgreSQL relationships (start)
- Computation: Python + SymPy + domain validators
- Document generation: HTML/Markdown/JSON → PDF
- Tests: pytest (COMPLETE)
- Observability: run ID, product ID, agent, model, prompt version, input, output, tool calls, validation, errors, revision, cost, duration

## Phase 25 — Repository Architecture

**Status: PARTIAL** (src/lpf structure exists)

Target structure:
```
ai-product-factory/
├── apps/cli/ + api/
├── factory/orchestration/
├── factory/discovery/
├── factory/research/
├── factory/curriculum/
├── factory/product/
├── factory/content/
├── factory/exercises/
├── factory/verification/
├── factory/qa/
├── factory/rendering/
├── factory/memory/
├── factory/learning/
├── schemas/ (→ src/lpf/domain/)
├── templates/
├── prompts/
├── tests/unit/ + integration/ + evaluation/ + golden/
├── products/
├── configs/
└── docs/
```

## Phase 26 — Testing Strategy

**Status: PARTIAL** (681 tests passing, 96% coverage)

- End-to-end offline pipeline tests — COMPLETE (stage machine, packaging, byte-identical determinism)
- Failure-path tests — COMPLETE (QA failure aborts before packaging; domain errors returned as values; unexpected errors propagate)
- Provider injection tests — COMPLETE (injection honoured; offline default preserved)
- Live provider verification — arXiv ✅, Wikimedia ✅ (fixed 403), SearXNG requires self-hosting, Tavily pending API key
- Derived relevance scoring for providers reporting no score — COMPLETE
- Intent-conditioned ranking + audience fit — COMPLETE (see ADR-007)
- Query intent classification (7 intents, deterministic) — COMPLETE
- Audience fit threaded from `LearnerProfile.level` — COMPLETE
- Corpus-relative freshness — COMPLETE (`published_at` still arXiv/Tavily only)
- Benchmark: Beginner Definition Retrieval — COMPLETE (mutation-verified)

- Layer 1: Unit tests (validators, schemas, parsers, calculators, renderers)
- Layer 2: Integration tests (Research → Curriculum → Content → QA → Revision)
- Layer 3: Golden products (known-good products for regression)
- Layer 4: Failure tests (inject wrong answer, missing citation, contradiction, bad equation, duplicate exercise, broken reference)

## Phase 27 — Evaluation Framework

**Status: PENDING**

- 11 measurable dimensions: Accuracy, Evidence, Curriculum, Pedagogy, Exercises, Answers, Difficulty, Completeness, Consistency, Presentation, Usability
- Automated metrics + deterministic gates + LLM evaluation + human evaluation
- No self-scoring by the same LLM that generated content

## Phase 28 — Cost Optimization

**Status: PENDING**

- Model hierarchy: Simple tasks → Cheap LLM, Medium → Mid LLM, Difficult → Strong LLM
- Formatting, classification, metadata → cheap
- Curriculum design, research synthesis → stronger
- Difficult reasoning, QA arbitration → strongest
- Deterministic Python wherever possible

## Phase 29 — Model Independence

**Status: PENDING**

- ModelProvider abstraction interface
- OpenAI, Gemini, DeepSeek, Groq, local Ollama implementations
- Protect from vendor lock-in

## Phase 30 — Human Approval → Exception Handling

**Status: PENDING**

- Confidence-based routing: HIGH → auto-pass, LOW → human review
- Human intervention = exception handling, not manual production
- Path to autonomy

## Phase 31 — Autonomous Factory

**Status: PENDING**

- MARKET → Opportunity → Product Idea → Spec → Research → Curriculum → Design → Content → Exercises → Verification → QA → FAIL? → Repair → PASS → Assembly → Product → Publish → Feedback → Learning → Better Factory
- Full autonomous loop with human approval only for exceptions
