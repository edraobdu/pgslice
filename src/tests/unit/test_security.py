"""Tests for security utilities."""

import pytest
from unittest.mock import patch, MagicMock

from snippy.utils.security import SQLSanitizer, SecureCredentials
from snippy.utils.exceptions import SecurityError


class TestSQLSanitizer:
    """Tests for SQL identifier validation."""

    @pytest.mark.parametrize("identifier", [
        "users",
        "user_table",
        "table123",
        "my_table_name",
        "_private_table",
        "a",  # Single character
        "a" * 63,  # Max length (63 chars is PostgreSQL limit)
    ])
    def test_valid_identifiers(self, identifier):
        """Test valid SQL identifiers pass validation."""
        # Should not raise exception
        SQLSanitizer.validate_identifier(identifier)

    @pytest.mark.parametrize("identifier", [
        "table-name",  # Hyphens not allowed
        "table name",  # Spaces not allowed
        "table.name",  # Dots not allowed (qualified names handled separately)
        "'; DROP TABLE users--",  # SQL injection attempt
        "table; DELETE FROM users",  # SQL injection
        "1table",  # Can't start with number
        "",  # Empty string
        "user@table",  # Special characters
        "table$name",  # Dollar sign
        "table#name",  # Hash
        "table%name",  # Percent
    ])
    def test_invalid_identifiers(self, identifier):
        """Test invalid SQL identifiers raise SecurityError."""
        with pytest.raises(SecurityError):
            SQLSanitizer.validate_identifier(identifier)

    def test_none_identifier(self):
        """Test None identifier raises SecurityError."""
        with pytest.raises(SecurityError):
            SQLSanitizer.validate_identifier(None)

    def test_numeric_identifier(self):
        """Test numeric identifier raises SecurityError."""
        with pytest.raises(SecurityError):
            SQLSanitizer.validate_identifier(123)

    def test_error_message_contains_identifier(self):
        """Test error message contains the invalid identifier."""
        with pytest.raises(SecurityError) as exc_info:
            SQLSanitizer.validate_identifier("bad-table")

        assert "bad-table" in str(exc_info.value)

    def test_sql_injection_attempts(self):
        """Test SQL injection attempts are rejected."""
        injection_attempts = [
            "'; DROP TABLE users--",
            "table; DELETE FROM users;",
            "admin'--",
            "1' OR '1'='1",
            "table/**/name",
        ]

        for attempt in injection_attempts:
            with pytest.raises(SecurityError):
                SQLSanitizer.validate_identifier(attempt)

    def test_case_sensitivity(self):
        """Test identifier validation is case-insensitive."""
        # Both should be valid
        SQLSanitizer.validate_identifier("Users")
        SQLSanitizer.validate_identifier("USERS")
        SQLSanitizer.validate_identifier("users")


class TestSecureCredentials:
    """Tests for secure credential handling."""

    def test_get_password_from_env(self, monkeypatch):
        """Test getting password from PGPASSWORD environment variable."""
        monkeypatch.setenv("PGPASSWORD", "test_password")

        password = SecureCredentials.get_password()

        assert password == "test_password"

    @patch('getpass.getpass')
    def test_prompt_for_password_when_env_not_set(self, mock_getpass, monkeypatch):
        """Test prompting for password when PGPASSWORD not set."""
        # Ensure PGPASSWORD is not set
        monkeypatch.delenv("PGPASSWORD", raising=False)
        mock_getpass.return_value = "prompted_password"

        password = SecureCredentials.get_password()

        assert password == "prompted_password"
        mock_getpass.assert_called_once()

    @patch('getpass.getpass')
    def test_prompt_message(self, mock_getpass, monkeypatch):
        """Test password prompt shows correct message."""
        monkeypatch.delenv("PGPASSWORD", raising=False)
        mock_getpass.return_value = "test"

        SecureCredentials.get_password()

        # Check that getpass was called with a prompt message
        call_args = mock_getpass.call_args
        assert call_args is not None
        assert len(call_args[0]) > 0  # Has a prompt argument

    @patch('getpass.getpass')
    def test_empty_password_from_prompt(self, mock_getpass, monkeypatch):
        """Test empty password from prompt is returned as-is."""
        monkeypatch.delenv("PGPASSWORD", raising=False)
        mock_getpass.return_value = ""

        password = SecureCredentials.get_password()

        assert password == ""

    def test_env_password_takes_precedence(self, monkeypatch):
        """Test PGPASSWORD environment variable takes precedence over prompt."""
        monkeypatch.setenv("PGPASSWORD", "env_password")

        with patch('getpass.getpass') as mock_getpass:
            mock_getpass.return_value = "prompted_password"

            password = SecureCredentials.get_password()

            assert password == "env_password"
            mock_getpass.assert_not_called()  # Should not prompt

    def test_special_characters_in_password(self, monkeypatch):
        """Test passwords with special characters are handled correctly."""
        special_password = "p@ssw0rd!#$%^&*()"
        monkeypatch.setenv("PGPASSWORD", special_password)

        password = SecureCredentials.get_password()

        assert password == special_password

    @patch('getpass.getpass')
    def test_keyboard_interrupt_during_prompt(self, mock_getpass, monkeypatch):
        """Test KeyboardInterrupt during password prompt is propagated."""
        monkeypatch.delenv("PGPASSWORD", raising=False)
        mock_getpass.side_effect = KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            SecureCredentials.get_password()
