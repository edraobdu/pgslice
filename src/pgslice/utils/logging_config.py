"""Logging configuration for pgslice."""

from __future__ import annotations

import logging
import sys


def disable_logging() -> None:
    """Disable all logging output."""
    logging.disable(logging.CRITICAL)


def setup_logging(log_level: str | None = None) -> None:
    """
    Configure logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
                   If None, logging is disabled entirely.
    """
    if log_level is None:
        disable_logging()
        return

    level = getattr(logging, log_level.upper(), logging.INFO)

    # Re-enable logging in case it was previously disabled
    logging.disable(logging.NOTSET)

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add console handler to stderr (not stdout, to avoid mixing with SQL output)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Module name (__name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
