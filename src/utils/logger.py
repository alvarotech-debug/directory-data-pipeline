"""
Logging configuration for the directory data pipeline.

Provides a consistent logging format across all pipeline modules.
"""

import logging
import sys
from pathlib import Path


def setup_logger(
    name: str = "pipeline",
    level: str = "INFO",
    log_file: Path | None = None,
) -> logging.Logger:
    """
    Configure and return a logger instance.

    Args:
        name: Logger name (usually module or component name).
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional file path for log output.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
