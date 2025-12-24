"""Security utilities for password handling and SQL sanitization."""

from __future__ import annotations

import getpass
import os
import re

from .exceptions import SecurityError


class SecureCredentials:
    """Secure password handling with memory cleanup."""

    def __init__(self, password: str | None = None) -> None:
        """Initialize with optional password."""
        self._password = password

    def get_password(self) -> str:
        """
        Get password, checking environment variable first before prompting.

        Checks PGPASSWORD environment variable (standard PostgreSQL convention).
        If not found, prompts user for password.
        """
        if self._password is None:
            # Check PGPASSWORD environment variable (PostgreSQL standard)
            env_password = os.getenv("PGPASSWORD")
            if env_password:
                self._password = env_password
            else:
                self._password = getpass.getpass("Database password: ")
        return self._password

    def clear(self) -> None:
        """Clear password from memory."""
        self._password = None


class SQLSanitizer:
    """SQL injection prevention utilities."""

    # Pattern for valid SQL identifiers (table/column names)
    # Allows alphanumeric, underscore, and dollar sign (PostgreSQL specific)
    IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_$]*$")

    @classmethod
    def validate_identifier(cls, identifier: str) -> None:
        """
        Validate SQL identifier to prevent injection.

        Args:
            identifier: Table name, column name, or schema name

        Raises:
            SecurityError: If identifier contains invalid characters
        """
        if not cls.IDENTIFIER_PATTERN.match(identifier):
            raise SecurityError(
                f"Invalid SQL identifier: '{identifier}'. "
                "Only alphanumeric characters, underscores, and dollar signs allowed."
            )

    @classmethod
    def quote_identifier(cls, identifier: str) -> str:
        """
        Quote SQL identifier safely.

        Args:
            identifier: SQL identifier to quote

        Returns:
            Quoted identifier

        Raises:
            SecurityError: If identifier is invalid
        """
        cls.validate_identifier(identifier)
        return f'"{identifier}"'

    @classmethod
    def validate_schema_table(cls, schema: str, table: str) -> tuple[str, str]:
        """
        Validate both schema and table names.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            Tuple of (schema, table) if valid

        Raises:
            SecurityError: If either name is invalid
        """
        cls.validate_identifier(schema)
        cls.validate_identifier(table)
        return schema, table
