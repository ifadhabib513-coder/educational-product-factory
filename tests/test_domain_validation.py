"""Tests for cross-artifact validation functions (Stage 2b-ii)."""

from __future__ import annotations

from lpf.domain.assessment import Answer, AnswerFormat, AnswerKey, Assessment, AssessmentType
from lpf.domain.curriculum import CurriculumBlueprint, CurriculumUnit
from lpf.domain.identity import with_content_hash
from lpf.domain.misconception import Misconception, MisconceptionSeverity
from lpf.domain.objectives import LearningObjective, Prerequisite
from lpf.domain.practice import DifficultyLevel, PracticeQuestion, QuestionType
from lpf.domain.quality import GateStatus, QualityGate, VerificationResult
from lpf.domain.validation import (
    check_answer_key_references,
    check_answer_references,
    check_assessment_references,
    check_misconception_objective_refs,
    check_objective_references,
    check_prerequisite_chain,
    check_quality_gate_references,
    check_question_references,
)
from lpf.result import is_err, is_ok

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_objectives() -> list[LearningObjective]:
    return [
        with_content_hash(LearningObjective(statement="Define velocity")),
        with_content_hash(LearningObjective(statement="Calculate acceleration")),
        with_content_hash(LearningObjective(statement="Analyze motion graphs")),
    ]


def _make_prerequisites(objs: list[LearningObjective]) -> list[Prerequisite]:
    return [
        Prerequisite(
            prerequisite_objective_id=objs[0].id,
            objective_id=objs[1].id,
            rationale="Must define before calculating",
        ),
        Prerequisite(
            prerequisite_objective_id=objs[1].id,
            objective_id=objs[2].id,
            rationale="Must calculate before analyzing",
        ),
    ]


def _make_blueprint(objs: list[LearningObjective]) -> CurriculumBlueprint:
    return CurriculumBlueprint(
        title="Motion Curriculum",
        units=[
            CurriculumUnit(
                unit_id="u1",
                title="Definitions",
                objective_ids=[objs[0].id],
                order=1,
            ),
            CurriculumUnit(
                unit_id="u2",
                title="Calculations",
                objective_ids=[objs[1].id],
                order=2,
            ),
            CurriculumUnit(
                unit_id="u3",
                title="Analysis",
                objective_ids=[objs[2].id],
                order=3,
            ),
        ],
    )


def _make_question(lesson_id: str, objective_ids: list[str]) -> PracticeQuestion:
    return with_content_hash(
        PracticeQuestion(
            question_type=QuestionType.NUMERICAL,
            difficulty=DifficultyLevel.INTERMEDIATE,
            lesson_id=lesson_id,
            objective_ids=objective_ids,
            stem="Calculate something",
        )
    )


def _make_assessment(question_ids: list[str]) -> Assessment:
    return with_content_hash(
        Assessment(
            assessment_type=AssessmentType.FORMATIVE,
            title="Quiz",
            question_ids=question_ids,
            total_points=10.0,
        )
    )


def _make_answer(question_id: str) -> Answer:
    return with_content_hash(
        Answer(
            question_id=question_id,
            correct_answer="42",
            answer_format=AnswerFormat.NUMERIC,
        )
    )


def _make_gate(name: str, status: GateStatus = GateStatus.PASSED) -> QualityGate:
    return with_content_hash(QualityGate(gate_name=name, status=status))


def _make_verification(gates: list[QualityGate]) -> VerificationResult:
    return with_content_hash(
        VerificationResult(
            gates=gates,
            overall_status=GateStatus.PASSED,
        )
    )


# ---------------------------------------------------------------------------
# Tests: check_question_references
# ---------------------------------------------------------------------------


