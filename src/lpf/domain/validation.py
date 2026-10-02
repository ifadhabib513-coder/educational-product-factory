"""Validation functions for cross-artifact consistency."""

from __future__ import annotations

from lpf.domain.assessment import Answer, AnswerKey, Assessment
from lpf.domain.curriculum import CurriculumBlueprint
from lpf.domain.misconception import Misconception
from lpf.domain.objectives import LearningObjective, Prerequisite
from lpf.domain.practice import PracticeQuestion
from lpf.domain.quality import VerificationResult
from lpf.errors import ValidationError
from lpf.result import Result, err, ok


def _check_id_refs(
    source_id: str,
    ref_label: str,
    ids: list[str],
    known_ids: set[str],
) -> list[dict[str, str]]:
    """Check a list of IDs against known IDs; return missing entries."""
    missing: list[dict[str, str]] = []
    for obj_id in ids:
        if obj_id not in known_ids:
            missing.append({ref_label: source_id, "objective_id": obj_id})
    return missing


def _check_single_id_refs(
    source_id: str,
    ref_label: str,
    id_field: str,
    ids: list[str],
    known_ids: set[str],
    target_label: str,
) -> list[dict[str, str]]:
    """Check a list of IDs against known IDs with customizable target label."""
    missing: list[dict[str, str]] = []
    for ref_id in ids:
        if ref_id not in known_ids:
            missing.append({ref_label: source_id, target_label: ref_id})
    return missing


def check_objective_references(
    blueprint: CurriculumBlueprint,
    objective_ids: set[str],
) -> Result[CurriculumBlueprint, ValidationError]:
    """Verify that every objective_id in the blueprint resolves to a known objective.

    Also checks belt-and-suspenders: a unit with empty objective_ids is an error
    despite the min_length=1 guard on the model.
    """
    missing: list[dict[str, str]] = []

    for unit in blueprint.units:
        if not unit.objective_ids:
            missing.append({"unit_id": unit.unit_id, "objective_id": "(empty)"})
            continue
        missing.extend(_check_id_refs(unit.unit_id, "unit_id", unit.objective_ids, objective_ids))

    if missing:
        return err(
            ValidationError(
                code="MISSING_OBJECTIVE_REFS",
                message=f"Blueprint references {len(missing)} unresolvable objective(s)",
                details={"missing": missing},
            )
        )

    return ok(blueprint)


def check_misconception_objective_refs(
    misconceptions: list[Misconception],
    objective_ids: set[str],
) -> Result[list[Misconception], ValidationError]:
    """Verify that every objective_id in each misconception resolves to a known objective."""
    missing: list[dict[str, str]] = []

    for m in misconceptions:
        if not m.objective_ids:
            missing.append({"misconception_id": m.id, "objective_id": "(empty)"})
            continue
        missing.extend(_check_id_refs(m.id, "misconception_id", m.objective_ids, objective_ids))

    if missing:
        return err(
            ValidationError(
                code="MISSING_OBJECTIVE_REFS",
                message=f"Misconceptions reference {len(missing)} unresolvable objective(s)",
                details={"missing": missing},
            )
        )

    return ok(misconceptions)


def check_question_references(
    questions: list[PracticeQuestion],
    lesson_ids: set[str],
    objective_ids: set[str],
) -> Result[list[PracticeQuestion], ValidationError]:
    """Verify that every question references valid lessons and objectives."""
    missing: list[dict[str, str]] = []

    for q in questions:
        if q.lesson_id not in lesson_ids:
            missing.append({"question_id": q.id, "lesson_id": q.lesson_id})
        if not q.objective_ids:
            missing.append({"question_id": q.id, "objective_id": "(empty)"})
            continue
        missing.extend(_check_id_refs(q.id, "question_id", q.objective_ids, objective_ids))

    if missing:
        return err(
            ValidationError(
                code="MISSING_QUESTION_REFS",
                message=f"Questions reference {len(missing)} unresolvable ID(s)",
                details={"missing": missing},
            )
        )

    return ok(questions)


def check_assessment_references(
    assessment: Assessment,
    question_ids: set[str],
) -> Result[Assessment, ValidationError]:
    """Verify that every question_id in the assessment resolves to a known question."""
    missing: list[dict[str, str]] = []

    if not assessment.question_ids:
        missing.append({"assessment_id": assessment.id, "question_id": "(empty)"})
    else:
        missing.extend(
            _check_single_id_refs(
                assessment.id,
                "assessment_id",
                "question_id",
                assessment.question_ids,
                question_ids,
                "question_id",
            )
        )

    if missing:
        return err(
            ValidationError(
                code="MISSING_ASSESSMENT_REFS",
                message=f"Assessment references {len(missing)} unresolvable question(s)",
                details={"missing": missing},
            )
        )

    return ok(assessment)


