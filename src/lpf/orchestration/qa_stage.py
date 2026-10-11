"""QA stage — runs the real validators as quality gates.

Every gate delegates to an existing ``check_*`` validator or an explicit coverage
assertion, so QA cannot pass by re-testing what construction already guaranteed.
Gate names are the :mod:`lpf.orchestration.gates` catalog constants, the single
source of truth the revision router keys on.
"""

from __future__ import annotations

from dataclasses import dataclass

from lpf.domain.assessment import Answer, AnswerKey, Assessment
from lpf.domain.curriculum import CurriculumBlueprint
from lpf.domain.identity import with_content_hash
from lpf.domain.lesson import Lesson
from lpf.domain.misconception import Misconception
from lpf.domain.objectives import LearningObjective
from lpf.domain.practice import PracticeQuestion
from lpf.domain.quality import (
    Finding,
    GateStatus,
    QualityGate,
    Severity,
    VerificationResult,
)
from lpf.domain.validation import (
    check_answer_key_references,
    check_answer_references,
    check_assessment_references,
    check_misconception_objective_refs,
    check_objective_references,
    check_question_references,
)
from lpf.domain.worked_example import WorkedExample
from lpf.errors import ValidationError
from lpf.orchestration.context import RunContext
from lpf.orchestration.gates import (
    ANSWER_KEY_REFERENCES,
    ANSWER_REFERENCES,
    ASSESSMENT_REFERENCES,
    CURRICULUM_COVERAGE,
    FACTUAL_CONSISTENCY,
    MINIMUM_SCORE,
    MISCONCEPTION_REFERENCES,
    NUMERICAL_CONSISTENCY,
    OBJECTIVE_REFERENCES,
    QUESTION_REFERENCES,
    REQUIRED_GATES_PRESENT,
    RESEARCH_EVIDENCE,
)
from lpf.orchestration.state import MAX_REVISIONS
from lpf.result import Result, is_ok
from lpf.schemas.research import EvidenceMap
from lpf.validators.factual import check_factual_consistency
from lpf.validators.numerics import check_worked_example_arithmetic


@dataclass(frozen=True)
class QaBundle:
    """Everything the QA stage produces."""

    gates: tuple[QualityGate, ...]
    verification: VerificationResult


def _gate_from_result(
    ctx: RunContext,
    *,
    name: str,
    result: Result,
    location: str,
    suggested_fix: str,
) -> QualityGate:
    """Convert a validator ``Result`` into a pass/fail quality gate."""
    if is_ok(result):
        return with_content_hash(
            QualityGate(
                id=ctx.id("gate"),
                created_at=ctx.now(),
                checked_at=ctx.now(),
                gate_name=name,
                status=GateStatus.PASSED,
                score=1.0,
            )
        )

    error: ValidationError = result.error
    finding = Finding(
        severity=Severity.CRITICAL,
        location=location,
        problem=error.message,
        evidence=str(error.details),
        suggested_fix=suggested_fix,
    )
    return with_content_hash(
        QualityGate(
            id=ctx.id("gate"),
            created_at=ctx.now(),
            checked_at=ctx.now(),
            gate_name=name,
            status=GateStatus.FAILED,
            score=0.0,
            findings=[finding],
        )
    )


def _coverage_gate(
    ctx: RunContext, *, objectives: list[LearningObjective], blueprint: CurriculumBlueprint
) -> QualityGate:
    """Every objective must appear in at least one unit."""
    covered = {oid for unit in blueprint.units for oid in unit.objective_ids}
    missing = [objective.id for objective in objectives if objective.id not in covered]
    if not missing:
        return with_content_hash(
            QualityGate(
                id=ctx.id("gate"),
                created_at=ctx.now(),
                checked_at=ctx.now(),
                gate_name=CURRICULUM_COVERAGE,
                status=GateStatus.PASSED,
                score=1.0,
            )
        )
    return with_content_hash(
        QualityGate(
            id=ctx.id("gate"),
            created_at=ctx.now(),
            checked_at=ctx.now(),
            gate_name=CURRICULUM_COVERAGE,
            status=GateStatus.FAILED,
            score=0.0,
            findings=[
                Finding(
                    severity=Severity.CRITICAL,
                    location="curriculum_blueprint",
                    problem="Some objectives are not covered by any curriculum unit.",
                    evidence=f"uncovered objective ids: {missing}",
                    suggested_fix="Add a unit referencing each uncovered objective.",
                )
            ],
        )
    )


