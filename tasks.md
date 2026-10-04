# Ralph Task Backlog: AI Educational Product Factory

> Managed by the Ralph autonomous loop. Tasks are executed sequentially from top to bottom.
> Each Ralph iteration picks the first uncompleted task `[ ]`, tests and verifies, marks it `[x]`, logs in `PROGRESS.md`, and commits to git.

---

## v0.7.0 Milestone Tasks

- [x] **TASK-001**: Implement Exact-Title Definitional Signal in Research Scoring
  - **Objective**: In `src/lpf/research/scoring.py` (and `relevance.py`), when query intent is `DEFINITIONAL` or `EXPLANATORY`, incorporate an exact/normalized title match signal so that an encyclopedic article matching the topic title exactly is promoted over incidental query mentions.
  - **Acceptance Criteria**:
    - Add a function (e.g. `exact_title_match(query: str, title: str) -> bool` or title normalization helper).
    - When intent is `DEFINITIONAL`, boost/weight candidates whose title matches the queried topic.
    - Write unit tests in `tests/test_research_intent_scoring.py` verifying exact-title definitional queries rank encyclopedic articles higher than incidental mentions.
    - Full pytest suite (671+ tests) and ruff linters pass.

- [ ] **TASK-002**: Eliminate Spurious False-Positive Conflicts in Research Mock Sentences
  - **Objective**: As identified in v0.6.0 version history, mock canned sentences share bucket words causing the conflict detector to report 8 false-positive conflicts during offline pipeline runs.
  - **Acceptance Criteria**:
    - Inspect mock source texts and conflict detection keywords/buckets.
    - Adjust mock texts or bucket disambiguation so offline pipeline does not trigger spurious false-positive conflicts.
    - Ensure genuine conflict detection tests continue passing with zero regressions.
    - Full pytest suite and ruff linters pass.

- [ ] **TASK-003**: Implement Factual Quality Gate Validator
  - **Objective**: Implement the factual consistency hard gate in `src/lpf/validators/` or `src/lpf/qa/` verifying generated lesson/claim assertions align with direct research evidence records.
  - **Acceptance Criteria**:
    - Schema validation and verification logic ensuring factual claims cite valid evidence record IDs.
    - Fails QA when assertions are ungrounded or contradictory to evidence.
    - Unit tests covering passing grounded content and failing ungrounded/conflicting content.
    - Full pytest suite and ruff linters pass.

- [ ] **TASK-004**: Implement Numerical and Symbolic Gate Validator
  - **Objective**: Implement numerical/symbolic consistency validation for STEM/quantitative lessons and worked examples (e.g., matching calculation steps to final answers using deterministic Python/SymPy evaluation).
  - **Acceptance Criteria**:
    - Validator verifying mathematical consistency between worked example steps and answers.
    - Unit tests with both correct equations/calculations and flawed examples caught by the gate.
    - Full pytest suite and ruff linters pass.

- [ ] **TASK-005**: Add Multi-Format Packaging (HTML and ZIP Bundle)
  - **Objective**: Extend `lpf.packaging` so `lpf generate` / packaging stage outputs clean standalone HTML and an archival ZIP bundle in addition to Markdown and JSON manifests.
  - **Acceptance Criteria**:
    - HTML generator template or converter for `product.md`.
    - ZIP bundler creating `<run_id>.zip` containing manifest, markdown, html, and json artifacts.
    - Unit tests in `tests/test_packaging.py` or `tests/test_e2e_pipeline.py`.
    - Full pytest suite and ruff linters pass.

- [ ] **TASK-006**: Support Cyclic Stage Machine Revision Loop
  - **Objective**: Upgrade the stage machine from purely linear to allow cyclic transitions from `qa` failure back to `content` or `assessment` revision before retrying QA (up to a max revision count).
  - **Acceptance Criteria**:
    - Update state machine transition table to permit `qa -> content` on repairable QA findings.
    - Enforce bounded iteration count to prevent infinite revision loops.
    - Add tests verifying successful revision loop and eventual completion or abort.
    - Full pytest suite and ruff linters pass.
