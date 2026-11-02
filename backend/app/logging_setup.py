"""loguru configuration: one human-readable stderr sink, level from `LOG_LEVEL`."""

from __future__ import annotations

import os
import sys

from loguru import logger


def configure_logging() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | {name}:{line} - {message}",
    )