def _evidence_gate(ctx: RunContext, evidence_map: EvidenceMap, *, required: bool) -> QualityGate:
    """Check whether any claim cleared the confidence threshold.

    ``required`` comes from ``ProductSpec.constraints.evidence_required``: when a
    product declares that evidence is required, a run with no supported claims
    *fails* (the product would be ungrounded); otherwise it is a warning worth
    surfacing. Either way a zero-evidence run is never silently passed.
    """
    supported = evidence_map.supported_claims
    if supported > 0:
        status = GateStatus.PASSED
    elif required:
        status = GateStatus.FAILED
    else:
        status = GateStatus.WARNING
    findings = (
        []
        if supported > 0
        else [
            Finding(
                severity=Severity.MAJOR if not required else Severity.CRITICAL,
                location="evidence_map",
                problem=(
                    "No claim met the confidence threshold."
                    + (" Evidence is required by the product spec." if required else "")
                ),
                evidence=f"supported_claims={supported} of {evidence_map.total_claims}",
                suggested_fix="Retrieve higher-authority sources for this topic.",
            )
        ]
    )
    return with_content_hash(
        QualityGate(
            id=ctx.id("gate"),
            created_at=ctx.now(),
            checked_at=ctx.now(),
            gate_name=RESEARCH_EVIDENCE,
            status=status,
            score=float(supported),
            findings=findings,
        )
    )


def _minimum_score_gate(
    ctx: RunContext, *, gates: list[QualityGate], minimum_score: float
) -> QualityGate:
    """Fail when the share of passed gates is below the spec's floor.

    The score is the fraction of the gates built so far that passed; this gate is
    added after them so it is not counted in its own ratio. It makes
    ``QualitySpec.minimum_score`` an enforced requirement rather than a dead knob.
    """
    passed = sum(1 for gate in gates if gate.status is GateStatus.PASSED)
    score = passed / len(gates) if gates else 0.0
    if score >= minimum_score:
        return with_content_hash(
            QualityGate(
                id=ctx.id("gate"),
                created_at=ctx.now(),
                checked_at=ctx.now(),
                gate_name=MINIMUM_SCORE,
                status=GateStatus.PASSED,
                score=score,
            )
        )
    return with_content_hash(
        QualityGate(
            id=ctx.id("gate"),
            created_at=ctx.now(),
            checked_at=ctx.now(),
            gate_name=MINIMUM_SCORE,
            status=GateStatus.FAILED,
            score=score,
            findings=[
                Finding(
                    severity=Severity.CRITICAL,
                    location="verification_result",
                    problem="Too few quality gates passed for this product.",
                    evidence=f"passed {passed} of {len(gates)} ({score:.2f} < {minimum_score})",
                    suggested_fix="Fix the failing gates or lower minimum_score.",
                )
            ],
        )
    )


def _overall_status(gates: tuple[QualityGate, ...]) -> GateStatus:
    """Failed if any gate failed, warning if any warned, else passed.

    Only ``FAILED`` and ``WARNING`` roll up. ``SKIPPED`` and ``NOT_APPLICABLE``
    are treated as non-failing: a gate that does not apply to a run must not sink
    it. (The QA stage does not currently emit either, but the rollup decision is
    fixed here so a future gate can use them safely.)
    """
    statuses = {gate.status for gate in gates}
    if GateStatus.FAILED in statuses:
        return GateStatus.FAILED
    if GateStatus.WARNING in statuses:
        return GateStatus.WARNING
    return GateStatus.PASSED


