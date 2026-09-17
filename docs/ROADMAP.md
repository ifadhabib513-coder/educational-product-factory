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

## Stage 2 — Domain Schemas

**Status: PENDING**

- Artifact model
- Product definition
- Learner profile
- Learning objectives
- Prerequisite graph
- Curriculum
- Lessons
- Practice
- Assessment
- Evidence
- Visual specification
- Quality results

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
