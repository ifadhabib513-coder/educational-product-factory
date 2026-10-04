# Ralph Loop Execution Progress

This document tracks autonomous engineering iterations performed by the Ralph Loop on `AI Educational Product Factory`.

| Iteration | Timestamp | Task ID | Description | Status | Commit |
|-----------|-----------|---------|-------------|--------|--------|
| - | 2026-10-04 | Setup | Initialized Ralph loop harness (`PROMPT.md`, `tasks.md`, `scripts/ralph.ps1`, `scripts/ralph.sh`) | Ready | Initial |
| 1 | 2026-10-04 | TASK-001 | Exact-Title Definitional Signal in Research Scoring | Completed | `f0c0a66` |

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
