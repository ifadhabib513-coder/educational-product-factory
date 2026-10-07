# Ralph Loop Execution Progress

This document tracks autonomous engineering iterations performed by the Ralph Loop on `AI Educational Product Factory`.

| Iteration | Timestamp | Task ID | Description | Status | Commit |
|-----------|-----------|---------|-------------|--------|--------|
| - | 2026-10-04 | Setup | Initialized Ralph loop harness (`PROMPT.md`, `tasks.md`, `scripts/ralph.ps1`, `scripts/ralph.sh`) | Ready | Initial |
| 1 | 2026-10-04 | TASK-001 | Exact-Title Definitional Signal in Research Scoring | Completed | `f0c0a66` |
| 2 | 2026-10-04 | TASK-002 | Eliminate Spurious False-Positive Conflicts in Mock Sentences | Completed | `ceca889` |
| 3 | 2026-10-05 | TASK-003 | Factual Quality Gate Validator | Completed | `f82be33`, `cf27812`, `0f65e47` |
| 4 | 2026-10-07 | TASK-004 | Numerical Consistency Gate for Worked Examples | Completed | `be905b3` |

---
## Detailed Iteration Logs

### Iteration 1 — 2026-10-04: TASK-001
- **Task**: Implement Exact-Title Definitional Signal in Research Scoring (`src/lpf/research/scoring.py`).
- **Rationale**: Resolves the live failure where narrow subtopics (`Basic Linear Algebra Subprograms`) could beat canonical definitional topics (`Linear algebra`).
- **Changes**:
  - Implemented `clean_title_for_matching`, `extract_query_topic`, and `has_exact_title` in `src/lpf/research/scoring.py`.
  - Re-weighted `intent_match` for `DEFINITIONAL` and `EXPLANATORY` intents: coverage (0.50), definition cue (0.30), exact title match (0.20).
  - Exported `has_exact_title` in `__all__`.
  - Added unit test suite `TestExactTitleMatch` and regression test `test_exact_title_separates_canonical_from_narrow_subtopic` in `tests/test_research_intent_scoring.py`.
- **Verification**:
  - `python -m pytest tests/`: 698 passed (17 new tests, 0 failures, 0 regressions).
  - `python -m ruff check src/ tests/`: All checks passed.
  - `python -m ruff format --check src/ tests/`: 125 files already formatted.

### Iteration 2 — 2026-10-04: TASK-002
- **Task**: Eliminate spurious false-positive conflicts in research mock sentences.
- **Rationale**: v0.6.0 version history recorded 8 false-positive conflicts on every offline run because the deterministic mock snippets shared bucket words.
- **Changes**:
  - Neutralised the `DeterministicSearchProvider` snippet in `src/lpf/orchestration/research_stage.py` to a single source-neutral string.
  - Offline conflict count dropped 8 → 0; genuine conflict-detection tests untouched.
- **Verification**:
  - `python -m pytest tests/`: all passing, conflict assertions re-run green.
  - Added regression coverage in `tests/test_e2e_pipeline.py::TestMockResearchNoise` (offline `conflicts == []`, `evidence_map.conflicting_claims == 0`) during iteration 3.
  - Commit `ceca889`.

### Iteration 3 — 2026-10-05 → 2026-10-07: TASK-003
- **Task**: Implement the factual quality gate validator (`src/lpf/validators/`).
- **Rationale**: QA previously had no way to fail a run whose claims were unsupported by the retrieved evidence.
- **Changes**:
  - Added `src/lpf/validators/` with `check_factual_claims_reference_valid_evidence` and `check_factual_consistency` (`INVALID_EVIDENCE_REFERENCES`, `CONTRADICTORY_EVIDENCE`, `UNGROUNDED_CLAIMS`).
  - Wired a `factual_consistency` gate into `build_qa` (`src/lpf/orchestration/qa_stage.py`).
  - Replaced the dead self-referential catalogue logic with a real one: `build_qa(..., verified_source_ids=...)` receives `{source.source_id for source in research.report.verified_sources}` from the pipeline, so a claim citing a source this run never verified now fails QA.
  - Corrected the gate `location` to `evidence_map` and rewrote `suggested_fix` to cover both citations and grounding.
  - Tests: `tests/test_validators_factual.py` (16 tests, including pipeline spy and phantom-source failure) plus `TestMockResearchNoise`.
- **Verification**:
  - `python -m pytest tests/`: 717 passed.
  - `python -m ruff check .`: All checks passed; `python -m ruff format --check .`: 144 files already formatted.
  - Mutation-tested: removing the pipeline wiring makes both catalogue tests fail; renaming the gate fails 3 tests.
  - Live `--live-research` run (arXiv + Wikimedia) succeeds with the gate green.
  - Commits `f82be33`, `cf27812`, `0f65e47`.

### Iteration 4 — 2026-10-07: TASK-004
- **Task**: Implement numerical/symbolic consistency validation for worked examples.
- **Changes**:
  - Added `src/lpf/validators/numerics.py` with `check_worked_example_arithmetic`:
    - Exact `fractions.Fraction` evaluation over a whitelisted AST (no `eval`, no network, no new dependency), so `0.1 + 0.2` equals `0.3` exactly.
    - Reports `step_mismatch` (a false equation such as `2 + 3 = 6`), `step_contradiction` (a variable silently redefined), `answer_mismatch` (`final_answer` disagreeing with the steps) and `undefined_arithmetic` (division by zero).
    - Pseudocode and prose (`result = apply(method, problem)`) are skipped rather than guessed at, so the default content stage output is never falsely flagged.
  - Wired a `numerical_consistency` gate into `build_qa` and passed `content.worked_examples` from the pipeline.
  - Tests: `tests/test_validators_numerics.py` (31 tests — evaluator exactness/whitelist, passing chains, four defect classes, gate wiring, pipeline spy, run-fails-before-packaging).
- **Verification**:
  - `python -m pytest tests/`: 748 passed (31 new, 0 regressions).
  - `python -m ruff check .`: All checks passed; `python -m ruff format --check .`: 146 files already formatted.
  - Mutation-tested (5/5 caught): gate short-circuited, step comparison flipped, final-answer check dropped, pipeline stops passing examples, binary floats replace exact decimals.
  - Commit `be905b3`.
