"""Tests for the CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from lpf import __version__
from lpf.cli import main
from lpf.orchestration.model import DeterministicMockModel


def _tree(path: Path) -> list[tuple[str, bytes]]:
    """Sorted relative-path -> bytes listing, for byte-identical comparisons."""
    return sorted(
        (rel.as_posix(), item.read_bytes())
        for item in path.rglob("*")
        if item.is_file()
        for rel in [item.relative_to(path)]
    )


def _generate_ok(
    runner: CliRunner,
    *,
    output_dir: str,
    extra_args: list[str] | None = None,
) -> None:
    result = runner.invoke(
        main,
        [
            "generate",
            "Physics",
            "Projectile Motion",
            "--run-id",
            "cli-test",
            *(extra_args or []),
        ],
        env={"LPF_OUTPUT_DIR": output_dir},
    )
    assert result.exit_code == 0, result.output
    assert "Run complete: cli-test" in result.output


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

    def test_generate_options_advertised(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["generate", "--help"])
        assert result.exit_code == 0
        assert "--model" in result.output
        assert "mock" in result.output
        assert "openai-compatible" in result.output
        assert "ollama" in result.output

    def test_generate_runs_pipeline(self, tmp_path: Path) -> None:
        _generate_ok(CliRunner(), output_dir=str(tmp_path))
        assert (tmp_path / "cli-test" / "manifest.json").is_file()
        assert (tmp_path / "cli-test" / "product.md").is_file()


class TestModelSelection:
    def test_default_is_mock_and_offline(self, tmp_path: Path, monkeypatch) -> None:
        calls: list[tuple] = []
        monkeypatch.setattr("lpf.cli.create_live_model", lambda *a, **k: calls.append((a, k)))
        _generate_ok(CliRunner(), output_dir=str(tmp_path))
        assert calls == []
        assert (tmp_path / "cli-test" / "product.md").is_file()

    def test_explicit_model_mock_is_byte_identical_to_default(self, tmp_path: Path) -> None:
        default_dir = tmp_path / "default"
        explicit_dir = tmp_path / "explicit"
        default_dir.mkdir()
        explicit_dir.mkdir()
        _generate_ok(CliRunner(), output_dir=str(default_dir))
        _generate_ok(CliRunner(), output_dir=str(explicit_dir), extra_args=["--model", "mock"])
        assert _tree(default_dir / "cli-test") == _tree(explicit_dir / "cli-test")

    @pytest.mark.parametrize("kind", ["ollama", "openai-compatible"])
    def test_live_kind_wires_create_live_model(
        self, tmp_path: Path, monkeypatch, kind: str
    ) -> None:
        captured: dict = {}
        monkeypatch.setenv("LPF_MODEL_NAME", "my-model")
        monkeypatch.setenv("LPF_MODEL_ENDPOINT", "http://example.test/v1")
        monkeypatch.setenv("LPF_API_KEY", "sekret")

        def fake_create(kind_: str, **kwargs):
            captured["kind"] = kind_
            captured["kwargs"] = kwargs
            return DeterministicMockModel()

        monkeypatch.setattr("lpf.cli.create_live_model", fake_create)
        result = CliRunner().invoke(
            main,
            ["generate", "Physics", "Projectile Motion", "--run-id", "cli-test", "--model", kind],
            env={"LPF_OUTPUT_DIR": str(tmp_path)},
        )
        assert result.exit_code == 0, result.output
        assert captured["kind"] == kind
        assert captured["kwargs"]["model"] == "my-model"
        assert captured["kwargs"]["base_url"] == "http://example.test/v1"
        assert captured["kwargs"]["api_key"] == "sekret"
        assert f"Writer model: {kind} (my-model @ http://example.test/v1)" in result.output
        assert (tmp_path / "cli-test" / "product.md").is_file()

    def test_config_provider_is_used_without_the_flag(self, tmp_path: Path, monkeypatch) -> None:
        captured: dict = {}
        monkeypatch.setenv("LPF_PROVIDER", "ollama")

        def fake_create(kind_: str, **kwargs):
            captured["kind"] = kind_
            return DeterministicMockModel()

        monkeypatch.setattr("lpf.cli.create_live_model", fake_create)
        result = CliRunner().invoke(
            main,
            ["generate", "Physics", "Projectile Motion", "--run-id", "cli-test"],
            env={"LPF_OUTPUT_DIR": str(tmp_path)},
        )
        assert result.exit_code == 0, result.output
        assert captured["kind"] == "ollama"

    def test_flag_beats_config_provider(self, tmp_path: Path, monkeypatch) -> None:
        calls: list[tuple] = []
        monkeypatch.setenv("LPF_PROVIDER", "ollama")
        monkeypatch.setattr("lpf.cli.create_live_model", lambda *a, **k: calls.append((a, k)))
        _generate_ok(CliRunner(), output_dir=str(tmp_path), extra_args=["--model", "mock"])
        assert calls == []

    def test_unknown_kind_from_config_is_a_readable_error(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("LPF_PROVIDER", "claude")
        result = CliRunner().invoke(
            main,
            ["generate", "Physics", "Projectile Motion", "--run-id", "cli-test"],
            env={"LPF_OUTPUT_DIR": str(tmp_path)},
        )
        assert result.exit_code == 1
        assert "Unknown model provider kind 'claude'" in result.output

    def test_live_model_is_passed_to_the_pipeline(self, tmp_path: Path, monkeypatch) -> None:
        import lpf.cli

        fake = DeterministicMockModel()
        monkeypatch.setattr("lpf.cli.create_live_model", lambda *a, **k: fake)
        captured: dict = {}
        real_pipeline = lpf.cli.FactoryPipeline

        def spy(**kwargs):
            captured["model"] = kwargs.get("model")
            return real_pipeline(**kwargs)

        monkeypatch.setattr("lpf.cli.FactoryPipeline", spy)
        result = CliRunner().invoke(
            main,
            [
                "generate",
                "Physics",
                "Projectile Motion",
                "--run-id",
                "cli-test",
                "--model",
                "ollama",
            ],
            env={"LPF_OUTPUT_DIR": str(tmp_path)},
        )
        assert result.exit_code == 0, result.output
        assert captured["model"] is fake


class TestCliInputHygiene:
    """Bad input must fail readably, and never write outside the output dir."""

    @pytest.mark.parametrize("run_id", ["../outside", "..\\..\\evil", "a/b", "a\\b", "", ".hidden"])
    def test_rejects_a_run_id_that_could_escape_the_output_dir(
        self, tmp_path: Path, run_id: str
    ) -> None:
        result = CliRunner().invoke(
            main,
            ["generate", "Physics", "Projectile Motion", "--run-id", run_id],
            env={"LPF_OUTPUT_DIR": str(tmp_path / "out")},
        )
        assert result.exit_code == 1
        assert "Invalid run id" in result.output
        assert not (tmp_path / "outside").exists()
        assert not (tmp_path / "evil").exists()

    def test_invalid_timeout_env_is_a_readable_error(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(
            main,
            ["generate", "Physics", "Projectile Motion", "--run-id", "cli-test"],
            env={"LPF_OUTPUT_DIR": str(tmp_path), "LPF_TIMEOUT": "abc"},
        )
        assert result.exit_code == 1
        assert "LPF_TIMEOUT" in result.output

    def test_no_seed_option_is_advertised(self) -> None:
        """The dead ``--seed`` knob was removed rather than left misleading."""
        result = CliRunner().invoke(main, ["generate", "--help"])
        assert result.exit_code == 0
        assert "--seed" not in result.output


class TestCliReporting:
    """The CLI reports a failed run and echoes the wired research providers."""

    def test_a_failed_run_reports_the_stage_and_reason(self, tmp_path: Path, monkeypatch) -> None:

        class FakeStage:
            value = "qa"

        class FakeState:
            stage = FakeStage()
            failure_reason = "gate failed"

        class FakeResult:
            succeeded = False
            state = FakeState()

        class FakePipeline:
            def __init__(self, **kwargs) -> None:
                pass

            async def run(self, inputs, run_id):
                return FakeResult()

            async def aclose(self) -> None:
                pass

        monkeypatch.setattr("lpf.cli.FactoryPipeline", FakePipeline)
        result = CliRunner().invoke(
            main,
            ["generate", "Physics", "Projectile Motion", "--run-id", "cli-test"],
            env={"LPF_OUTPUT_DIR": str(tmp_path)},
        )
        assert result.exit_code == 1
        assert "Run failed at stage 'qa'." in result.output
        assert "Reason: gate failed" in result.output

    def test_live_research_wires_the_real_providers(self, tmp_path: Path, monkeypatch) -> None:
        from lpf.schemas.research import SearchProvider

        captured: dict = {}

        class FakeResult:
            run_id = "cli-test"
            succeeded = True
            artifacts: list = []
            verification = None
            package = None

        class FakePipeline:
            def __init__(self, **kwargs) -> None:
                captured.update(kwargs)

            async def run(self, inputs, run_id):
                return FakeResult()

            async def aclose(self) -> None:
                pass

        monkeypatch.setattr("lpf.cli.FactoryPipeline", FakePipeline)
        result = CliRunner().invoke(
            main,
            [
                "generate",
                "Physics",
                "Projectile Motion",
                "--run-id",
                "cli-test",
                "--live-research",
            ],
            env={"LPF_OUTPUT_DIR": str(tmp_path)},
        )
        assert result.exit_code == 0, result.output
        providers = captured["research_providers"]
        assert set(providers) == {SearchProvider.ARXIV, SearchProvider.WIKIMEDIA}
        assert "Research providers: arxiv, wikimedia" in result.output


class TestCliAsyncCleanup:
    """The CLI's single event loop must close all resources without RuntimeError."""

    def test_cli_runs_and_closes_without_event_loop_error(self, tmp_path: Path) -> None:
        """Exercise the full async CLI path (run + aclose) with mock provider.

        This would previously raise 'RuntimeError: Event loop is closed'
        because asyncio.run() was called twice, creating two separate loops.
        """
        result = CliRunner().invoke(
            main,
            [
                "generate",
                "Physics",
                "Projectile Motion",
                "--run-id",
                "cli-cleanup",
                "--model",
                "mock",
            ],
            env={"LPF_OUTPUT_DIR": str(tmp_path)},
        )
        assert result.exit_code == 0, result.output
        assert "Run complete: cli-cleanup" in result.output
        assert "RuntimeError" not in result.output
        assert "Event loop is closed" not in result.output

    def test_cli_live_research_closes_without_event_loop_error(self, tmp_path: Path, monkeypatch) -> None:
        """Exercise live research path with mocked providers."""

        class FakeResult:
            run_id = "cli-cleanup-live"
            succeeded = True
            artifacts: list = []
            verification = None
            package = None

        class FakePipeline:
            def __init__(self, **kwargs) -> None:
                pass

            async def run(self, inputs, run_id):
                return FakeResult()

            async def aclose(self) -> None:
                pass

        monkeypatch.setattr("lpf.cli.FactoryPipeline", FakePipeline)
        result = CliRunner().invoke(
            main,
            [
                "generate",
                "Physics",
                "Projectile Motion",
                "--run-id",
                "cli-cleanup-live",
                "--live-research",
            ],
            env={"LPF_OUTPUT_DIR": str(tmp_path)},
        )
        assert result.exit_code == 0, result.output
        assert "Run complete: cli-cleanup-live" in result.output
        assert "RuntimeError" not in result.output
        assert "Event loop is closed" not in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
