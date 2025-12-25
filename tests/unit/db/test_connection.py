"""Tests for pgslice.db.connection module."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import psycopg
import pytest

from pgslice.config import DatabaseConfig
from pgslice.db.connection import ConnectionManager
from pgslice.utils.exceptions import DBConnectionError, ReadOnlyEnforcementError
from pgslice.utils.security import SecureCredentials


class TestConnectionManager:
    """Tests for ConnectionManager class."""

    @pytest.fixture
    def db_config(self) -> DatabaseConfig:
        """Provide a sample database configuration."""
        return DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
        )

    @pytest.fixture
    def credentials(self) -> SecureCredentials:
        """Provide credentials with password."""
        return SecureCredentials(password="test_password")

    @pytest.fixture
    def mock_connection(self) -> MagicMock:
        """Create a mock psycopg connection."""
        conn = MagicMock(spec=psycopg.Connection)

        # Set up cursor context manager that succeeds
        cursor = MagicMock()
        cursor_cm = MagicMock()
        cursor_cm.__enter__ = MagicMock(return_value=cursor)
        cursor_cm.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor_cm

        return conn


class TestInit(TestConnectionManager):
    """Tests for ConnectionManager initialization."""

    def test_init_stores_config(
        self, db_config: DatabaseConfig, credentials: SecureCredentials
    ) -> None:
        """Should store config and credentials."""
        manager = ConnectionManager(db_config, credentials)

        assert manager.config == db_config
        assert manager.credentials == credentials

    def test_init_default_ttl(
        self, db_config: DatabaseConfig, credentials: SecureCredentials
    ) -> None:
        """Default TTL should be 30 minutes."""
        manager = ConnectionManager(db_config, credentials)

        assert manager.ttl == timedelta(minutes=30)

    def test_init_custom_ttl(
        self, db_config: DatabaseConfig, credentials: SecureCredentials
    ) -> None:
        """Can specify custom TTL."""
        manager = ConnectionManager(db_config, credentials, ttl_minutes=60)

        assert manager.ttl == timedelta(minutes=60)

    def test_init_no_connection_yet(
        self, db_config: DatabaseConfig, credentials: SecureCredentials
    ) -> None:
        """Should not create connection on init."""
        manager = ConnectionManager(db_config, credentials)

        assert manager._connection is None
        assert manager._last_used is None
        assert manager._is_read_only is False


class TestGetConnection(TestConnectionManager):
    """Tests for get_connection method."""

    def test_creates_connection_on_first_call(
        self,
        db_config: DatabaseConfig,
        credentials: SecureCredentials,
        mock_connection: MagicMock,
    ) -> None:
        """Should create connection on first call."""
        manager = ConnectionManager(db_config, credentials)

        with patch("psycopg.connect", return_value=mock_connection):
            conn = manager.get_connection()

        assert conn == mock_connection
        assert manager._connection == mock_connection
        assert manager._last_used is not None

    def test_reuses_existing_connection(
        self,
        db_config: DatabaseConfig,
        credentials: SecureCredentials,
        mock_connection: MagicMock,
    ) -> None:
        """Should reuse existing connection if not expired."""
        manager = ConnectionManager(db_config, credentials)

        with patch("psycopg.connect", return_value=mock_connection) as mock_connect:
            conn1 = manager.get_connection()
            conn2 = manager.get_connection()

        assert conn1 is conn2
        mock_connect.assert_called_once()  # Only one connection created

    def test_updates_last_used(
        self,
        db_config: DatabaseConfig,
        credentials: SecureCredentials,
        mock_connection: MagicMock,
    ) -> None:
        """Should update last_used on each call."""
        manager = ConnectionManager(db_config, credentials)

        with patch("psycopg.connect", return_value=mock_connection):
            manager.get_connection()
            first_time = manager._last_used

            manager.get_connection()
            second_time = manager._last_used

        assert second_time is not None
        assert second_time >= first_time  # type: ignore

    def test_raises_db_connection_error(
        self, db_config: DatabaseConfig, credentials: SecureCredentials
    ) -> None:
        """Should raise DBConnectionError on connection failure."""
        manager = ConnectionManager(db_config, credentials)

        with (
            patch("psycopg.connect", side_effect=psycopg.Error("Connection refused")),
            pytest.raises(DBConnectionError, match="Database connection failed"),
        ):
            manager.get_connection()

    def test_raises_read_only_enforcement_error(
        self,
        db_config: DatabaseConfig,
        credentials: SecureCredentials,
    ) -> None:
        """Should raise ReadOnlyEnforcementError if read-only can't be set."""
        manager = ConnectionManager(db_config, credentials)

        # Mock connection that fails to set read-only
        mock_conn = MagicMock(spec=psycopg.Connection)
        cursor = MagicMock()
        cursor.execute.side_effect = psycopg.Error("Permission denied")
        cursor.fetchone.return_value = ("off",)
        cursor_cm = MagicMock()
        cursor_cm.__enter__ = MagicMock(return_value=cursor)
        cursor_cm.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = cursor_cm

        with (
            patch("psycopg.connect", return_value=mock_conn),
            pytest.raises(ReadOnlyEnforcementError),
        ):
            manager.get_connection()


