"""loguru configuration: one human-readable stderr sink, level from the `LOG_LEVEL` setting."""

from __future__ import annotations

import sys

from loguru import logger


def configure_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level.upper(),
        format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | {name}:{line} - {message}",
    )
