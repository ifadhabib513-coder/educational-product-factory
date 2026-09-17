"""Tests for the CLI."""

from __future__ import annotations

from click.testing import CliRunner

from lpf import __version__
from lpf.cli import main


class TestCli:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "AI Educational Product Factory" in result.output

    def test_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_generate_not_implemented(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["generate", "Physics", "Projectile Motion"])
        assert result.exit_code == 0
        assert "Not yet implemented" in result.output