class TestCheckQuestionReferences:
    def test_ok_path(self) -> None:
        q = _make_question("lesson_001", ["obj_001"])
        result = check_question_references([q], {"lesson_001"}, {"obj_001"})
        assert is_ok(result)

    def test_err_missing_lesson(self) -> None:
        q = _make_question("lesson_999", ["obj_001"])
        result = check_question_references([q], {"lesson_001"}, {"obj_001"})
        assert is_err(result)
        error = result.error  # type: ignore[union-attr]
        assert error.code == "MISSING_QUESTION_REFS"
        assert any(item.get("lesson_id") == "lesson_999" for item in error.details["missing"])

    def test_err_missing_objective(self) -> None:
        q = _make_question("lesson_001", ["obj_999"])
        result = check_question_references([q], {"lesson_001"}, {"obj_001"})
        assert is_err(result)
        error = result.error  # type: ignore[union-attr]
        assert error.code == "MISSING_QUESTION_REFS"

    def test_err_empty_objective_ids(self) -> None:
        # Use model_construct to bypass min_length=1 guard — tests belt-and-suspenders validator
        q = PracticeQuestion.model_construct(
            id="q_empty",
            artifact_type="practice_question",
            question_type=QuestionType.SHORT_ANSWER,
            difficulty=DifficultyLevel.BEGINNER,
            lesson_id="lesson_001",
            objective_ids=[],
            stem="Test",
        )
        result = check_question_references([q], {"lesson_001"}, {"obj_001"})
        assert is_err(result)

    def test_multiple_questions(self) -> None:
        q1 = _make_question("lesson_001", ["obj_001"])
        q2 = _make_question("lesson_002", ["obj_002"])
        result = check_question_references(
            [q1, q2],
            {"lesson_001", "lesson_002"},
            {"obj_001", "obj_002"},
        )
        assert is_ok(result)


# ---------------------------------------------------------------------------
# Tests: check_assessment_references
# ---------------------------------------------------------------------------


class TestCheckAssessmentReferences:
    def test_ok_path(self) -> None:
        a = _make_assessment(["q1", "q2"])
        result = check_assessment_references(a, {"q1", "q2"})
        assert is_ok(result)

    def test_err_missing_question(self) -> None:
        a = _make_assessment(["q1", "q_missing"])
        result = check_assessment_references(a, {"q1"})
        assert is_err(result)
        error = result.error  # type: ignore[union-attr]
        assert error.code == "MISSING_ASSESSMENT_REFS"
        assert any(item.get("question_id") == "q_missing" for item in error.details["missing"])

    def test_err_empty_question_ids(self) -> None:
        # Use model_construct to bypass min_length=1 guard — tests belt-and-suspenders validator
        a = Assessment.model_construct(
            id="a_empty",
            artifact_type="assessment",
            assessment_type=AssessmentType.DIAGNOSTIC,
            title="Empty",
            question_ids=[],
            total_points=0.0,
        )
        result = check_assessment_references(a, set())
        assert is_err(result)


# ---------------------------------------------------------------------------
# Tests: check_answer_references
# ---------------------------------------------------------------------------


class TestCheckAnswerReferences:
    def test_ok_path(self) -> None:
        a = _make_answer("q1")
        result = check_answer_references([a], {"q1"})
        assert is_ok(result)

    def test_err_missing_question(self) -> None:
        a = _make_answer("q_missing")
        result = check_answer_references([a], {"q1"})
        assert is_err(result)
        error = result.error  # type: ignore[union-attr]
        assert error.code == "MISSING_ANSWER_REFS"

    def test_multiple_answers(self) -> None:
        a1 = _make_answer("q1")
        a2 = _make_answer("q2")
        result = check_answer_references([a1, a2], {"q1", "q2"})
        assert is_ok(result)


# ---------------------------------------------------------------------------
# Tests: check_answer_key_references
# ---------------------------------------------------------------------------


class TestCheckAnswerKeyReferences:
    def test_ok_path(self) -> None:
        a1 = _make_answer("q1")
        a2 = _make_answer("q2")
        ak = with_content_hash(
            AnswerKey(
                assessment_id="assess_1",
                answers=[a1, a2],
                total_points=10.0,
            )
        )
        result = check_answer_key_references(ak, {"q1", "q2"})
        assert is_ok(result)

    def test_err_missing_question(self) -> None:
        a1 = _make_answer("q_missing")
        ak = with_content_hash(
            AnswerKey(
                assessment_id="assess_1",
                answers=[a1],
                total_points=5.0,
            )
        )
        result = check_answer_key_references(ak, {"q1"})
        assert is_err(result)


# ---------------------------------------------------------------------------
# Tests: check_quality_gate_references
# ---------------------------------------------------------------------------


