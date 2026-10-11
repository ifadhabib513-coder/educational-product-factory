"""Single source of truth for QA gate names (TASK-013).

Every quality-gate name the QA stage can emit is declared here exactly once.
The QA stage builds its gates from these constants and ``revision`` owns gates
through them, so a gate name can never drift between what the stage emits and
what the revision router knows about.
"""

from __future__ import annotations

from typing import Final

CURRICULUM_COVERAGE: Final[str] = "curriculum_coverage"
OBJECTIVE_REFERENCES: Final[str] = "objective_references"
MISCONCEPTION_REFERENCES: Final[str] = "misconception_references"
QUESTION_REFERENCES: Final[str] = "question_references"
ASSESSMENT_REFERENCES: Final[str] = "assessment_references"
ANSWER_REFERENCES: Final[str] = "answer_references"
ANSWER_KEY_REFERENCES: Final[str] = "answer_key_references"
RESEARCH_EVIDENCE: Final[str] = "research_evidence"
FACTUAL_CONSISTENCY: Final[str] = "factual_consistency"
NUMERICAL_CONSISTENCY: Final[str] = "numerical_consistency"
REQUIRED_GATES_PRESENT: Final[str] = "required_gates_present"

#: The complete catalog of gate names the QA stage can emit. Every name must
#: appear in exactly one revision ownership set (see :mod:`lpf.orchestration.
#: revision`); ``revision`` imports from here, so the cross-check test only
#: needs to compare the catalog against the ownership sets.
ALL_GATES: Final[tuple[str, ...]] = (
    CURRICULUM_COVERAGE,
    OBJECTIVE_REFERENCES,
    MISCONCEPTION_REFERENCES,
    QUESTION_REFERENCES,
    ASSESSMENT_REFERENCES,
    ANSWER_REFERENCES,
    ANSWER_KEY_REFERENCES,
    RESEARCH_EVIDENCE,
    FACTUAL_CONSISTENCY,
    NUMERICAL_CONSISTENCY,
    REQUIRED_GATES_PRESENT,
)
