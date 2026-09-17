"""Result type for expected, recoverable failures.

Result[T, E] is used for expected, recoverable failures such as validation errors,
provider errors, and workflow errors. Exceptions remain appropriate for programmer
errors and truly exceptional conditions. See docs/adr/001-project-foundation.md.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")
F = TypeVar("F")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """A successful result containing a value."""

    value: T


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    """A failed result containing an error."""

    error: E


Result = Ok[T] | Err[E]


def ok(value: T) -> Ok[T]:
    """Create a successful result."""
    return Ok(value)


def err(error: E) -> Err[E]:
    """Create a failed result."""
    return Err(error)


def is_ok(result: Result[T, E]) -> bool:
    """Check if a result is Ok."""
    return isinstance(result, Ok)


def is_err(result: Result[T, E]) -> bool:
    """Check if a result is Err."""
    return isinstance(result, Err)


def unwrap(result: Result[T, E]) -> T:
    """Unwrap an Ok value or raise the Err error.

    Use only when failure is truly unexpected at this call site.
    Prefer map/map_err for recoverable pipelines.
    """
    if isinstance(result, Ok):
        return result.value
    raise result.error  # type: ignore[misc]


def unwrap_or(result: Result[T, E], default: T) -> T:
    """Unwrap an Ok value or return the default."""
    if isinstance(result, Ok):
        return result.value
    return default


def map_result(result: Result[T, E], fn: Callable[[T], U]) -> Result[U, E]:
    """Apply fn to the value inside Ok, leaving Err unchanged."""
    if isinstance(result, Ok):
        return Ok(fn(result.value))
    return result  # type: ignore[return-value]


def map_err(result: Result[T, E], fn: Callable[[E], F]) -> Result[T, F]:
    """Apply fn to the error inside Err, leaving Ok unchanged."""
    if isinstance(result, Err):
        return Err(fn(result.error))
    return result  # type: ignore[return-value]


def flat_map(result: Result[T, E], fn: Callable[[T], Result[U, E]]) -> Result[U, E]:
    """Chain a function that may also fail."""
    if isinstance(result, Ok):
        return fn(result.value)
    return result  # type: ignore[return-value]
