"""Integration tests for REPL functionality."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from io import StringIO

from snippy.repl import REPL
from snippy.db.connection import ConnectionManager
from snippy.utils.exceptions import InvalidTimeframeError


@pytest.mark.integration
class TestREPLCommands:
    """Tests for REPL command execution."""

    @pytest.fixture
    def repl(self, test_db_connection, test_app_config):
        """Create REPL instance."""
        conn_manager = Mock(spec=ConnectionManager)
        conn_manager.get_connection.return_value = test_db_connection

        return REPL(conn_manager, test_app_config)

    def test_cmd_help(self, repl):
        """Test help command displays available commands."""
        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_help([])

            # Should print help information
            assert mock_print.called
            # Check that command names are mentioned
            call_args_str = str(mock_print.call_args_list)
            assert "dump" in call_args_str or "help" in call_args_str.lower()

    def test_cmd_list_tables(self, repl):
        """Test tables command lists all tables."""
        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_list_tables([])

            # Should print table names
            assert mock_print.called
            call_args_str = str(mock_print.call_args_list)
            # Should mention some tables from test schema
            assert "users" in call_args_str or "roles" in call_args_str

    def test_cmd_list_tables_with_schema(self, repl):
        """Test tables command with schema argument."""
        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_list_tables(["--schema", "public"])

            # Should print tables from public schema
            assert mock_print.called

    def test_cmd_describe_table(self, repl):
        """Test describe command shows table structure."""
        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_describe_table(["users"])

            # Should print table information
            assert mock_print.called
            call_args_str = str(mock_print.call_args_list)
            # Should mention columns
            assert "id" in call_args_str or "username" in call_args_str

    def test_cmd_describe_table_with_schema(self, repl):
        """Test describe command with schema argument."""
        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_describe_table(["users", "--schema", "public"])

            assert mock_print.called

    def test_cmd_describe_table_not_found(self, repl):
        """Test describe command with non-existent table."""
        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_describe_table(["nonexistent_table"])

            # Should print error message
            assert mock_print.called
            call_args_str = str(mock_print.call_args_list)
            assert "error" in call_args_str.lower() or "not found" in call_args_str.lower()

    def test_cmd_describe_table_without_args(self, repl):
        """Test describe command without table name shows usage."""
        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_describe_table([])

            # Should print usage information
            assert mock_print.called
            call_args_str = str(mock_print.call_args_list)
            assert "usage" in call_args_str.lower()


@pytest.mark.integration
class TestREPLDumpCommand:
    """Tests for REPL dump command."""

    @pytest.fixture
    def repl(self, test_db_connection, test_app_config):
        """Create REPL instance."""
        conn_manager = Mock(spec=ConnectionManager)
        conn_manager.get_connection.return_value = test_db_connection

        return REPL(conn_manager, test_app_config)

    def test_cmd_dump_without_args(self, repl):
        """Test dump command without arguments shows usage."""
        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_dump([])

            # Should print usage information
            assert mock_print.called
            call_args_str = str(mock_print.call_args_list)
            assert "usage" in call_args_str.lower()

    def test_cmd_dump_with_single_pk(self, repl, tmp_path):
        """Test dump command with single PK value."""
        output_file = tmp_path / "test_dump.sql"

        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_dump(["roles", "1", "--output", str(output_file)])

            # Should create output file
            assert output_file.exists()

            # Should print success message
            call_args_str = str(mock_print.call_args_list)
            assert "wrote" in call_args_str.lower() or "success" in call_args_str.lower()

    def test_cmd_dump_with_multiple_pks(self, repl, tmp_path):
        """Test dump command with multiple PK values."""
        output_file = tmp_path / "test_dump.sql"

        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_dump(["roles", "1,2,3", "--output", str(output_file)])

            # Should create output file with multiple records
            assert output_file.exists()

    def test_cmd_dump_to_stdout(self, repl):
        """Test dump command without --output prints to stdout."""
        # Capture stdout
        import sys
        from io import StringIO

        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        try:
            repl._cmd_dump(["roles", "1"])

            output = captured_output.getvalue()
            # Should contain SQL
            assert "INSERT" in output or "SELECT" in output or "role" in output.lower()

        finally:
            sys.stdout = old_stdout

    def test_cmd_dump_with_wide_mode(self, repl, tmp_path):
        """Test dump command with --wide flag."""
        output_file = tmp_path / "test_dump.sql"

        with patch.object(repl.console, 'print'):
            repl._cmd_dump(["users", "1", "--output", str(output_file), "--wide"])

            # Should create output file
            assert output_file.exists()

    def test_cmd_dump_with_schema(self, repl, tmp_path):
        """Test dump command with --schema flag."""
        output_file = tmp_path / "test_dump.sql"

        with patch.object(repl.console, 'print'):
            repl._cmd_dump(["users", "1", "--output", str(output_file), "--schema", "public"])

            assert output_file.exists()


@pytest.mark.integration
class TestREPLTimeframeFilter:
    """Tests for REPL timeframe filter parsing."""

    @pytest.fixture
    def repl(self, test_db_connection, test_app_config):
        """Create REPL instance."""
        conn_manager = Mock(spec=ConnectionManager)
        conn_manager.get_connection.return_value = test_db_connection

        return REPL(conn_manager, test_app_config)

    def test_parse_timeframe_full_format(self, repl):
        """Test parsing timeframe with full format (table:column:start:end)."""
        tf = repl._parse_timeframe("transactions:created_at:2024-01-01:2024-12-31")

        assert tf.table_name == "transactions"
        assert tf.column_name == "created_at"
        assert tf.start_date.year == 2024
        assert tf.start_date.month == 1
        assert tf.end_date.year == 2024
        assert tf.end_date.month == 12

    def test_parse_timeframe_short_format(self, repl):
        """Test parsing timeframe with short format (table:start:end)."""
        tf = repl._parse_timeframe("transactions:2024-01-01:2024-12-31")

        assert tf.table_name == "transactions"
        assert tf.column_name == "created_at"  # Default column
        assert tf.start_date.year == 2024

    def test_parse_timeframe_invalid_format(self, repl):
        """Test parsing invalid timeframe format raises error."""
        with pytest.raises(InvalidTimeframeError):
            repl._parse_timeframe("invalid_format")

    def test_parse_timeframe_invalid_date(self, repl):
        """Test parsing timeframe with invalid date raises error."""
        with pytest.raises(InvalidTimeframeError):
            repl._parse_timeframe("transactions:created_at:not-a-date:2024-12-31")


@pytest.mark.integration
class TestREPLCacheCommands:
    """Tests for REPL cache commands."""

    @pytest.fixture
    def repl_with_cache(self, test_db_connection, test_app_config):
        """Create REPL instance with cache enabled."""
        conn_manager = Mock(spec=ConnectionManager)
        conn_manager.get_connection.return_value = test_db_connection

        # Ensure cache is enabled
        test_app_config.cache.enabled = True

        return REPL(conn_manager, test_app_config)

    def test_cmd_clear_cache(self, repl_with_cache):
        """Test clear cache command."""
        with patch.object(repl_with_cache.console, 'print') as mock_print:
            repl_with_cache._cmd_clear_cache([])

            # Should print success message
            call_args_str = str(mock_print.call_args_list)
            assert "cleared" in call_args_str.lower() or "success" in call_args_str.lower()

    def test_cmd_clear_cache_when_disabled(self, test_db_connection, test_app_config):
        """Test clear cache command when cache is disabled."""
        conn_manager = Mock(spec=ConnectionManager)
        conn_manager.get_connection.return_value = test_db_connection

        # Disable cache
        test_app_config.cache.enabled = False
        repl = REPL(conn_manager, test_app_config)

        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_clear_cache([])

            # Should print message that cache is disabled
            call_args_str = str(mock_print.call_args_list)
            assert "disabled" in call_args_str.lower()


@pytest.mark.integration
class TestREPLErrorHandling:
    """Tests for REPL error handling."""

    @pytest.fixture
    def repl(self, test_db_connection, test_app_config):
        """Create REPL instance."""
        conn_manager = Mock(spec=ConnectionManager)
        conn_manager.get_connection.return_value = test_db_connection

        return REPL(conn_manager, test_app_config)

    def test_dump_invalid_table(self, repl):
        """Test dump command with invalid table name."""
        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_dump(["nonexistent_table", "1"])

            # Should print error message
            call_args_str = str(mock_print.call_args_list)
            assert "error" in call_args_str.lower()

    def test_dump_invalid_pk_value(self, repl):
        """Test dump command with non-existent PK value."""
        with patch.object(repl.console, 'print') as mock_print:
            repl._cmd_dump(["roles", "99999"])  # Unlikely to exist

            # Should complete (might find 0 records, which is valid)
            # Just verify it doesn't crash
            assert True
