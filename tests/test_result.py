"""Tests for the Result type."""

from __future__ import annotations

import pytest

from lpf.result import (
    Err,
    Ok,
    err,
    flat_map,
    is_err,
    is_ok,
    map_err,
    map_result,
    ok,
    unwrap,
    unwrap_or,
)


class TestOk:
    def test_is_ok(self) -> None:
        assert is_ok(ok(42))

    def test_value(self) -> None:
        assert ok(42).value == 42

    def test_str(self) -> None:
        assert str(ok(42)) == "Ok(value=42)"


class TestErr:
    def test_is_err(self) -> None:
        assert is_err(err("bad"))

    def test_error(self) -> None:
        assert err("bad").error == "bad"

    def test_str(self) -> None:
        assert str(err("bad")) == "Err(error='bad')"


class TestUnwrap:
    def test_unwrap_ok(self) -> None:
        assert unwrap(ok(10)) == 10

    def test_unwrap_err_raises(self) -> None:
        with pytest.raises(ValueError, match="boom"):
            unwrap(err(ValueError("boom")))

    def test_unwrap_non_exception_error(self) -> None:
        with pytest.raises(TypeError, match="Cannot raise non-exception error"):
            unwrap(err("plain string"))


class TestUnwrapOr:
    def test_unwrap_or_ok(self) -> None:
        assert unwrap_or(ok(10), 0) == 10

    def test_unwrap_or_err(self) -> None:
        assert unwrap_or(err("x"), 0) == 0


class TestMapResult:
    def test_map_ok(self) -> None:
        result = map_result(ok(5), lambda x: x * 2)
        assert isinstance(result, Ok)
        assert result.value == 10

    def test_map_err_passthrough(self) -> None:
        result: Ok[int] | Err[str] = map_result(err("fail"), lambda x: x * 2)
        assert isinstance(result, Err)
        assert result.error == "fail"


class TestMapErr:
    def test_map_err(self) -> None:
        result = map_err(err("bad"), lambda e: f"fixed: {e}")
        assert isinstance(result, Err)
        assert result.error == "fixed: bad"

    def test_map_err_ok_passthrough(self) -> None:
        result = map_err(ok(7), lambda e: f"fixed: {e}")
        assert isinstance(result, Ok)
        assert result.value == 7


class TestFlatMap:
    def test_flat_map_ok_to_ok(self) -> None:
        result = flat_map(ok(3), lambda x: ok(x + 1))
        assert isinstance(result, Ok)
        assert result.value == 4

    def test_flat_map_ok_to_err(self) -> None:
        result = flat_map(ok(3), lambda x: err("nope"))
        assert isinstance(result, Err)
        assert result.error == "nope"

    def test_flat_map_err_passthrough(self) -> None:
        result = flat_map(err("orig"), lambda x: ok(x + 1))
        assert isinstance(result, Err)
        assert result.error == "orig"