def check_answer_references(
    answers: list[Answer],
    question_ids: set[str],
) -> Result[list[Answer], ValidationError]:
    """Verify that every answer references a known question."""
    missing: list[dict[str, str]] = []

    for a in answers:
        if a.question_id not in question_ids:
            missing.append({"answer_id": a.id, "question_id": a.question_id})

    if missing:
        return err(
            ValidationError(
                code="MISSING_ANSWER_REFS",
                message=f"Answers reference {len(missing)} unresolvable question(s)",
                details={"missing": missing},
            )
        )

    return ok(answers)


def check_answer_key_references(
    answer_key: AnswerKey,
    question_ids: set[str],
) -> Result[AnswerKey, ValidationError]:
    """Verify that every answer in the answer key references a known question."""
    return map_result(
        check_answer_references(answer_key.answers, question_ids),
        lambda _: answer_key,
    )


def check_quality_gate_references(
    verification: VerificationResult,
    required_gates: list[str],
) -> Result[VerificationResult, ValidationError]:
    """Verify that all required gates are present in the verification result."""
    present_gates = {gate.gate_name for gate in verification.gates}
    missing = [g for g in required_gates if g not in present_gates]

    if missing:
        return err(
            ValidationError(
                code="MISSING_QUALITY_GATES",
                message=f"Verification missing {len(missing)} required gate(s)",
                details={"missing_gates": missing},
            )
        )

    return ok(verification)


def check_prerequisite_chain(
    objectives: list[LearningObjective],
    prerequisites: list[Prerequisite],
) -> Result[list[LearningObjective], ValidationError]:
    """Verify that prerequisite relationships reference valid objectives and have no cycles."""
    objective_ids = {o.id for o in objectives}
    missing: list[dict[str, str]] = []

    for p in prerequisites:
        if p.prerequisite_objective_id not in objective_ids:
            missing.append(
                {
                    "prerequisite_id": p.prerequisite_objective_id,
                    "objective_id": p.objective_id,
                    "issue": "prerequisite not found",
                }
            )
        if p.objective_id not in objective_ids:
            missing.append(
                {
                    "prerequisite_id": p.prerequisite_objective_id,
                    "objective_id": p.objective_id,
                    "issue": "dependent objective not found",
                }
            )

    if missing:
        return err(
            ValidationError(
                code="MISSING_PREREQUISITE_REFS",
                message=f"Prerequisites reference {len(missing)} unresolvable objective(s)",
                details={"missing": missing},
            )
        )

    # Cycle detection via DFS
    adj: dict[str, list[str]] = {o.id: [] for o in objectives}
    for p in prerequisites:
        adj[p.prerequisite_objective_id].append(p.objective_id)

    white, gray, black = 0, 1, 2
    color: dict[str, int] = {o.id: white for o in objectives}

    def _dfs(node: str) -> list[str] | None:
        """Returns cycle path if found, else None."""
        color[node] = gray
        for neighbor in adj.get(node, []):
            if color[neighbor] == gray:
                return [neighbor, node]
            if color[neighbor] == white:
                result = _dfs(neighbor)
                if result is not None:
                    result.append(node)
                    return result
        color[node] = black
        return None

    for o in objectives:
        if color[o.id] == white:
            cycle = _dfs(o.id)
            if cycle is not None:
                return err(
                    ValidationError(
                        code="PREREQUISITE_CYCLE",
                        message="Prerequisite chain contains a cycle",
                        details={"cycle": cycle},
                    )
                )

    return ok(objectives)


# Re-export for convenience
from collections.abc import Callable  # noqa: E402
from typing import TypeVar  # noqa: E402

T = TypeVar("T")
F = TypeVar("F")


def map_result(
    result: Result[T, ValidationError], fn: Callable[[T], T]
) -> Result[T, ValidationError]:  # noqa: E501
    """Apply fn to the value inside Ok, leaving Err unchanged."""
    from lpf.result import Ok

    if isinstance(result, Ok):
        return Ok(fn(result.value))
    return result  # type: ignore[return-value]