class TestConnectionExpiry(TestConnectionManager):
    """Tests for connection expiry handling."""

    def test_expired_connection_is_recreated(
        self,
        db_config: DatabaseConfig,
        credentials: SecureCredentials,
        mock_connection: MagicMock,
    ) -> None:
        """Should recreate connection when TTL exceeded."""
        manager = ConnectionManager(db_config, credentials, ttl_minutes=30)

        with patch("psycopg.connect", return_value=mock_connection):
            manager.get_connection()

        # Simulate expired connection
        manager._last_used = datetime.now() - timedelta(minutes=31)

        # Create new mock for second connection
        new_mock = MagicMock(spec=psycopg.Connection)
        cursor = MagicMock()
        cursor_cm = MagicMock()
        cursor_cm.__enter__ = MagicMock(return_value=cursor)
        cursor_cm.__exit__ = MagicMock(return_value=False)
        new_mock.cursor.return_value = cursor_cm

        with patch("psycopg.connect", return_value=new_mock):
            conn = manager.get_connection()

        assert conn == new_mock

    def test_is_connection_expired_no_connection(
        self, db_config: DatabaseConfig, credentials: SecureCredentials
    ) -> None:
        """No connection should not be considered expired."""
        manager = ConnectionManager(db_config, credentials)

        assert manager._is_connection_expired() is False

    def test_is_connection_expired_within_ttl(
        self,
        db_config: DatabaseConfig,
        credentials: SecureCredentials,
        mock_connection: MagicMock,
    ) -> None:
        """Connection within TTL should not be expired."""
        manager = ConnectionManager(db_config, credentials, ttl_minutes=30)

        with patch("psycopg.connect", return_value=mock_connection):
            manager.get_connection()

        assert manager._is_connection_expired() is False


class TestClose(TestConnectionManager):
    """Tests for close method."""

    def test_close_closes_connection(
        self,
        db_config: DatabaseConfig,
        credentials: SecureCredentials,
        mock_connection: MagicMock,
    ) -> None:
        """Should close the connection."""
        manager = ConnectionManager(db_config, credentials)

        with patch("psycopg.connect", return_value=mock_connection):
            manager.get_connection()

        manager.close()

        mock_connection.close.assert_called_once()
        assert manager._connection is None
        assert manager._last_used is None

    def test_close_without_connection(
        self, db_config: DatabaseConfig, credentials: SecureCredentials
    ) -> None:
        """Close without connection should not raise."""
        manager = ConnectionManager(db_config, credentials)
        manager.close()  # Should not raise


class TestContextManager(TestConnectionManager):
    """Tests for context manager protocol."""

    def test_enter_returns_self(
        self, db_config: DatabaseConfig, credentials: SecureCredentials
    ) -> None:
        """__enter__ should return the manager."""
        manager = ConnectionManager(db_config, credentials)

        with manager as ctx:
            assert ctx is manager

    def test_exit_closes_connection(
        self,
        db_config: DatabaseConfig,
        credentials: SecureCredentials,
        mock_connection: MagicMock,
    ) -> None:
        """__exit__ should close the connection."""
        manager = ConnectionManager(db_config, credentials)

        with patch("psycopg.connect", return_value=mock_connection), manager:
            manager.get_connection()

        mock_connection.close.assert_called_once()


class TestIsReadOnly(TestConnectionManager):
    """Tests for is_read_only property."""

    def test_read_only_property(
        self, db_config: DatabaseConfig, credentials: SecureCredentials
    ) -> None:
        """Should return read-only status."""
        manager = ConnectionManager(db_config, credentials)

        # Initially false
        assert manager.is_read_only is False

        # Set manually (simulating successful read-only enforcement)
        manager._is_read_only = True
        assert manager.is_read_only is True
