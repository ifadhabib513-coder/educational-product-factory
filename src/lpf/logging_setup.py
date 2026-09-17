"""Logging configuration for the product factory."""

from __future__ import annotations

import logging

from lpf.config import LpfConfig


def setup_logging(config: LpfConfig) -> None:
    """Configure the 'lpf' logger from config.log_level."""
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    logger = logging.getLogger("lpf")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
        logger.addHandler(handler)
