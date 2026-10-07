"""QA stage — runs the real validators as quality gates.

Every gate delegates to an existing ``check_*`` validator or an explicit coverage
assertion, so QA cannot pass by re-testing what construction already guaranteed.
The one thing construction *does* guarantee — schema validity — is still declared
as a gate, because silently omitting it would make the gate set misleading.
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
from lpf.errors import ValidationError
from lpf.orchestration.context import RunContext
from lpf.result import Result, is_ok
from lpf.schemas.research import EvidenceMap
from lpf.validators.factual import check_factual_consistency


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
                gate_name="curriculum_coverage",
                status=GateStatus.PASSED,
                score=1.0,
            )
        )
    return with_content_hash(
        QualityGate(
            id=ctx.id("gate"),
            created_at=ctx.now(),
            checked_at=ctx.now(),
            gate_name="curriculum_coverage",
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


def _evidence_gate(ctx: RunContext, evidence_map: EvidenceMap) -> QualityGate:
    """At least one claim must clear the confidence threshold.

    A run that produces no supported claims is not a hard failure for a mock
    product, but it is a warning worth surfacing: it means the product's content
    is not backed by any evidence.
    """
    supported = evidence_map.supported_claims
    status = GateStatus.PASSED if supported > 0 else GateStatus.WARNING
    findings = (
        []
        if supported > 0
        else [
            Finding(
                severity=Severity.MAJOR,
                location="evidence_map",
                problem="No claim met the confidence threshold.",
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
            gate_name="research_evidence",
            status=status,
            score=float(supported),
            findings=findings,
        )
    )


def _overall_status(gates: tuple[QualityGate, ...]) -> GateStatus:
    """Failed if any gate failed, warning if any warned, else passed."""
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
    verified_source_ids: set[str] | None = None,
    required_gates: list[str] | None = None,
) -> QaBundle:
    """Run every validator and assemble a VerificationResult."""
    objective_ids = {objective.id for objective in objectives}
    lesson_ids = {lesson.id for lesson in lessons}
    question_ids = {question.id for question in questions}

    gate_list: list[QualityGate] = [
        with_content_hash(
            QualityGate(
                id=ctx.id("gate"),
                created_at=ctx.now(),
                checked_at=ctx.now(),
                gate_name="schema_validity",
                status=GateStatus.PASSED,
                score=1.0,
            )
        ),
        _coverage_gate(ctx, objectives=objectives, blueprint=blueprint),
        _gate_from_result(
            ctx,
            name="objective_references",
            result=check_objective_references(blueprint, objective_ids),
            location="curriculum_blueprint",
            suggested_fix="Reference only existing objective ids.",
        ),
        _gate_from_result(
            ctx,
            name="misconception_references",
            result=check_misconception_objective_refs(misconceptions, objective_ids),
            location="misconceptions",
            suggested_fix="Reference only existing objective ids.",
        ),
        _gate_from_result(
            ctx,
            name="question_references",
            result=check_question_references(questions, lesson_ids, objective_ids),
            location="practice_questions",
            suggested_fix="Reference only existing lesson and objective ids.",
        ),
        _gate_from_result(
            ctx,
            name="assessment_references",
            result=check_assessment_references(assessment, question_ids),
            location="assessment",
            suggested_fix="Reference only existing question ids.",
        ),
        _gate_from_result(
            ctx,
            name="answer_references",
            result=check_answer_references(answers, question_ids),
            location="answers",
            suggested_fix="Reference only existing question ids.",
        ),
        _gate_from_result(
            ctx,
            name="answer_key_references",
            result=check_answer_key_references(answer_key, question_ids),
            location="answer_key",
            suggested_fix="Every answer in the key must reference an existing question.",
        ),
        _evidence_gate(ctx, evidence_map),
        _gate_from_result(
            ctx,
            name="factual_consistency",
            result=check_factual_consistency(lessons, evidence_map, verified_source_ids),
            location="evidence_map",
            suggested_fix=(
                "Cite only sources this run actually verified, and ground every "
                "factual claim in evidence that is not purely contradictory."
            ),
        ),
    ]

    if required_gates:
        present = {gate.gate_name for gate in gate_list}
        missing = [name for name in required_gates if name not in present]
        gate_list.append(
            with_content_hash(
                QualityGate(
                    id=ctx.id("gate"),
                    created_at=ctx.now(),
                    checked_at=ctx.now(),
                    gate_name="required_gates_present",
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
            iteration=1,
            max_iterations=3,
            source_refs=[blueprint.id, assessment.id, evidence_map.id],
        )
    )
    return QaBundle(gates=gates, verification=verification)
