"""Database connection management with TTL and read-only enforcement."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import psycopg

from ..config import DatabaseConfig
from ..utils.exceptions import DBConnectionError, ReadOnlyEnforcementError
from ..utils.logging_config import get_logger
from ..utils.security import SecureCredentials

logger = get_logger(__name__)


class ConnectionManager:
    """Manages PostgreSQL connections with TTL and read-only enforcement."""

    def __init__(
        self,
        config: DatabaseConfig,
        credentials: SecureCredentials,
        ttl_minutes: int = 30,
    ) -> None:
        """
        Initialize connection manager.

        Always enforces read-only connections. Exits if read-only cannot be set.

        Args:
            config: Database configuration
            credentials: Secure credentials handler
            ttl_minutes: Connection time-to-live in minutes
        """
        self.config = config
        self.credentials = credentials
        self.ttl = timedelta(minutes=ttl_minutes)
        self._connection: psycopg.Connection[Any] | None = None
        self._last_used: datetime | None = None
        self._is_read_only: bool = False

    def get_connection(self) -> psycopg.Connection[Any]:
        """
        Get active connection, creating new one if needed.

        Returns:
            Active PostgreSQL connection

        Raises:
            DBConnectionError: If connection cannot be established
            ReadOnlyEnforcementError: If read-only required but not available
        """
        if self._is_connection_expired():
            self._close_connection()

        if self._connection is None:
            self._create_connection()

        self._last_used = datetime.now()
        return self._connection  # type: ignore

    def _create_connection(self) -> None:
        """
        Create new database connection with read-only enforcement.

        Raises:
            DBConnectionError: If connection fails
            ReadOnlyEnforcementError: If read-only required but not available
        """
        logger.info(
            f"Connecting to {self.config.host}:{self.config.port}/{self.config.database}"
        )

        try:
            # Create connection
            self._connection = psycopg.connect(
                host=self.config.host,
                port=self.config.port,
                dbname=self.config.database,
                user=self.config.user,
                password=self.credentials.get_password(),
                connect_timeout=10,
                autocommit=True,  # We only do SELECTs
            )

            # Try to set read-only mode
            self._is_read_only = self._try_set_read_only()

            # Enforce read-only - exit if not available
            if not self._is_read_only:
                self._close_connection()
                raise ReadOnlyEnforcementError(
                    "Cannot establish read-only connection. "
                    "Pgslice requires read-only mode for safety. "
                    "Please ensure your database user has appropriate permissions."
                )

            logger.info("Connection established (READ-ONLY mode)")

        except psycopg.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            raise DBConnectionError(f"Database connection failed: {e}") from e

    def _try_set_read_only(self) -> bool:
        """
        Attempt to set connection to read-only mode.

        Returns:
            True if read-only mode was successfully set

        Tries multiple approaches:
        1. SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY
        2. SET default_transaction_read_only = on
        3. Check if database is already read-only
        """
        if self._connection is None:
            return False

        try:
            # Method 1: Set session characteristics
            with self._connection.cursor() as cur:
                cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            logger.debug("Set read-only via SESSION CHARACTERISTICS")
            return True
        except psycopg.Error:
            logger.debug("Could not set SESSION CHARACTERISTICS to read-only")

        try:
            # Method 2: Set default transaction mode
            with self._connection.cursor() as cur:
                cur.execute("SET default_transaction_read_only = on")
            logger.debug("Set read-only via default_transaction_read_only")
            return True
        except psycopg.Error:
            logger.debug("Could not set default_transaction_read_only")

        try:
            # Method 3: Check if already read-only
            with self._connection.cursor() as cur:
                cur.execute("SHOW default_transaction_read_only")
                result = cur.fetchone()
                if result and result[0] == "on":
                    logger.debug("Database already in read-only mode")
                    return True
        except psycopg.Error:
            logger.debug("Could not check default_transaction_read_only")

        return False

    def _is_connection_expired(self) -> bool:
        """
        Check if connection has expired based on TTL.

        Returns:
            True if connection should be renewed
        """
        if self._connection is None or self._last_used is None:
            return False

        return datetime.now() - self._last_used > self.ttl

    def _close_connection(self) -> None:
        """Close existing connection."""
        if self._connection:
            logger.debug("Closing connection")
            self._connection.close()
            self._connection = None
            self._last_used = None
            self._is_read_only = False

    def close(self) -> None:
        """Explicitly close connection."""
        self._close_connection()

    @property
    def is_read_only(self) -> bool:
        """Check if current connection is read-only."""
        return self._is_read_only

    def __enter__(self) -> ConnectionManager:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - close connection."""
        self.close()
