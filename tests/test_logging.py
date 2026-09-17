"""Tests for logging setup."""

from __future__ import annotations

import logging

from lpf.config import LpfConfig
from lpf.logging_setup import setup_logging


class TestSetupLogging:
    def test_logger_is_named_lpf(self) -> None:
        config = LpfConfig(log_level="INFO")
        setup_logging(config)
        logger = logging.getLogger("lpf")
        assert logger.name == "lpf"

    def test_respects_env_var_level(self, monkeypatch) -> None:
        monkeypatch.setenv("LPF_LOG_LEVEL", "DEBUG")
        from lpf.config import load_config

        config = load_config()
        setup_logging(config)
        logger = logging.getLogger("lpf")
        assert logger.level == logging.DEBUG
