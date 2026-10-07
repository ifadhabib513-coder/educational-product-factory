"""Numerical and symbolic consistency validators.

Worked examples are the one place a product can ship arithmetic that is
simply *wrong*. This gate re-derives every checkable numeric assertion in a
worked example with exact rational arithmetic and compares it against what
the example claims, so a step that says ``2 + 3 = 6`` or a final answer that
disagrees with the steps cannot reach a package.

Design constraints:

* **Exact, not floating point.** Values are evaluated as
  ``fractions.Fraction`` over decimal literals, so ``0.1 + 0.2`` equals
  ``0.3`` exactly and no epsilon tuning is needed.
* **No ``eval``.** Expressions are walked as an AST against a whitelist of
  arithmetic nodes; names, calls, strings and comparisons are reported as
  "not checkable" rather than executed.
* **Skip, never guess.** Pseudocode (``result = apply(method, problem)``)
  and prose answers carry no numeric claim, so they are ignored instead of
  failing. The gate only ever fails on a claim it could actually verify.
"""

from __future__ import annotations

import ast
import keyword
import math
from fractions import Fraction
from typing import Final

from lpf.domain.worked_example import WorkedExample
from lpf.errors import ValidationError
from lpf.result import Result, err, ok

#: Guard against resource exhaustion from expressions such as ``2 ** 999999999``.
_MAX_EXPONENT: Final = 1024

__all__ = [
    "check_worked_example_arithmetic",
    "evaluate_arithmetic",
    "try_evaluate",
]


class _NotArithmeticError(Exception):
    """The text is not a pure arithmetic expression."""


class _DivisionByZeroError(Exception):
    """The expression is arithmetically undefined (division by zero)."""


_BINARY_OPS: tuple[type[ast.operator], ...] = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
)


def evaluate_arithmetic(text: str) -> Fraction:
    """Evaluate ``text`` as a pure arithmetic expression.

    Returns the exact value. Raises :class:`_NotArithmeticError` when the text
    uses anything outside the arithmetic whitelist (identifiers, calls,
    comparisons, strings) and :class:`_DivisionByZeroError` when the expression is
    undefined, such as division by zero.
    """
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise _NotArithmeticError from exc
    return _evaluate_node(tree.body)


def try_evaluate(text: str) -> Fraction | None:
    """Evaluate ``text``, returning ``None`` when it is not checkable."""
    try:
        return evaluate_arithmetic(text)
    except (_NotArithmeticError, _DivisionByZeroError):
        return None


def _evaluate_node(node: ast.AST) -> Fraction:
    if isinstance(node, ast.Constant):
        return _constant(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, _BINARY_OPS):
        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)
        return _apply(node.op, left, right)
    raise _NotArithmeticError


def _constant(value: object) -> Fraction:
    if isinstance(value, bool):
        raise _NotArithmeticError
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _NotArithmeticError
        return Fraction(str(value))
    raise _NotArithmeticError


