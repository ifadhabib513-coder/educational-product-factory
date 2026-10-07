"""Tests for the numerical quality gate (TASK-004).

Covers the evaluator's exactness and whitelist, the three defect classes the
gate reports (bad steps, contradictory steps, wrong final answers), and the
wiring that puts the gate in front of the packager.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from lpf.domain.content import SolutionStep
from lpf.domain.worked_example import WorkedExample
from lpf.orchestration import pipeline as pipeline_module
from lpf.orchestration.pipeline import FactoryPipeline
from lpf.result import is_err, is_ok, unwrap
from lpf.schemas.discovery import DiscoveryInputs
from lpf.validators.numerics import (
    _DivisionByZeroError,
    check_worked_example_arithmetic,
    evaluate_arithmetic,
    try_evaluate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _worked_example(
    expressions: list[str | None],
    final_answer: str = "42",
) -> WorkedExample:
    return WorkedExample(
        title="Solving for area",
        lesson_id="lesson_001",
        problem_statement="Find the area of a 3 by 4 rectangle.",
        solution_steps=[
            SolutionStep(
                order=index + 1,
                statement=f"Step {index + 1}.",
                expression=expression,
            )
            for index, expression in enumerate(expressions)
        ],
        final_answer=final_answer,
    )


def _errors(result: object) -> list[dict[str, str]]:
    details = getattr(result, "error", None).details  # type: ignore[union-attr]
    return details["problems"]


def _inputs() -> DiscoveryInputs:
    return DiscoveryInputs(
        request="Teach me linear algebra basics.",
        subject="linear algebra",
        level="year 10",
    )


# ---------------------------------------------------------------------------
# The evaluator: exact, and blind to anything that is not arithmetic
# ---------------------------------------------------------------------------


class TestArithmeticEvaluator:
    def test_integer_arithmetic(self) -> None:
        assert evaluate_arithmetic("2 + 3") == Fraction(5)
        assert evaluate_arithmetic("2 ** 10") == Fraction(1024)

    def test_rationals_are_exact_not_floating_point(self) -> None:
        assert evaluate_arithmetic("1/3 + 1/6") == Fraction(1, 2)
        assert evaluate_arithmetic("0.1 + 0.2") == Fraction(3, 10)

    def test_unary_minus_and_parentheses(self) -> None:
        assert evaluate_arithmetic("-(2 + 3) * 4") == Fraction(-20)

    @pytest.mark.parametrize(
        "text",
        ["apply(method, problem)", "x + 1", "2 + 3 == 5", "'5'", "5 <= 6", "True"],
    )
    def test_non_arithmetic_text_is_skipped_not_executed(self, text: str) -> None:
        assert try_evaluate(text) is None

    def test_division_by_zero_is_reported_as_undefined(self) -> None:
        with pytest.raises(_DivisionByZeroError):
            evaluate_arithmetic("1/0")
        assert try_evaluate("1/0") is None

    def test_absurd_exponents_are_not_evaluated(self) -> None:
        assert try_evaluate("2 ** 999999999") is None

    def test_fractional_exponents_are_skipped(self) -> None:
        assert try_evaluate("4 ** 0.5") is None


# ---------------------------------------------------------------------------
# Consistent examples pass
# ---------------------------------------------------------------------------


class TestConsistentExamplesPass:
    def test_correct_chain_passes(self) -> None:
        result = check_worked_example_arithmetic(
            [_worked_example(["x = 2 * 3", "area = x * 4"], "area = 24")]
        )
        assert is_ok(result)
        assert len(unwrap(result)) == 1  # type: ignore[arg-type]

    def test_true_arithmetic_equations_pass(self) -> None:
        result = check_worked_example_arithmetic([_worked_example(["2 + 3 = 5", "7 - 2 = 5"], "5")])
        assert is_ok(result)

    def test_repeated_assignment_of_the_same_value_passes(self) -> None:
        result = check_worked_example_arithmetic([_worked_example(["x = 4", "x = 2 * 2"], "x = 4")])
        assert is_ok(result)

    def test_pseudocode_and_prose_carry_no_numeric_claim(self) -> None:
        # This is exactly what the default content stage emits.
        result = check_worked_example_arithmetic(
            [
                _worked_example(
                    ["Identify what is being asked.", "result = apply(method, problem)"],
                    "The problem is solved and the result checked.",
                )
            ]
        )
        assert is_ok(result)

    def test_final_answer_written_as_an_equation_passes(self) -> None:
        result = check_worked_example_arithmetic([_worked_example(["area = 3 * 4"], "12 = 3 * 4")])
        assert is_ok(result)

    def test_steps_with_no_expression_pass(self) -> None:
        result = check_worked_example_arithmetic([_worked_example([None, None], "prose answer")])
        assert is_ok(result)

    def test_no_worked_examples_is_not_a_failure(self) -> None:
        assert is_ok(check_worked_example_arithmetic([]))


# ---------------------------------------------------------------------------
# Flawed examples are caught
# ---------------------------------------------------------------------------


class TestFlawedExamplesCaught:
    def _assert_kind(self, result: object, kind: str) -> None:
        assert is_err(result)
        assert result.error.code == "NUMERIC_INCONSISTENCY"  # type: ignore[union-attr]
        problems = _errors(result)
        assert problems, "expected at least one reported problem"
        assert any(problem["kind"] == kind for problem in problems), problems

    def test_false_arithmetic_step(self) -> None:
        result = check_worked_example_arithmetic([_worked_example(["2 + 3 = 6"], "6")])
        self._assert_kind(result, "step_mismatch")

    def test_step_that_contradicts_an_earlier_step(self) -> None:
        result = check_worked_example_arithmetic([_worked_example(["x = 4", "x = 2 * 3"], "6")])
        self._assert_kind(result, "step_contradiction")

    def test_final_answer_that_disagrees_with_a_named_step(self) -> None:
        result = check_worked_example_arithmetic([_worked_example(["area = 3 * 4"], "area = 13")])
        self._assert_kind(result, "answer_mismatch")

    def test_final_answer_that_disagrees_with_the_last_computation(self) -> None:
        result = check_worked_example_arithmetic([_worked_example(["area = 3 * 4"], "13")])
        self._assert_kind(result, "answer_mismatch")

    def test_final_equation_that_is_not_true(self) -> None:
        result = check_worked_example_arithmetic([_worked_example(["area = 3 * 4"], "14 = 3 * 4")])
        self._assert_kind(result, "answer_mismatch")

    def test_division_by_zero_in_a_step(self) -> None:
        result = check_worked_example_arithmetic([_worked_example(["x = 1 / 0"], "1")])
        self._assert_kind(result, "undefined_arithmetic")

    def test_every_flawed_example_is_reported_not_just_the_first(self) -> None:
        result = check_worked_example_arithmetic(
            [
                _worked_example(["2 + 2 = 5"], "5"),
                _worked_example(["3 + 3 = 7"], "7"),
            ]
        )
        self._assert_kind(result, "step_mismatch")
        assert len(_errors(result)) >= 2

    def test_a_flawed_example_does_not_hide_behind_a_clean_one(self) -> None:
        result = check_worked_example_arithmetic(
            [
                _worked_example(["x = 1 + 1"], "x = 2"),
                _worked_example(["y = 1 + 1"], "y = 3"),
            ]
        )
        self._assert_kind(result, "answer_mismatch")
        reported = {problem["example_id"] for problem in _errors(result)}
        assert len(reported) == 1


# ---------------------------------------------------------------------------
# The gate is wired into QA
# ---------------------------------------------------------------------------


class TestQaGateWiring:
    async def test_gate_is_present_in_a_passing_run(self, tmp_path: Path) -> None:
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(_inputs(), run_id="num-pass", seed="s")
        assert result.succeeded
        gates = {gate.gate_name: gate for gate in result.verification.gates}  # type: ignore[union-attr]
        assert "numerical_consistency" in gates
        assert gates["numerical_consistency"].status.value == "passed"

    async def test_gate_is_required_when_asked_for(self, tmp_path: Path) -> None:
        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(
            _inputs(),
            run_id="num-req",
            seed="s",
            required_gates=["numerical_consistency"],
        )
        assert result.succeeded
        names = [gate.gate_name for gate in result.verification.gates]  # type: ignore[union-attr]
        assert "numerical_consistency" in names
        assert "required_gates_present" in names

    async def test_pipeline_hands_the_gate_the_runs_worked_examples(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import lpf.orchestration.qa_stage as qa_module

        real = qa_module.check_worked_example_arithmetic
        seen: list[list[WorkedExample]] = []

        def spy(examples: list[WorkedExample]):
            seen.append(examples)
            return real(examples)

        monkeypatch.setattr(qa_module, "check_worked_example_arithmetic", spy)

        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(_inputs(), run_id="num-spy", seed="s")
        assert result.succeeded

        expected = [
            artifact for artifact in result.artifacts if artifact.artifact_type == "worked_example"
        ]
        assert expected
        assert [example.id for example in seen[0]] == [example.id for example in expected]

    async def test_a_flawed_worked_example_fails_the_run_before_packaging(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from lpf.orchestration.content_stage import ContentBundle

        original_build_content = pipeline_module.build_content

        async def with_bad_arithmetic(*args: object, **kwargs: object) -> ContentBundle:
            bundle = await original_build_content(*args, **kwargs)
            flawed = _worked_example(["2 + 3 = 6"], "2 + 3 = 5")
            return replace(bundle, worked_examples=[*bundle.worked_examples, flawed])

        monkeypatch.setattr(pipeline_module, "build_content", with_bad_arithmetic)

        pipeline = FactoryPipeline(output_dir=str(tmp_path))
        result = await pipeline.run(_inputs(), run_id="num-fail", seed="s")

        assert not result.succeeded
        assert result.package is None
        assert not (tmp_path / "num-fail").exists()
        verification = result.verification
        assert verification is not None
        failed = [gate for gate in verification.gates if gate.gate_name == "numerical_consistency"]
        assert failed and failed[0].status.value == "failed"
        finding = failed[0].findings[0]
        assert "2 + 3 = 6" in finding.evidence
