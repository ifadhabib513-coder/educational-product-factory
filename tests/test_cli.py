"""Tests for the CLI."""

from __future__ import annotations

from pathlib import Path

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

    def test_generate_runs_pipeline(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("LPF_OUTPUT_DIR", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["generate", "Physics", "Projectile Motion", "--run-id", "cli-test"],
        )
        assert result.exit_code == 0
        assert "Run complete: cli-test" in result.output
        assert (tmp_path / "cli-test" / "manifest.json").is_file()
        assert (tmp_path / "cli-test" / "product.md").is_file()