def build_qa(
    ctx: RunContext,
    *,
    blueprint: CurriculumBlueprint,
    objectives: list[LearningObjective],
    lessons: list[Lesson],
    misconceptions: list[Misconception],
    questions: list[PracticeQuestion],
    answers: list[Answer],
    answer_key: AnswerKey,
    assessment: Assessment,
    evidence_map: EvidenceMap,
    worked_examples: list[WorkedExample] | None = None,
    verified_source_ids: set[str] | None = None,
    required_gates: list[str] | None = None,
    minimum_score: float | None = None,
    evidence_required: bool = True,
    iteration: int = 1,
) -> QaBundle:
    """Run every validator and assemble a VerificationResult.

    ``iteration`` records which attempt of the QA/revision cycle produced this
    result: 1 for the first pass, 2 after the first revision, and so on.
    ``minimum_score`` and ``evidence_required`` come from the product spec's
    ``QualitySpec``/``ConstraintsSpec`` so those declared requirements are
    actually enforced.
    """
    objective_ids = {objective.id for objective in objectives}
    lesson_ids = {lesson.id for lesson in lessons}
    question_ids = {question.id for question in questions}

    gate_list: list[QualityGate] = [
        _coverage_gate(ctx, objectives=objectives, blueprint=blueprint),
        _gate_from_result(
            ctx,
            name=OBJECTIVE_REFERENCES,
            result=check_objective_references(blueprint, objective_ids),
            location="curriculum_blueprint",
            suggested_fix="Reference only existing objective ids.",
        ),
        _gate_from_result(
            ctx,
            name=MISCONCEPTION_REFERENCES,
            result=check_misconception_objective_refs(misconceptions, objective_ids),
            location="misconceptions",
            suggested_fix="Reference only existing objective ids.",
        ),
        _gate_from_result(
            ctx,
            name=QUESTION_REFERENCES,
            result=check_question_references(questions, lesson_ids, objective_ids),
            location="practice_questions",
            suggested_fix="Reference only existing lesson and objective ids.",
        ),
        _gate_from_result(
            ctx,
            name=ASSESSMENT_REFERENCES,
            result=check_assessment_references(assessment, question_ids),
            location="assessment",
            suggested_fix="Reference only existing question ids.",
        ),
        _gate_from_result(
            ctx,
            name=ANSWER_REFERENCES,
            result=check_answer_references(answers, question_ids),
            location="answers",
            suggested_fix="Reference only existing question ids.",
        ),
        _gate_from_result(
            ctx,
            name=ANSWER_KEY_REFERENCES,
            result=check_answer_key_references(answer_key, question_ids),
            location="answer_key",
            suggested_fix="Every answer in the key must reference an existing question.",
        ),
        _evidence_gate(ctx, evidence_map, required=evidence_required),
        _gate_from_result(
            ctx,
            name=FACTUAL_CONSISTENCY,
            result=check_factual_consistency(lessons, evidence_map, verified_source_ids),
            location="evidence_map",
            suggested_fix=(
                "Cite only sources this run actually verified, and ground every "
                "factual claim in evidence that is not purely contradictory."
            ),
        ),
        _gate_from_result(
            ctx,
            name=NUMERICAL_CONSISTENCY,
            result=check_worked_example_arithmetic(list(worked_examples or [])),
            location="worked_examples",
            suggested_fix=(
                "Recompute each worked example: every numeric step must be "
                "arithmetically true and the final answer must agree with the steps."
            ),
        ),
    ]

    if required_gates:
        required = sorted(set(required_gates))
        present = {gate.gate_name for gate in gate_list}
        missing = [name for name in required if name not in present]
        gate_list.append(
            with_content_hash(
                QualityGate(
                    id=ctx.id("gate"),
                    created_at=ctx.now(),
                    checked_at=ctx.now(),
                    gate_name=REQUIRED_GATES_PRESENT,
                    status=GateStatus.PASSED if not missing else GateStatus.FAILED,
                    score=1.0 if not missing else 0.0,
                    findings=[]
                    if not missing
                    else [
                        Finding(
                            severity=Severity.CRITICAL,
                            location="verification_result",
                            problem="Required quality gates are missing from this run.",
                            evidence=f"missing gates: {missing}",
                            suggested_fix="Add the missing gates or relax required_gates.",
                        )
                    ],
                )
            )
        )

    if minimum_score is not None:
        gate_list.append(_minimum_score_gate(ctx, gates=gate_list, minimum_score=minimum_score))

    gates: tuple[QualityGate, ...] = tuple(gate_list)
    status = _overall_status(gates)
    passed = sum(1 for gate in gates if gate.status is GateStatus.PASSED)
    verification = with_content_hash(
        VerificationResult(
            id=ctx.id("verification"),
            created_at=ctx.now(),
            gates=list(gates),
            overall_status=status,
            overall_score=passed / len(gates),
            iteration=iteration,
            max_iterations=MAX_REVISIONS + 1,
            source_refs=[blueprint.id, assessment.id, evidence_map.id],
        )
    )
    return QaBundle(gates=gates, verification=verification)
