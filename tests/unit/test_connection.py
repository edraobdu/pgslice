"""Tests for connection management (with mocks)."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from freezegun import freeze_time

from snippy.db.connection import ConnectionManager
from snippy.config import DatabaseConfig
from snippy.utils.exceptions import ConnectionError, ReadOnlyViolationError


class TestConnectionManagerCreation:
    """Tests for ConnectionManager creation."""

    def test_init(self, test_db_config):
        """Test ConnectionManager initialization."""
        manager = ConnectionManager(test_db_config, ttl_minutes=30)

        assert manager.config == test_db_config
        assert manager.ttl_minutes == 30

    def test_default_ttl(self, test_db_config):
        """Test default TTL value."""
        manager = ConnectionManager(test_db_config)

        assert manager.ttl_minutes == 30  # Default value


class TestConnectionManagerConnectionLifecycle:
    """Tests for connection creation and reuse."""

    @patch('psycopg.connect')
    def test_get_connection_creates_new(self, mock_connect, test_db_config):
        """Test get_connection creates new connection if none exists."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        manager = ConnectionManager(test_db_config)
        conn = manager.get_connection()

        assert conn == mock_conn
        mock_connect.assert_called_once()

    @patch('psycopg.connect')
    def test_get_connection_reuses_within_ttl(self, mock_connect, test_db_config):
        """Test get_connection reuses connection within TTL."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        manager = ConnectionManager(test_db_config, ttl_minutes=5)

        # First call creates connection
        with freeze_time("2024-01-01 10:00:00"):
            conn1 = manager.get_connection()

        # Second call within TTL reuses connection
        with freeze_time("2024-01-01 10:03:00"):
            conn2 = manager.get_connection()

        assert conn1 == conn2
        mock_connect.assert_called_once()  # Only called once

    @patch('psycopg.connect')
    def test_get_connection_recreates_after_ttl(self, mock_connect, test_db_config):
        """Test get_connection creates new connection after TTL expires."""
        mock_conn1 = Mock()
        mock_conn2 = Mock()
        mock_connect.side_effect = [mock_conn1, mock_conn2]

        manager = ConnectionManager(test_db_config, ttl_minutes=5)

        # First call creates connection
        with freeze_time("2024-01-01 10:00:00"):
            conn1 = manager.get_connection()

        # Second call after TTL creates new connection
        with freeze_time("2024-01-01 10:06:00"):
            conn2 = manager.get_connection()

        assert conn1 != conn2
        assert mock_connect.call_count == 2

    @patch('psycopg.connect')
    def test_connection_error_handling(self, mock_connect, test_db_config):
        """Test connection error is wrapped in custom exception."""
        import psycopg
        mock_connect.side_effect = psycopg.OperationalError("Connection failed")

        manager = ConnectionManager(test_db_config)

        with pytest.raises(ConnectionError) as exc_info:
            manager.get_connection()

        assert "Connection failed" in str(exc_info.value)


class TestConnectionManagerReadOnly:
    """Tests for read-only mode detection and enforcement."""

    @patch('psycopg.connect')
    def test_detect_read_only_true(self, mock_connect, test_db_config):
        """Test detecting read-only connection."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Simulate read-only responses
        mock_cursor.fetchone.side_effect = [
            (True,),  # transaction_read_only check
        ]
        mock_connect.return_value = mock_conn

        manager = ConnectionManager(test_db_config)
        is_readonly = manager._detect_read_only(mock_conn)

        assert is_readonly is True

    @patch('psycopg.connect')
    def test_detect_read_only_false(self, mock_connect, test_db_config):
        """Test detecting read-write connection."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Simulate read-write responses
        mock_cursor.fetchone.side_effect = [
            (False,),  # transaction_read_only check
        ]
        mock_connect.return_value = mock_conn

        manager = ConnectionManager(test_db_config)
        is_readonly = manager._detect_read_only(mock_conn)

        assert is_readonly is False

    @patch('psycopg.connect')
    def test_detect_read_only_fallback_methods(self, mock_connect, test_db_config):
        """Test read-only detection uses fallback methods if first fails."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # First method fails, second succeeds
        mock_cursor.fetchone.side_effect = [
            None,  # First check returns None
            ('on',),  # default_transaction_read_only = on
        ]
        mock_connect.return_value = mock_conn

        manager = ConnectionManager(test_db_config)
        is_readonly = manager._detect_read_only(mock_conn)

        # Should detect as read-only via fallback
        assert is_readonly is True


class TestConnectionManagerRequireReadOnly:
    """Tests for read-only requirement enforcement."""

    @patch('psycopg.connect')
    @patch('snippy.db.connection.click.confirm')
    def test_require_read_only_accepts_readonly(self, mock_confirm, mock_connect, test_db_config):
        """Test read-only requirement accepts read-only connection."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (True,)  # Read-only
        mock_connect.return_value = mock_conn

        test_db_config_ro = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
        )

        manager = ConnectionManager(test_db_config_ro, ttl_minutes=30, require_read_only=True)
        conn = manager.get_connection()

        assert conn == mock_conn
        mock_confirm.assert_not_called()  # Should not prompt

    @patch('psycopg.connect')
    @patch('snippy.db.connection.click.confirm')
    def test_require_read_only_rejects_readwrite_user_cancels(
        self, mock_confirm, mock_connect, test_db_config
    ):
        """Test read-only requirement rejects read-write if user cancels."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (False,)  # Read-write
        mock_connect.return_value = mock_conn
        mock_confirm.return_value = False  # User cancels

        manager = ConnectionManager(test_db_config, ttl_minutes=30, require_read_only=True)

        with pytest.raises(ReadOnlyViolationError):
            manager.get_connection()

    @patch('psycopg.connect')
    @patch('snippy.db.connection.click.confirm')
    def test_require_read_only_allows_readwrite_with_override(
        self, mock_confirm, mock_connect, test_db_config
    ):
        """Test read-only requirement can be overridden if user confirms."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (False,)  # Read-write
        mock_connect.return_value = mock_conn
        mock_confirm.return_value = True  # User confirms

        manager = ConnectionManager(
            test_db_config,
            ttl_minutes=30,
            require_read_only=True,
            allow_write_override=True,
        )
        conn = manager.get_connection()

        assert conn == mock_conn
        mock_confirm.assert_called_once()


class TestConnectionManagerContextManager:
    """Tests for context manager protocol."""

    @patch('psycopg.connect')
    def test_context_manager_enter_exit(self, mock_connect, test_db_config):
        """Test ConnectionManager works as context manager."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        manager = ConnectionManager(test_db_config)

        with manager as conn:
            assert conn == mock_conn

    @patch('psycopg.connect')
    def test_context_manager_closes_connection_on_exit(self, mock_connect, test_db_config):
        """Test context manager closes connection on exit."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        manager = ConnectionManager(test_db_config)

        with manager:
            pass

        mock_conn.close.assert_called_once()

    @patch('psycopg.connect')
    def test_context_manager_closes_on_exception(self, mock_connect, test_db_config):
        """Test context manager closes connection even if exception occurs."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        manager = ConnectionManager(test_db_config)

        with pytest.raises(ValueError):
            with manager:
                raise ValueError("Test error")

        mock_conn.close.assert_called_once()
