"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

from lpf.config import LpfConfig, load_config


class TestLpfConfig:
    def test_defaults(self) -> None:
        cfg = LpfConfig()
        assert cfg.log_level == "INFO"
        assert cfg.output_dir == "projects"
        assert cfg.provider == "mock"
        assert cfg.timeout_seconds == 120
        assert cfg.model_name is None
        assert cfg.model_endpoint is None
        assert cfg.api_key is None

    def test_frozen(self) -> None:
        cfg = LpfConfig()
        try:
            cfg.log_level = "DEBUG"  # type: ignore[misc]
        except AttributeError:
            return
        raise AssertionError("Expected AttributeError on frozen dataclass")


class TestLoadConfig:
    def test_load_defaults(self) -> None:
        cfg = load_config()
        assert cfg.log_level == "INFO"
        assert cfg.provider == "mock"

    def test_load_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("LPF_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LPF_PROVIDER", "ollama")
        monkeypatch.setenv("LPF_OUTPUT_DIR", "out")
        monkeypatch.setenv("LPF_TIMEOUT", "60")
        monkeypatch.setenv("LPF_MODEL_NAME", "llama3.2")
        monkeypatch.setenv("LPF_MODEL_ENDPOINT", "http://localhost:11434")
        monkeypatch.setenv("LPF_API_KEY", "secret")
        cfg = load_config()
        assert cfg.log_level == "DEBUG"
        assert cfg.provider == "ollama"
        assert cfg.output_dir == "out"
        assert cfg.timeout_seconds == 60
        assert cfg.model_name == "llama3.2"
        assert cfg.model_endpoint == "http://localhost:11434"
        assert cfg.api_key == "secret"


class TestLoadConfigFromToml:
    def _write(self, tmp_path: Path, body: str) -> Path:
        path = tmp_path / "lpf.toml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_toml_provides_model_section(self, tmp_path: Path) -> None:
        path = self._write(
            tmp_path,
            "[model]\n"
            'kind = "ollama"\n'
            'name = "llama3.2"\n'
            'endpoint = "http://localhost:11434"\n'
            'api_key = "sekret"\n',
        )
        cfg = load_config(path)
        assert cfg.provider == "ollama"
        assert cfg.model_name == "llama3.2"
        assert cfg.model_endpoint == "http://localhost:11434"
        assert cfg.api_key == "sekret"

    def test_toml_run_section_sets_tunables(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, '[run]\noutput_dir = "out"\ntimeout = 45\n')
        cfg = load_config(path)
        assert cfg.output_dir == "out"
        assert cfg.timeout_seconds == 45

    def test_env_wins_over_toml(self, tmp_path: Path, monkeypatch) -> None:
        path = self._write(tmp_path, '[model]\nkind = "ollama"\n')
        monkeypatch.setenv("LPF_PROVIDER", "openai-compatible")
        cfg = load_config(path)
        assert cfg.provider == "openai-compatible"

    def test_cli_flag_default_stays_mock_without_model_section(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, '[run]\nlog_level = "DEBUG"\n')
        cfg = load_config(path)
        assert cfg.provider == "mock"

    def test_missing_toml_is_a_no_op(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "does-not-exist.toml")
        assert cfg.provider == "mock"
        assert cfg.model_name is None

    def test_malformed_toml_is_ignored(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, "not = [valid toml\n")
        cfg = load_config(path)
        assert cfg.provider == "mock"

    def test_unknown_toml_keys_are_ignored(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, '[model]\nkind = "ollama"\nbrand_new_key = "x"\n')
        cfg = load_config(path)
        assert cfg.provider == "ollama"
