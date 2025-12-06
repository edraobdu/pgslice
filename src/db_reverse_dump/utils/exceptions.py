"""Custom exceptions for db_reverse_dump."""


class DBReverseDumpError(Exception):
    """Base exception for db_reverse_dump."""

    pass


class ConnectionError(DBReverseDumpError):
    """Database connection error."""

    pass


class SchemaError(DBReverseDumpError):
    """Schema introspection error."""

    pass


class CircularDependencyError(DBReverseDumpError):
    """Circular dependency detected in record relationships."""

    pass


class SecurityError(DBReverseDumpError):
    """Security validation error (e.g., SQL injection attempt)."""

    pass


class RecordNotFoundError(DBReverseDumpError):
    """Requested record not found in database."""

    pass


class PermissionError(DBReverseDumpError):
    """Database permission denied."""

    pass


class ReadOnlyEnforcementError(DBReverseDumpError):
    """Read-only connection required but not available."""

    pass


class InvalidTimeframeError(DBReverseDumpError):
    """Invalid timeframe filter specification."""

    pass


class ConfigurationError(DBReverseDumpError):
    """Configuration error."""

    pass
