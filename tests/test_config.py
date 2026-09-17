"""Tests for configuration loading."""

from __future__ import annotations

from lpf.config import LpfConfig, load_config


class TestLpfConfig:
    def test_defaults(self) -> None:
        cfg = LpfConfig()
        assert cfg.log_level == "INFO"
        assert cfg.output_dir == "projects"
        assert cfg.provider == "mock"
        assert cfg.timeout_seconds == 120

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
        cfg = load_config()
        assert cfg.log_level == "DEBUG"
        assert cfg.provider == "ollama"
        assert cfg.output_dir == "out"
        assert cfg.timeout_seconds == 60
