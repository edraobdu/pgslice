"""Tests for pgslice.utils.exceptions module."""

from __future__ import annotations

import pytest

from pgslice.utils.exceptions import (
    CircularDependencyError,
    ConfigurationError,
    DBConnectionError,
    DBPermissionError,
    DBReverseDumpError,
    InvalidTimeframeError,
    ReadOnlyEnforcementError,
    RecordNotFoundError,
    SchemaError,
    SecurityError,
)


class TestDBReverseDumpError:
    """Tests for base exception class."""

    def test_inherits_from_exception(self) -> None:
        """Base exception should inherit from Exception."""
        assert issubclass(DBReverseDumpError, Exception)

    def test_can_be_raised(self) -> None:
        """Base exception can be raised and caught."""
        with pytest.raises(DBReverseDumpError):
            raise DBReverseDumpError("test error")

    def test_message_is_preserved(self) -> None:
        """Exception message should be preserved."""
        error = DBReverseDumpError("test message")
        assert str(error) == "test message"


class TestDBConnectionError:
    """Tests for database connection error."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from DBReverseDumpError."""
        assert issubclass(DBConnectionError, DBReverseDumpError)

    def test_can_catch_as_base(self) -> None:
        """Should be catchable as base exception."""
        with pytest.raises(DBReverseDumpError):
            raise DBConnectionError("connection failed")

    def test_message_with_host_info(self) -> None:
        """Can include host information in message."""
        error = DBConnectionError("Failed to connect to localhost:5432")
        assert "localhost:5432" in str(error)


class TestSchemaError:
    """Tests for schema introspection error."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from DBReverseDumpError."""
        assert issubclass(SchemaError, DBReverseDumpError)

    def test_can_be_raised_with_table_info(self) -> None:
        """Can include table information."""
        error = SchemaError("Table 'users' not found")
        assert "users" in str(error)


class TestCircularDependencyError:
    """Tests for circular dependency error."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from DBReverseDumpError."""
        assert issubclass(CircularDependencyError, DBReverseDumpError)

    def test_can_include_cycle_info(self) -> None:
        """Can include cycle information in message."""
        error = CircularDependencyError("Circular dependency: users -> orders -> users")
        assert "users -> orders -> users" in str(error)


class TestSecurityError:
    """Tests for security validation error."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from DBReverseDumpError."""
        assert issubclass(SecurityError, DBReverseDumpError)

    def test_can_include_invalid_input(self) -> None:
        """Can include invalid input information."""
        error = SecurityError("Invalid identifier: 'DROP TABLE'")
        assert "DROP TABLE" in str(error)


class TestRecordNotFoundError:
    """Tests for record not found error."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from DBReverseDumpError."""
        assert issubclass(RecordNotFoundError, DBReverseDumpError)

    def test_can_include_record_info(self) -> None:
        """Can include record information."""
        error = RecordNotFoundError("Record users.42 not found")
        assert "users.42" in str(error)


class TestDBPermissionError:
    """Tests for database permission error."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from DBReverseDumpError."""
        assert issubclass(DBPermissionError, DBReverseDumpError)

    def test_can_include_permission_details(self) -> None:
        """Can include permission details."""
        error = DBPermissionError("SELECT denied on table 'secrets'")
        assert "secrets" in str(error)


class TestReadOnlyEnforcementError:
    """Tests for read-only enforcement error."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from DBReverseDumpError."""
        assert issubclass(ReadOnlyEnforcementError, DBReverseDumpError)

    def test_standard_message(self) -> None:
        """Can have standard enforcement message."""
        error = ReadOnlyEnforcementError("Cannot establish read-only connection")
        assert "read-only" in str(error).lower()


class TestInvalidTimeframeError:
    """Tests for invalid timeframe error."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from DBReverseDumpError."""
        assert issubclass(InvalidTimeframeError, DBReverseDumpError)

    def test_can_include_timeframe_details(self) -> None:
        """Can include timeframe details."""
        error = InvalidTimeframeError("Start date after end date")
        assert "date" in str(error).lower()


class TestConfigurationError:
    """Tests for configuration error."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from DBReverseDumpError."""
        assert issubclass(ConfigurationError, DBReverseDumpError)

    def test_can_include_config_details(self) -> None:
        """Can include configuration details."""
        error = ConfigurationError("Missing required config: DB_HOST")
        assert "DB_HOST" in str(error)


class TestExceptionHierarchy:
    """Tests for exception hierarchy relationships."""

    def test_all_exceptions_inherit_from_base(self) -> None:
        """All custom exceptions should inherit from base."""
        exceptions = [
            DBConnectionError,
            SchemaError,
            CircularDependencyError,
            SecurityError,
            RecordNotFoundError,
            DBPermissionError,
            ReadOnlyEnforcementError,
            InvalidTimeframeError,
            ConfigurationError,
        ]
        for exc in exceptions:
            assert issubclass(exc, DBReverseDumpError), (
                f"{exc.__name__} should inherit from DBReverseDumpError"
            )

    def test_catching_base_catches_all(self) -> None:
        """Catching base exception should catch all derived exceptions."""
        exceptions_to_test = [
            DBConnectionError("test"),
            SchemaError("test"),
            CircularDependencyError("test"),
            SecurityError("test"),
            RecordNotFoundError("test"),
            DBPermissionError("test"),
            ReadOnlyEnforcementError("test"),
            InvalidTimeframeError("test"),
            ConfigurationError("test"),
        ]

        for exc in exceptions_to_test:
            try:
                raise exc
            except DBReverseDumpError as caught:
                assert caught is exc
            else:
                pytest.fail(
                    f"{type(exc).__name__} was not caught as DBReverseDumpError"
                )