class TestCheckQualityGateReferences:
    def test_ok_path(self) -> None:
        gates = [_make_gate("schema"), _make_gate("factual")]
        vr = _make_verification(gates)
        result = check_quality_gate_references(vr, ["schema", "factual"])
        assert is_ok(result)

    def test_err_missing_gate(self) -> None:
        gates = [_make_gate("schema")]
        vr = _make_verification(gates)
        result = check_quality_gate_references(vr, ["schema", "factual", "math"])
        assert is_err(result)
        error = result.error  # type: ignore[union-attr]
        assert error.code == "MISSING_QUALITY_GATES"
        assert "factual" in error.details["missing_gates"]
        assert "math" in error.details["missing_gates"]

    def test_empty_required_gates(self) -> None:
        gates = [_make_gate("anything")]
        vr = _make_verification(gates)
        result = check_quality_gate_references(vr, [])
        assert is_ok(result)


# ---------------------------------------------------------------------------
# Tests: check_prerequisite_chain
# ---------------------------------------------------------------------------


class TestCheckPrerequisiteChain:
    def test_ok_path(self) -> None:
        objs = _make_objectives()
        prereqs = _make_prerequisites(objs)
        result = check_prerequisite_chain(objs, prereqs)
        assert is_ok(result)

    def test_err_missing_prerequisite(self) -> None:
        objs = _make_objectives()
        prereqs = [
            Prerequisite(
                prerequisite_objective_id="bogus_id",
                objective_id=objs[0].id,
            )
        ]
        result = check_prerequisite_chain(objs, prereqs)
        assert is_err(result)
        error = result.error  # type: ignore[union-attr]
        assert error.code == "MISSING_PREREQUISITE_REFS"

    def test_err_missing_dependent(self) -> None:
        objs = _make_objectives()
        prereqs = [
            Prerequisite(
                prerequisite_objective_id=objs[0].id,
                objective_id="bogus_id",
            )
        ]
        result = check_prerequisite_chain(objs, prereqs)
        assert is_err(result)
        error = result.error  # type: ignore[union-attr]
        assert error.code == "MISSING_PREREQUISITE_REFS"

    def test_cycle_detection(self) -> None:
        objs = _make_objectives()
        # Create a cycle: obj0 -> obj1 -> obj2 -> obj0
        prereqs = [
            Prerequisite(
                prerequisite_objective_id=objs[0].id,
                objective_id=objs[1].id,
            ),
            Prerequisite(
                prerequisite_objective_id=objs[1].id,
                objective_id=objs[2].id,
            ),
            Prerequisite(
                prerequisite_objective_id=objs[2].id,
                objective_id=objs[0].id,
            ),
        ]
        result = check_prerequisite_chain(objs, prereqs)
        assert is_err(result)
        error = result.error  # type: ignore[union-attr]
        assert error.code == "PREREQUISITE_CYCLE"
        assert "cycle" in error.details

    def test_no_prerequisites(self) -> None:
        objs = _make_objectives()
        result = check_prerequisite_chain(objs, [])
        assert is_ok(result)


# ---------------------------------------------------------------------------
# Tests: check_objective_references (existing, verify still works)
# ---------------------------------------------------------------------------


class TestCheckObjectiveReferencesBackwardCompat:
    def test_ok_path(self) -> None:
        objs = _make_objectives()
        blueprint = _make_blueprint(objs)
        obj_ids = {o.id for o in objs}
        result = check_objective_references(blueprint, obj_ids)
        assert is_ok(result)

    def test_err_path(self) -> None:
        objs = _make_objectives()
        blueprint = _make_blueprint(objs)
        result = check_objective_references(blueprint, {objs[0].id})
        assert is_err(result)


# ---------------------------------------------------------------------------
# Tests: check_misconception_objective_refs (existing, verify still works)
# ---------------------------------------------------------------------------


class TestCheckMisconceptionObjectiveRefsBackwardCompat:
    def test_ok_path(self) -> None:
        objs = _make_objectives()
        m = with_content_hash(
            Misconception(
                statement="wrong",
                correction="right",
                objective_ids=[objs[0].id],
                severity=MisconceptionSeverity.COMMON,
            )
        )
        result = check_misconception_objective_refs([m], {o.id for o in objs})
        assert is_ok(result)

    def test_err_path(self) -> None:
        objs = _make_objectives()
        m = with_content_hash(
            Misconception(
                statement="wrong",
                correction="right",
                objective_ids=[objs[0].id],
            )
        )
        result = check_misconception_objective_refs([m], {"bogus"})
        assert is_err(result)
