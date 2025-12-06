"""Tests for custom exceptions."""

import pytest

from snippy.utils.exceptions import (
    DBReverseDumpError,
    ConnectionError,
    SchemaError,
    CircularDependencyError,
    InvalidTimeframeError,
)


class TestExceptionHierarchy:
    """Tests for exception class hierarchy."""

    def test_base_exception(self):
        """Test DBReverseDumpError base exception."""
        exc = DBReverseDumpError("Test error")

        assert isinstance(exc, Exception)
        assert str(exc) == "Test error"

    def test_connection_error(self):
        """Test ConnectionError inherits from DBReverseDumpError."""
        exc = ConnectionError("Connection failed")

        assert isinstance(exc, DBReverseDumpError)
        assert isinstance(exc, Exception)
        assert str(exc) == "Connection failed"

    def test_read_only_violation_error(self):
        """Test Con inherits from DBReverseDumpError."""
        exc = ConnectionError("Read-only mode violated")

        assert isinstance(exc, DBReverseDumpError)
        assert str(exc) == "Read-only mode violated"

        assert isinstance(exc, DBReverseDumpError)
        assert str(exc) == "Schema introspection failed"

    def test_circular_dependency_error(self):
        """Test CircularDependencyError inherits from DBReverseDumpError."""
        exc = CircularDependencyError("Circular dependency detected")

        assert isinstance(exc, DBReverseDumpError)
        assert str(exc) == "Circular dependency detected"

    def test_invalid_timeframe_error(self):
        """Test InvalidTimeframeError inherits from DBReverseDumpError."""
        exc = InvalidTimeframeError("Invalid timeframe specification")

        assert isinstance(exc, DBReverseDumpError)
        assert str(exc) == "Invalid timeframe specification"


class TestExceptionInstantiation:
    """Tests for exception instantiation and messages."""

    def test_exception_with_message(self):
        """Test exception with custom message."""
        exc = DBReverseDumpError("Custom error message")

        assert str(exc) == "Custom error message"

    def test_exception_without_message(self):
        """Test exception without message."""
        exc = DBReverseDumpError()

        assert str(exc) == ""

    def test_exception_with_formatted_message(self):
        """Test exception with formatted message."""
        table_name = "users"
        exc = TableNotFoundError(f"Table '{table_name}' not found in schema 'public'")

        assert "users" in str(exc)
        assert "public" in str(exc)

    def test_exception_can_be_raised_and_caught(self):
        """Test exception can be raised and caught."""
        with pytest.raises(ConnectionError) as exc_info:
            raise ConnectionError("Test connection error")

        assert str(exc_info.value) == "Test connection error"

    def test_catch_specific_exception(self):
        """Test catching specific exception type."""
        try:
            raise TableNotFoundError("Test table error")
        except SchemaIntrospectionError as e:
            # Should be caught as SchemaIntrospectionError (parent class)
            assert "Test table error" in str(e)
        except Exception:
            pytest.fail("Should have been caught as SchemaIntrospectionError")

    def test_catch_base_exception(self):
        """Test all custom exceptions can be caught as DBReverseDumpError."""
        exceptions = [
            ConnectionError("test"),
            CircularDependencyError("test"),
            InvalidTimeframeError("test"),
        ]

        for exc in exceptions:
            try:
                raise exc
            except DBReverseDumpError:
                pass  # Successfully caught as base exception
            except Exception:
                pytest.fail(f"{type(exc).__name__} should be caught as DBReverseDumpError")
