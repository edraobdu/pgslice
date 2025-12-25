"""Tests for pgslice.utils.security module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pgslice.utils.exceptions import SecurityError
from pgslice.utils.security import SecureCredentials, SQLSanitizer


class TestSecureCredentials:
    """Tests for SecureCredentials class."""

    def test_init_with_password(self) -> None:
        """Can initialize with a password."""
        creds = SecureCredentials(password="secret123")
        assert creds.get_password() == "secret123"

    def test_init_without_password(self) -> None:
        """Can initialize without a password."""
        creds = SecureCredentials()
        assert creds._password is None

    def test_get_password_from_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should get password from PGPASSWORD environment variable."""
        monkeypatch.setenv("PGPASSWORD", "env_password")
        creds = SecureCredentials()
        assert creds.get_password() == "env_password"

    def test_get_password_prompts_when_no_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should prompt for password when env var not set."""
        monkeypatch.delenv("PGPASSWORD", raising=False)

        with patch(
            "pgslice.utils.security.getpass.getpass", return_value="prompted_password"
        ):
            creds = SecureCredentials()
            password = creds.get_password()
            assert password == "prompted_password"

    def test_get_password_caches_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Password should be cached after first retrieval."""
        monkeypatch.setenv("PGPASSWORD", "cached_password")
        creds = SecureCredentials()

        # Get password twice
        first = creds.get_password()
        # Change env var
        monkeypatch.setenv("PGPASSWORD", "new_password")
        second = creds.get_password()

        # Should still be the cached value
        assert first == second == "cached_password"

    def test_clear_removes_password(self) -> None:
        """Clear should remove password from memory."""
        creds = SecureCredentials(password="to_clear")
        assert creds.get_password() == "to_clear"

        creds.clear()
        assert creds._password is None

    def test_provided_password_takes_precedence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicitly provided password should take precedence over env var."""
        monkeypatch.setenv("PGPASSWORD", "env_password")
        creds = SecureCredentials(password="explicit_password")
        assert creds.get_password() == "explicit_password"


class TestSQLSanitizer:
    """Tests for SQLSanitizer class."""

    class TestValidateIdentifier:
        """Tests for validate_identifier method."""

        def test_valid_simple_identifier(self) -> None:
            """Should accept simple alphanumeric identifiers."""
            SQLSanitizer.validate_identifier("users")
            SQLSanitizer.validate_identifier("orders")
            SQLSanitizer.validate_identifier("test_table")

        def test_valid_identifier_with_underscore(self) -> None:
            """Should accept identifiers with underscores."""
            SQLSanitizer.validate_identifier("user_orders")
            SQLSanitizer.validate_identifier("_private")
            SQLSanitizer.validate_identifier("table__name")

        def test_valid_identifier_with_numbers(self) -> None:
            """Should accept identifiers with numbers (not at start)."""
            SQLSanitizer.validate_identifier("table1")
            SQLSanitizer.validate_identifier("orders2024")
            SQLSanitizer.validate_identifier("v2_schema")

        def test_valid_identifier_with_dollar_sign(self) -> None:
            """Should accept PostgreSQL-style identifiers with dollar sign."""
            SQLSanitizer.validate_identifier("table$1")
            SQLSanitizer.validate_identifier("func$result")

        def test_valid_identifier_starting_with_underscore(self) -> None:
            """Should accept identifiers starting with underscore."""
            SQLSanitizer.validate_identifier("_internal")
            SQLSanitizer.validate_identifier("__private")

        def test_invalid_sql_injection_attempt(self) -> None:
            """Should reject SQL injection attempts."""
            with pytest.raises(SecurityError, match="Invalid SQL identifier"):
                SQLSanitizer.validate_identifier("users; DROP TABLE users")

        def test_invalid_semicolon(self) -> None:
            """Should reject identifiers with semicolons."""
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier("table;")

        def test_invalid_quotes(self) -> None:
            """Should reject identifiers with quotes."""
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier("table'name")
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier('table"name')

        def test_invalid_parentheses(self) -> None:
            """Should reject identifiers with parentheses."""
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier("table()")
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier("func(arg)")

        def test_invalid_spaces(self) -> None:
            """Should reject identifiers with spaces."""
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier("table name")
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier(" leading")

        def test_invalid_starting_with_number(self) -> None:
            """Should reject identifiers starting with numbers."""
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier("1table")
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier("123")

        def test_invalid_special_characters(self) -> None:
            """Should reject identifiers with special characters."""
            invalid_chars = ["@", "#", "%", "^", "&", "*", "-", "+", "=", "!", "?"]
            for char in invalid_chars:
                with pytest.raises(SecurityError):
                    SQLSanitizer.validate_identifier(f"table{char}name")

        def test_invalid_unicode(self) -> None:
            """Should reject identifiers with unicode characters."""
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier("tàble")
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier("表")

        def test_invalid_empty_string(self) -> None:
            """Should reject empty identifiers."""
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier("")

    class TestQuoteIdentifier:
        """Tests for quote_identifier method."""

        def test_quotes_valid_identifier(self) -> None:
            """Should quote valid identifiers."""
            assert SQLSanitizer.quote_identifier("users") == '"users"'
            assert SQLSanitizer.quote_identifier("order_items") == '"order_items"'

        def test_raises_for_invalid_identifier(self) -> None:
            """Should raise SecurityError for invalid identifiers."""
            with pytest.raises(SecurityError):
                SQLSanitizer.quote_identifier("users; DROP TABLE")

        def test_quote_preserves_case(self) -> None:
            """Quoting should preserve identifier case."""
            assert SQLSanitizer.quote_identifier("Users") == '"Users"'
            assert SQLSanitizer.quote_identifier("USER_TABLE") == '"USER_TABLE"'

    class TestValidateSchemaTable:
        """Tests for validate_schema_table method."""

        def test_valid_schema_and_table(self) -> None:
            """Should validate both schema and table names."""
            result = SQLSanitizer.validate_schema_table("public", "users")
            assert result == ("public", "users")

        def test_valid_custom_schema(self) -> None:
            """Should validate custom schema names."""
            result = SQLSanitizer.validate_schema_table("my_schema", "orders")
            assert result == ("my_schema", "orders")

        def test_invalid_schema_raises(self) -> None:
            """Should raise for invalid schema name."""
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_schema_table("bad;schema", "users")

        def test_invalid_table_raises(self) -> None:
            """Should raise for invalid table name."""
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_schema_table("public", "bad;table")

        def test_both_invalid_raises(self) -> None:
            """Should raise if both are invalid (fails on schema first)."""
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_schema_table("bad;schema", "bad;table")


class TestSecurityIntegration:
    """Integration tests for security utilities."""

    def test_identifier_pattern_regex(self) -> None:
        """Test the regex pattern directly."""
        pattern = SQLSanitizer.IDENTIFIER_PATTERN

        # Valid matches
        assert pattern.match("users")
        assert pattern.match("_private")
        assert pattern.match("Table123")
        assert pattern.match("schema$1")

        # Invalid - no match
        assert not pattern.match("")
        assert not pattern.match("123table")
        assert not pattern.match("table-name")
        assert not pattern.match("table name")
