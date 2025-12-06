"""End-to-end tests for CLI."""

import pytest
import sys
from unittest.mock import patch, Mock
from pathlib import Path

from snippy.cli import main
from snippy.utils.exceptions import ConnectionError


class TestCLIArgumentParsing:
    """Tests for CLI argument parsing."""

    def test_help_flag(self):
        """Test --help flag displays help."""
        with patch.object(sys, 'argv', ['snippy', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                main()

            # --help should exit with code 0
            assert exc_info.value.code == 0

    def test_version_flag(self):
        """Test --version flag displays version."""
        with patch.object(sys, 'argv', ['snippy', '--version']):
            with pytest.raises(SystemExit) as exc_info:
                main()

            # --version should exit with code 0
            assert exc_info.value.code == 0


class TestCLIClearCache:
    """Tests for --clear-cache command."""

    @patch('snippy.cli.SchemaCache')
    @patch('snippy.cli.load_config')
    def test_clear_cache_command(self, mock_load_config, mock_schema_cache):
        """Test --clear-cache clears cache and exits."""
        # Mock config
        mock_config = Mock()
        mock_config.cache.enabled = True
        mock_config.cache.cache_dir = Path("/tmp/cache")
        mock_config.db.host = "localhost"
        mock_config.db.database = "test_db"
        mock_load_config.return_value = mock_config

        # Mock cache
        mock_cache_instance = Mock()
        mock_schema_cache.return_value = mock_cache_instance

        with patch.object(sys, 'argv', ['snippy', '--clear-cache']):
            exit_code = main()

            # Should clear cache
            mock_cache_instance.invalidate_cache.assert_called_once()
            # Should exit with success
            assert exit_code == 0

    @patch('snippy.cli.load_config')
    def test_clear_cache_when_disabled(self, mock_load_config):
        """Test --clear-cache when cache is disabled."""
        # Mock config with cache disabled
        mock_config = Mock()
        mock_config.cache.enabled = False
        mock_load_config.return_value = mock_config

        with patch.object(sys, 'argv', ['snippy', '--clear-cache']):
            exit_code = main()

            # Should exit gracefully
            assert exit_code == 0


class TestCLIREPLMode:
    """Tests for --repl mode."""

    @patch('snippy.cli.REPL')
    @patch('snippy.cli.ConnectionManager')
    @patch('snippy.cli.SecureCredentials')
    @patch('snippy.cli.load_config')
    def test_repl_mode_starts_repl(
        self, mock_load_config, mock_credentials, mock_conn_manager, mock_repl
    ):
        """Test --repl flag starts REPL."""
        # Mock config
        mock_config = Mock()
        mock_config.db.host = "localhost"
        mock_config.db.port = 5432
        mock_config.db.database = "test_db"
        mock_config.db.user = "test_user"
        mock_config.db.schema = "public"
        mock_config.connection_ttl_minutes = 30
        mock_config.require_read_only = False
        mock_config.allow_write_connection = False
        mock_config.log_level = "INFO"
        mock_load_config.return_value = mock_config

        # Mock password
        mock_credentials.get_password.return_value = "test_pass"

        # Mock REPL
        mock_repl_instance = Mock()
        mock_repl.return_value = mock_repl_instance

        with patch.object(sys, 'argv', ['snippy', '--repl', '--host', 'localhost', '--database', 'test_db', '--user', 'test_user']):
            exit_code = main()

            # Should start REPL
            mock_repl_instance.start.assert_called_once()
            # Should exit with success
            assert exit_code == 0

    @patch('snippy.cli.ConnectionManager')
    @patch('snippy.cli.SecureCredentials')
    @patch('snippy.cli.load_config')
    def test_repl_keyboard_interrupt(
        self, mock_load_config, mock_credentials, mock_conn_manager
    ):
        """Test REPL handles KeyboardInterrupt gracefully."""
        # Mock config
        mock_config = Mock()
        mock_config.db.host = "localhost"
        mock_config.db.port = 5432
        mock_config.db.database = "test_db"
        mock_config.db.user = "test_user"
        mock_config.db.schema = "public"
        mock_config.connection_ttl_minutes = 30
        mock_config.require_read_only = False
        mock_config.allow_write_connection = False
        mock_config.log_level = "INFO"
        mock_config.cache.enabled = False
        mock_load_config.return_value = mock_config

        # Mock password
        mock_credentials.get_password.return_value = "test_pass"

        # Mock REPL to raise KeyboardInterrupt
        with patch('snippy.cli.REPL') as mock_repl:
            mock_repl_instance = Mock()
            mock_repl_instance.start.side_effect = KeyboardInterrupt()
            mock_repl.return_value = mock_repl_instance

            with patch.object(sys, 'argv', ['snippy', '--repl', '--host', 'localhost', '--database', 'test_db', '--user', 'test_user']):
                exit_code = main()

                # Should exit gracefully with code 0
                assert exit_code == 0


class TestCLIConnectionSetup:
    """Tests for database connection setup."""

    @patch('snippy.cli.ConnectionManager')
    @patch('snippy.cli.SecureCredentials')
    @patch('snippy.cli.load_config')
    def test_connection_with_cli_overrides(
        self, mock_load_config, mock_credentials, mock_conn_manager
    ):
        """Test CLI arguments override config values."""
        # Mock config with defaults
        mock_config = Mock()
        mock_config.db.host = "default_host"
        mock_config.db.port = 5432
        mock_config.db.database = "default_db"
        mock_config.db.user = "default_user"
        mock_config.db.schema = "public"
        mock_config.connection_ttl_minutes = 30
        mock_config.require_read_only = False
        mock_config.allow_write_connection = False
        mock_config.log_level = "INFO"
        mock_config.cache.enabled = False
        mock_load_config.return_value = mock_config

        # Mock password
        mock_credentials.get_password.return_value = "test_pass"

        # Mock REPL
        with patch('snippy.cli.REPL') as mock_repl:
            mock_repl_instance = Mock()
            mock_repl.return_value = mock_repl_instance

            with patch.object(sys, 'argv', [
                'snippy', '--repl',
                '--host', 'override_host',
                '--port', '5433',
                '--database', 'override_db',
                '--user', 'override_user',
            ]):
                main()

                # Should create connection manager with overridden values
                call_args = mock_conn_manager.call_args
                db_config = call_args[0][0]

                assert db_config.host == 'override_host'
                assert db_config.port == 5433
                assert db_config.database == 'override_db'
                assert db_config.user == 'override_user'

    @patch('snippy.cli.SecureCredentials')
    @patch('snippy.cli.load_config')
    def test_connection_error_handling(self, mock_load_config, mock_credentials):
        """Test connection errors are handled gracefully."""
        # Mock config
        mock_config = Mock()
        mock_config.db.host = "invalid_host"
        mock_config.db.port = 5432
        mock_config.db.database = "test_db"
        mock_config.db.user = "test_user"
        mock_config.db.schema = "public"
        mock_config.connection_ttl_minutes = 30
        mock_config.require_read_only = False
        mock_config.allow_write_connection = False
        mock_config.log_level = "INFO"
        mock_config.cache.enabled = False
        mock_load_config.return_value = mock_config

        # Mock password
        mock_credentials.get_password.return_value = "test_pass"

        # Mock ConnectionManager to raise error
        with patch('snippy.cli.ConnectionManager') as mock_conn_manager:
            mock_conn_manager.side_effect = ConnectionError("Connection failed")

            with patch.object(sys, 'argv', ['snippy', '--repl', '--host', 'invalid_host', '--database', 'test_db', '--user', 'test_user']):
                exit_code = main()

                # Should exit with error code
                assert exit_code != 0


class TestCLILogging:
    """Tests for logging setup."""

    @patch('snippy.cli.setup_logging')
    @patch('snippy.cli.load_config')
    def test_logging_setup_with_default_level(self, mock_load_config, mock_setup_logging):
        """Test logging is set up with default level."""
        # Mock config
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_config.cache.enabled = False
        mock_load_config.return_value = mock_config

        with patch.object(sys, 'argv', ['snippy', '--clear-cache']):
            main()

            # Should set up logging with INFO level
            mock_setup_logging.assert_called_once_with("INFO")

    @patch('snippy.cli.setup_logging')
    @patch('snippy.cli.load_config')
    def test_logging_setup_with_custom_level(self, mock_load_config, mock_setup_logging):
        """Test logging is set up with custom level from env."""
        # Mock config with DEBUG level
        mock_config = Mock()
        mock_config.log_level = "DEBUG"
        mock_config.cache.enabled = False
        mock_load_config.return_value = mock_config

        with patch.object(sys, 'argv', ['snippy', '--clear-cache']):
            main()

            # Should set up logging with DEBUG level
            mock_setup_logging.assert_called_once_with("DEBUG")


class TestCLIReadOnlyMode:
    """Tests for read-only mode enforcement."""

    @patch('snippy.cli.ConnectionManager')
    @patch('snippy.cli.SecureCredentials')
    @patch('snippy.cli.load_config')
    def test_require_read_only_flag(
        self, mock_load_config, mock_credentials, mock_conn_manager
    ):
        """Test --require-read-only flag is passed to connection manager."""
        # Mock config
        mock_config = Mock()
        mock_config.db.host = "localhost"
        mock_config.db.port = 5432
        mock_config.db.database = "test_db"
        mock_config.db.user = "test_user"
        mock_config.db.schema = "public"
        mock_config.connection_ttl_minutes = 30
        mock_config.require_read_only = False  # Default
        mock_config.allow_write_connection = False
        mock_config.log_level = "INFO"
        mock_config.cache.enabled = False
        mock_load_config.return_value = mock_config

        # Mock password
        mock_credentials.get_password.return_value = "test_pass"

        # Mock REPL
        with patch('snippy.cli.REPL') as mock_repl:
            mock_repl_instance = Mock()
            mock_repl.return_value = mock_repl_instance

            with patch.object(sys, 'argv', [
                'snippy', '--repl',
                '--host', 'localhost',
                '--database', 'test_db',
                '--user', 'test_user',
                '--require-read-only',
            ]):
                main()

                # Should create connection manager with require_read_only=True
                call_kwargs = mock_conn_manager.call_args[1]
                assert call_kwargs['require_read_only'] is True


class TestCLIExceptionHandling:
    """Tests for general exception handling."""

    @patch('snippy.cli.load_config')
    def test_unexpected_exception_handling(self, mock_load_config):
        """Test unexpected exceptions are caught and logged."""
        # Make load_config raise an unexpected exception
        mock_load_config.side_effect = RuntimeError("Unexpected error")

        with patch.object(sys, 'argv', ['snippy', '--repl']):
            exit_code = main()

            # Should exit with error code
            assert exit_code != 0