def _apply(op: ast.operator, left: Fraction, right: Fraction) -> Fraction:
    if isinstance(op, ast.Add):
        return left + right
    if isinstance(op, ast.Sub):
        return left - right
    if isinstance(op, ast.Mult):
        return left * right
    if isinstance(op, ast.Div):
        if right == 0:
            raise _DivisionByZeroError
        return left / right
    if isinstance(op, ast.FloorDiv):
        if right == 0:
            raise _DivisionByZeroError
        return Fraction(left // right, 1)
    if isinstance(op, ast.Mod):
        if right == 0:
            raise _DivisionByZeroError
        return left % right
    # ast.Pow
    if not right.denominator == 1:
        raise _NotArithmeticError
    exponent = right.numerator
    if abs(exponent) > _MAX_EXPONENT:
        raise _NotArithmeticError
    if exponent < 0 and left == 0:
        raise _DivisionByZeroError
    return left**exponent


def _is_identifier(text: str) -> bool:
    stripped = text.strip()
    return stripped.isidentifier() and not keyword.iskeyword(stripped)


def _split_assignment(text: str) -> tuple[str, str] | None:
    """Split ``lhs = rhs`` on a single ``=``.

    Returns ``None`` for comparisons (``==``, ``<=``, ``>=``, ``!=``) and
    for expressions that carry no assignment.
    """
    stripped = text.strip()
    if any(token in stripped for token in ("==", "!=", "<=", ">=")):
        return None
    if stripped.count("=") != 1:
        return None
    lhs, _, rhs = stripped.partition("=")
    if not lhs.strip() or not rhs.strip():
        return None
    return lhs.strip(), rhs.strip()


def _problem(
    example: WorkedExample,
    kind: str,
    where: str,
    detail: str,
) -> dict[str, str]:
    return {
        "example_id": example.id,
        "example_title": example.title,
        "kind": kind,
        "location": where,
        "detail": detail,
    }


def _resolve(
    example: WorkedExample,
    where: str,
    text: str,
    problems: list[dict[str, str]],
) -> Fraction | None:
    """Evaluate ``text`` or record why it could not be checked."""
    try:
        return evaluate_arithmetic(text)
    except _DivisionByZeroError:
        problems.append(
            _problem(
                example,
                "undefined_arithmetic",
                where,
                f"`{text}` is undefined (division by zero)",
            )
        )
        return None
    except _NotArithmeticError:
        return None


def _check_final_answer(
    example: WorkedExample,
    environment: dict[str, Fraction],
    last_value: Fraction | None,
    problems: list[dict[str, str]],
) -> None:
    final = (example.final_answer or "").strip()
    if not final:
        return

    assignment = _split_assignment(final)
    if assignment is None:
        value = _resolve(example, "final_answer", final, problems)
        if value is None or last_value is None:
            return
        if value != last_value:
            problems.append(
                _problem(
                    example,
                    "answer_mismatch",
                    "final_answer",
                    f"final answer `{final}` disagrees with the last computed value `{last_value}`",
                )
            )
        return

    lhs, rhs = assignment
    if _is_identifier(lhs):
        value = _resolve(example, "final_answer", rhs, problems)
        if value is None:
            return
        expected = environment.get(lhs)
        if expected is not None and expected != value:
            problems.append(
                _problem(
                    example,
                    "answer_mismatch",
                    "final_answer",
                    f"final answer sets `{lhs} = {value}` but the solution "
                    f"steps established `{lhs} = {expected}`",
                )
            )
        return

    lhs_value = _resolve(example, "final_answer", lhs, problems)
    rhs_value = _resolve(example, "final_answer", rhs, problems)
    if lhs_value is None or rhs_value is None:
        return
    if lhs_value != rhs_value:
        problems.append(
            _problem(
                example,
                "answer_mismatch",
                "final_answer",
                f"final answer `{lhs} = {rhs}` is not true: {lhs_value} != {rhs_value}",
            )
        )


def check_worked_example_arithmetic(
    examples: list[WorkedExample],
) -> Result[tuple[WorkedExample, ...], ValidationError]:
    """Verify every checkable numeric claim inside the worked examples.

    Three classes of defect are reported:

    ``step_mismatch``
        A step asserts ``lhs = rhs`` where both sides evaluate but differ.
    ``step_contradiction``
        A step reassigns a variable to a different value than an earlier
        step in the same example established.
    ``answer_mismatch``
        ``final_answer`` disagrees with the solution steps.
    ``undefined_arithmetic``
        A checkable expression divides by zero.
    """
    problems: list[dict[str, str]] = []

    for example in examples:
        environment: dict[str, Fraction] = {}
        last_value: Fraction | None = None

        for step in sorted(example.solution_steps, key=lambda item: item.order):
            text = (step.expression or "").strip()
            if not text:
                continue
            where = f"solution_steps[{step.order}].expression"

            assignment = _split_assignment(text)
            if assignment is None:
                value = _resolve(example, where, text, problems)
                if value is not None:
                    last_value = value
                continue

            lhs, rhs = assignment
            rhs_value = _resolve(example, where, rhs, problems)
            if rhs_value is None:
                continue
            last_value = rhs_value

            if _is_identifier(lhs):
                previous = environment.get(lhs)
                if previous is not None and previous != rhs_value:
                    problems.append(
                        _problem(
                            example,
                            "step_contradiction",
                            where,
                            f"`{lhs}` is set to `{rhs_value}` but an earlier "
                            f"step set it to `{previous}`",
                        )
                    )
                environment[lhs] = rhs_value
                continue

            lhs_value = _resolve(example, where, lhs, problems)
            if lhs_value is None:
                continue
            if lhs_value != rhs_value:
                problems.append(
                    _problem(
                        example,
                        "step_mismatch",
                        where,
                        f"`{text}` is false: {lhs_value} != {rhs_value}",
                    )
                )

        _check_final_answer(example, environment, last_value, problems)

    if problems:
        return err(
            ValidationError(
                code="NUMERIC_INCONSISTENCY",
                message=f"Worked examples contain {len(problems)} numeric error(s)",
                details={"problems": problems},
            )
        )
    return ok(tuple(examples))
