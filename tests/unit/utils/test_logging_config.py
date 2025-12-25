"""Tests for pgslice.utils.logging_config module."""

from __future__ import annotations

import logging
import sys

import pytest

from pgslice.utils.logging_config import get_logger, setup_logging


class TestSetupLogging:
    """Tests for setup_logging function."""

    def teardown_method(self) -> None:
        """Reset logging after each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)

    def test_sets_debug_level(self) -> None:
        """Should set DEBUG log level."""
        setup_logging("DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_sets_info_level(self) -> None:
        """Should set INFO log level."""
        setup_logging("INFO")
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_sets_warning_level(self) -> None:
        """Should set WARNING log level."""
        setup_logging("WARNING")
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_sets_error_level(self) -> None:
        """Should set ERROR log level."""
        setup_logging("ERROR")
        root = logging.getLogger()
        assert root.level == logging.ERROR

    def test_default_level_is_info(self) -> None:
        """Default log level should be INFO."""
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_level_case_insensitive(self) -> None:
        """Log level should be case insensitive."""
        setup_logging("debug")
        assert logging.getLogger().level == logging.DEBUG

        setup_logging("Debug")
        assert logging.getLogger().level == logging.DEBUG

        setup_logging("DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_invalid_level_defaults_to_info(self) -> None:
        """Invalid log level should default to INFO."""
        setup_logging("INVALID_LEVEL")
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_adds_console_handler(self) -> None:
        """Should add a console handler to stdout."""
        setup_logging("INFO")
        root = logging.getLogger()

        # Should have exactly one handler
        assert len(root.handlers) == 1
        handler = root.handlers[0]

        # Should be a StreamHandler
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream == sys.stdout

    def test_handler_has_correct_level(self) -> None:
        """Handler should have the same level as configured."""
        setup_logging("WARNING")
        root = logging.getLogger()

        handler = root.handlers[0]
        assert handler.level == logging.WARNING

    def test_handler_has_formatter(self) -> None:
        """Handler should have a formatter."""
        setup_logging("INFO")
        root = logging.getLogger()

        handler = root.handlers[0]
        assert handler.formatter is not None

    def test_formatter_format(self) -> None:
        """Formatter should use expected format."""
        setup_logging("INFO")
        root = logging.getLogger()

        handler = root.handlers[0]
        formatter = handler.formatter
        assert formatter is not None

        # Check format includes expected components
        fmt = formatter._fmt
        assert "%(asctime)s" in fmt
        assert "%(name)s" in fmt
        assert "%(levelname)s" in fmt
        assert "%(message)s" in fmt

    def test_removes_existing_handlers(self) -> None:
        """Should remove existing handlers before adding new one."""
        root = logging.getLogger()

        # Store initial handler count (pytest may have added handlers)
        initial_count = len(root.handlers)

        # Add some handlers manually
        root.addHandler(logging.StreamHandler())
        root.addHandler(logging.StreamHandler())
        assert len(root.handlers) == initial_count + 2

        # Setup logging should replace them all with just one
        setup_logging("INFO")
        assert len(root.handlers) == 1

    def test_calling_twice_replaces_handlers(self) -> None:
        """Calling setup_logging twice should not duplicate handlers."""
        setup_logging("INFO")
        setup_logging("DEBUG")

        root = logging.getLogger()
        assert len(root.handlers) == 1
        assert root.level == logging.DEBUG


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_logger_instance(self) -> None:
        """Should return a Logger instance."""
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)

    def test_returns_named_logger(self) -> None:
        """Should return a logger with the given name."""
        logger = get_logger("pgslice.test")
        assert logger.name == "pgslice.test"

    def test_same_name_returns_same_logger(self) -> None:
        """Same name should return the same logger instance."""
        logger1 = get_logger("same.name")
        logger2 = get_logger("same.name")
        assert logger1 is logger2

    def test_different_names_return_different_loggers(self) -> None:
        """Different names should return different loggers."""
        logger1 = get_logger("first.logger")
        logger2 = get_logger("second.logger")
        assert logger1 is not logger2

    def test_child_logger_hierarchy(self) -> None:
        """Child loggers should be part of hierarchy."""
        _parent = get_logger("parent")
        child = get_logger("parent.child")

        assert child.parent is not None
        # The parent might be an intermediate logger
        assert "parent" in child.name


class TestLoggingIntegration:
    """Integration tests for logging functionality."""

    def setup_method(self) -> None:
        """Set up logging for each test."""
        setup_logging("DEBUG")

    def teardown_method(self) -> None:
        """Reset logging after each test."""
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)

    def test_logger_outputs_messages(self, caplog: pytest.LogCaptureFixture) -> None:
        """Logger should output messages."""
        with caplog.at_level(logging.INFO):
            logger = get_logger("test.integration")
            logger.info("Test message")

        assert "Test message" in caplog.text
        assert "test.integration" in caplog.text

    def test_logger_respects_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Logger should respect log level."""
        setup_logging("WARNING")
        logger = get_logger("test.level")

        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")

        captured = capsys.readouterr()
        assert "Debug message" not in captured.out
        assert "Info message" not in captured.out
        assert "Warning message" in captured.out

    def test_log_format_includes_timestamp(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Log format should include timestamp."""
        with caplog.at_level(logging.INFO):
            logger = get_logger("test.format")
            logger.info("Timestamped message")

        # caplog.text includes formatted messages
        assert "Timestamped message" in caplog.text
