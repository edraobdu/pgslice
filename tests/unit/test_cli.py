"""Tests for pgslice.cli module."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pgslice.cli import (
    MainTableTimeframe,
    main,
    parse_main_timeframe,
    run_describe_table,
    run_list_tables,
)
from pgslice.utils.exceptions import InvalidTimeframeError


class TestMain:
    """Tests for main function."""

    def test_version_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print version and exit."""
        with patch.object(sys, "argv", ["pgslice", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "pgslice" in captured.out

    def test_help_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print help and exit."""
        with patch.object(sys, "argv", ["pgslice", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "PostgreSQL" in captured.out
        assert "--host" in captured.out

    def test_missing_required_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should fail with missing required parameters."""
        # Clear env vars
        monkeypatch.delenv("DB_HOST", raising=False)
        monkeypatch.delenv("DB_USER", raising=False)
        monkeypatch.delenv("DB_NAME", raising=False)

        with (
            patch.object(sys, "argv", ["pgslice"]),
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.db.host = ""
            mock_config.db.user = ""
            mock_config.db.database = ""
            mock_load.return_value = mock_config

            exit_code = main()
            assert exit_code == 1

    def test_clear_cache_flag(self, tmp_path: Path) -> None:
        """Should clear cache and exit."""
        with (
            patch.object(sys, "argv", ["pgslice", "--clear-cache"]),
            patch("pgslice.cli.load_config") as mock_load,
            patch("pgslice.cache.schema_cache.SchemaCache"),
        ):
            mock_config = MagicMock()
            mock_config.cache.enabled = True
            mock_config.cache.cache_dir = tmp_path
            mock_config.cache.ttl_hours = 24
            mock_load.return_value = mock_config

            exit_code = main()
            assert exit_code == 0

    def test_no_cache_flag(self) -> None:
        """Should disable caching when --no-cache is used."""
        with (
            patch.object(sys, "argv", ["pgslice", "--no-cache", "--host", "localhost"]),
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.db.host = ""
            mock_config.db.user = ""
            mock_config.db.database = ""
            mock_config.cache.enabled = True
            mock_load.return_value = mock_config

            main()

            # Cache should be disabled
            assert mock_config.cache.enabled is False

    def test_create_schema_flag(self) -> None:
        """Should enable create_schema when --create-schema is used."""
        with (
            patch.object(
                sys, "argv", ["pgslice", "--create-schema", "--host", "localhost"]
            ),
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.db.host = ""
            mock_config.db.user = ""
            mock_config.db.database = ""
            mock_config.create_schema = False
            mock_load.return_value = mock_config

            main()

            # create_schema should be enabled
            assert mock_config.create_schema is True

    def test_cli_args_override_config(self) -> None:
        """CLI arguments should override config values."""
        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "cli-host",
                    "--port",
                    "5433",
                    "--user",
                    "cli-user",
                    "--database",
                    "cli-db",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.db.host = "config-host"
            mock_config.db.port = 5432
            mock_config.db.user = "config-user"
            mock_config.db.database = "config-db"
            mock_config.db.schema = "public"
            mock_config.cache.enabled = True
            mock_config.connection_ttl_minutes = 30
            mock_load.return_value = mock_config

            with (
                patch("pgslice.cli.SecureCredentials"),
                patch("pgslice.cli.ConnectionManager") as mock_cm,
                patch("pgslice.cli.REPL"),
            ):
                mock_cm_instance = MagicMock()
                mock_cm.return_value = mock_cm_instance

                main()

            # CLI args should have overridden config
            assert mock_config.db.host == "cli-host"
            assert mock_config.db.port == 5433
            assert mock_config.db.user == "cli-user"
            assert mock_config.db.database == "cli-db"

    def test_keyboard_interrupt_handling(self) -> None:
        """Should handle keyboard interrupt gracefully."""
        with (
            patch.object(sys, "argv", ["pgslice"]),
            patch("pgslice.cli.load_config", side_effect=KeyboardInterrupt),
        ):
            exit_code = main()
            assert exit_code == 130

    def test_db_error_handling(self) -> None:
        """Should handle database errors."""
        from pgslice.utils.exceptions import DBConnectionError

        with (
            patch.object(sys, "argv", ["pgslice"]),
            patch(
                "pgslice.cli.load_config",
                side_effect=DBConnectionError("Connection failed"),
            ),
        ):
            exit_code = main()
            assert exit_code == 1

    def test_unexpected_error_handling(self) -> None:
        """Should handle unexpected errors."""
        with (
            patch.object(sys, "argv", ["pgslice"]),
            patch("pgslice.cli.load_config", side_effect=RuntimeError("Unexpected")),
        ):
            exit_code = main()
            assert exit_code == 1

    def test_log_level_argument(self) -> None:
        """Should respect log level argument."""
        with (
            patch.object(
                sys, "argv", ["pgslice", "--log-level", "DEBUG", "--clear-cache"]
            ),
            patch("pgslice.cli.setup_logging") as mock_setup,
        ):
            with patch("pgslice.cli.load_config") as mock_load:
                mock_config = MagicMock()
                mock_config.cache.enabled = False
                mock_load.return_value = mock_config

                main()

            mock_setup.assert_called_with("DEBUG")

    def test_connection_test_failure(self) -> None:
        """Should fail if connection test fails."""
        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "localhost",
                    "--user",
                    "test",
                    "--database",
                    "test",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.db.host = "localhost"
            mock_config.db.user = "test"
            mock_config.db.database = "test"
            mock_config.db.port = 5432
            mock_config.db.schema = "public"
            mock_config.cache.enabled = False
            mock_config.connection_ttl_minutes = 30
            mock_load.return_value = mock_config

            with (
                patch("pgslice.cli.SecureCredentials"),
                patch("pgslice.cli.ConnectionManager") as mock_cm,
            ):
                mock_cm_instance = MagicMock()
                mock_cm_instance.get_connection.side_effect = Exception(
                    "Connection failed"
                )
                mock_cm.return_value = mock_cm_instance

                exit_code = main()
                assert exit_code == 1

    def test_successful_repl_start(self) -> None:
        """Should start REPL successfully."""
        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "localhost",
                    "--user",
                    "test",
                    "--database",
                    "test",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.db.host = "localhost"
            mock_config.db.user = "test"
            mock_config.db.database = "test"
            mock_config.db.port = 5432
            mock_config.db.schema = "public"
            mock_config.cache.enabled = False
            mock_config.connection_ttl_minutes = 30
            mock_load.return_value = mock_config

            with patch("pgslice.cli.SecureCredentials") as mock_creds:
                mock_creds_instance = MagicMock()
                mock_creds.return_value = mock_creds_instance

                with patch("pgslice.cli.ConnectionManager") as mock_cm:
                    mock_cm_instance = MagicMock()
                    mock_cm.return_value = mock_cm_instance

                    with patch("pgslice.cli.REPL") as mock_repl:
                        mock_repl_instance = MagicMock()
                        mock_repl.return_value = mock_repl_instance

                        exit_code = main()

                        mock_repl_instance.start.assert_called_once()
                        mock_cm_instance.close.assert_called_once()
                        mock_creds_instance.clear.assert_called_once()
                        assert exit_code == 0


class TestCLIDumpMode:
    """Tests for CLI dump mode (non-interactive)."""

    def test_table_without_pks_or_timeframe_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should fail when --table is provided without --pks or --timeframe."""
        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "localhost",
                    "--user",
                    "test",
                    "--database",
                    "test",
                    "--table",
                    "users",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.db.host = "localhost"
            mock_config.db.user = "test"
            mock_config.db.database = "test"
            mock_load.return_value = mock_config

            exit_code = main()
            assert exit_code == 1

            captured = capsys.readouterr()
            assert "--pks or --timeframe is required" in captured.err

    def test_cli_dump_mode_executes(self) -> None:
        """Should execute dump in CLI mode when --table and --pks are provided."""
        from pgslice.dumper.dump_service import DumpResult

        mock_result = DumpResult(
            sql_content="INSERT INTO users VALUES (1);",
            record_count=1,
            tables_involved={"users"},
        )

        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "localhost",
                    "--user",
                    "test",
                    "--database",
                    "test",
                    "--table",
                    "users",
                    "--pks",
                    "1",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
            patch("pgslice.cli.SecureCredentials"),
            patch("pgslice.cli.ConnectionManager") as mock_cm,
            patch("pgslice.cli.DumpService") as mock_dump_service,
            patch("pgslice.cli.SQLWriter") as mock_writer,
        ):
            mock_config = MagicMock()
            mock_config.db.host = "localhost"
            mock_config.db.user = "test"
            mock_config.db.database = "test"
            mock_config.db.port = 5432
            mock_config.db.schema = "public"
            mock_config.cache.enabled = False
            mock_config.connection_ttl_minutes = 30
            mock_config.create_schema = False
            mock_load.return_value = mock_config

            mock_cm_instance = MagicMock()
            mock_cm.return_value = mock_cm_instance

            mock_service_instance = MagicMock()
            mock_service_instance.dump.return_value = mock_result
            mock_dump_service.return_value = mock_service_instance

            exit_code = main()
            assert exit_code == 0

            # DumpService.dump should have been called
            mock_service_instance.dump.assert_called_once()
            call_kwargs = mock_service_instance.dump.call_args[1]
            assert call_kwargs["table"] == "users"
            assert call_kwargs["pk_values"] == ["1"]

            # SQL should be written to stdout (no --output flag)
            mock_writer.write_to_stdout.assert_called_once_with(mock_result.sql_content)

    def test_cli_dump_with_output_file(self, tmp_path: Path) -> None:
        """Should write to file when --output is specified."""
        from pgslice.dumper.dump_service import DumpResult

        output_file = str(tmp_path / "output.sql")
        mock_result = DumpResult(
            sql_content="INSERT INTO users VALUES (1);",
            record_count=1,
            tables_involved={"users"},
        )

        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "localhost",
                    "--user",
                    "test",
                    "--database",
                    "test",
                    "--table",
                    "users",
                    "--pks",
                    "1",
                    "--output",
                    output_file,
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
            patch("pgslice.cli.SecureCredentials"),
            patch("pgslice.cli.ConnectionManager") as mock_cm,
            patch("pgslice.cli.DumpService") as mock_dump_service,
            patch("pgslice.cli.SQLWriter") as mock_writer,
        ):
            mock_config = MagicMock()
            mock_config.db.host = "localhost"
            mock_config.db.user = "test"
            mock_config.db.database = "test"
            mock_config.db.port = 5432
            mock_config.db.schema = "public"
            mock_config.cache.enabled = False
            mock_config.connection_ttl_minutes = 30
            mock_config.create_schema = False
            mock_load.return_value = mock_config

            mock_cm_instance = MagicMock()
            mock_cm.return_value = mock_cm_instance

            mock_service_instance = MagicMock()
            mock_service_instance.dump.return_value = mock_result
            mock_dump_service.return_value = mock_service_instance

            exit_code = main()
            assert exit_code == 0

            # SQL should be written to file
            mock_writer.write_to_file.assert_called_once()
            call_args = mock_writer.write_to_file.call_args[0]
            assert call_args[1] == output_file

    def test_cli_dump_with_flags(self) -> None:
        """Should pass flags to DumpService correctly."""
        from pgslice.dumper.dump_service import DumpResult

        mock_result = DumpResult(
            sql_content="INSERT...",
            record_count=1,
            tables_involved={"users"},
        )

        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "localhost",
                    "--user",
                    "test",
                    "--database",
                    "test",
                    "--table",
                    "users",
                    "--pks",
                    "1,2,3",
                    "--wide",
                    "--keep-pks",
                    "--create-schema",
                    "--truncate",
                    "orders:2024-01-01:2024-12-31",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
            patch("pgslice.cli.SecureCredentials"),
            patch("pgslice.cli.ConnectionManager") as mock_cm,
            patch("pgslice.cli.DumpService") as mock_dump_service,
            patch("pgslice.cli.SQLWriter"),
        ):
            mock_config = MagicMock()
            mock_config.db.host = "localhost"
            mock_config.db.user = "test"
            mock_config.db.database = "test"
            mock_config.db.port = 5432
            mock_config.db.schema = "public"
            mock_config.cache.enabled = False
            mock_config.connection_ttl_minutes = 30
            mock_config.create_schema = False
            mock_load.return_value = mock_config

            mock_cm_instance = MagicMock()
            mock_cm.return_value = mock_cm_instance

            mock_service_instance = MagicMock()
            mock_service_instance.dump.return_value = mock_result
            mock_dump_service.return_value = mock_service_instance

            exit_code = main()
            assert exit_code == 0

            # Check that flags were passed correctly
            call_kwargs = mock_service_instance.dump.call_args[1]
            assert call_kwargs["pk_values"] == ["1", "2", "3"]
            assert call_kwargs["wide_mode"] is True
            assert call_kwargs["keep_pks"] is True
            assert call_kwargs["create_schema"] is True
            assert len(call_kwargs["timeframe_filters"]) == 1


class TestLoggingDefault:
    """Tests for logging disabled by default."""

    def test_logging_disabled_by_default(self) -> None:
        """Should disable logging when --log-level is not specified."""
        with (
            patch.object(sys, "argv", ["pgslice", "--clear-cache"]),
            patch("pgslice.cli.setup_logging") as mock_setup,
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.cache.enabled = False
            mock_load.return_value = mock_config

            main()

            # setup_logging should be called with None (disabled)
            mock_setup.assert_called_with(None)


class TestParseMainTimeframe:
    """Tests for parse_main_timeframe function."""

    def test_parses_valid_format(self) -> None:
        """Should parse column:start:end format."""
        result = parse_main_timeframe("created_at:2024-01-01:2024-12-31")

        assert isinstance(result, MainTableTimeframe)
        assert result.column_name == "created_at"
        assert result.start_date == datetime(2024, 1, 1)
        assert result.end_date == datetime(2024, 12, 31)

    def test_raises_for_invalid_format(self) -> None:
        """Should raise for invalid format."""
        with pytest.raises(InvalidTimeframeError, match="Invalid timeframe format"):
            parse_main_timeframe("just_column")

        with pytest.raises(InvalidTimeframeError, match="Invalid timeframe format"):
            parse_main_timeframe("a:b:c:d")

    def test_raises_for_invalid_start_date(self) -> None:
        """Should raise for invalid start date."""
        with pytest.raises(InvalidTimeframeError, match="Invalid start date"):
            parse_main_timeframe("created_at:invalid:2024-12-31")

    def test_raises_for_invalid_end_date(self) -> None:
        """Should raise for invalid end date."""
        with pytest.raises(InvalidTimeframeError, match="Invalid end date"):
            parse_main_timeframe("created_at:2024-01-01:invalid")


class TestMainTableTimeframeCLI:
    """Tests for main table timeframe CLI functionality."""

    def test_mutual_exclusion_with_pks(self) -> None:
        """Should not allow both --pks and --timeframe."""
        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--table",
                    "users",
                    "--pks",
                    "1",
                    "--timeframe",
                    "created_at:2024-01-01:2024-12-31",
                ],
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        # argparse exits with 2 for argument errors
        assert exc_info.value.code == 2

    def test_timeframe_mode_executes(self) -> None:
        """Should execute dump with timeframe mode."""
        from pgslice.dumper.dump_service import DumpResult

        mock_result = DumpResult(
            sql_content="INSERT INTO users VALUES (1);",
            record_count=1,
            tables_involved={"users"},
        )

        mock_table_meta = MagicMock()
        mock_table_meta.primary_keys = ["id"]

        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "localhost",
                    "--user",
                    "test",
                    "--database",
                    "test",
                    "--table",
                    "users",
                    "--timeframe",
                    "created_at:2024-01-01:2024-12-31",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
            patch("pgslice.cli.SecureCredentials"),
            patch("pgslice.cli.ConnectionManager") as mock_cm,
            patch("pgslice.cli.SchemaIntrospector") as mock_introspector,
            patch("pgslice.cli.DumpService") as mock_dump_service,
            patch("pgslice.cli.SQLWriter"),
            patch("pgslice.cli.printy"),
        ):
            mock_config = MagicMock()
            mock_config.db.host = "localhost"
            mock_config.db.user = "test"
            mock_config.db.database = "test"
            mock_config.db.port = 5432
            mock_config.db.schema = "public"
            mock_config.cache.enabled = False
            mock_config.connection_ttl_minutes = 30
            mock_config.create_schema = False
            mock_load.return_value = mock_config

            mock_cm_instance = MagicMock()
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [(1,), (2,), (3,)]
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_cm_instance.get_connection.return_value = mock_conn
            mock_cm.return_value = mock_cm_instance

            mock_introspector_instance = MagicMock()
            mock_introspector_instance.get_table_metadata.return_value = mock_table_meta
            mock_introspector.return_value = mock_introspector_instance

            mock_service_instance = MagicMock()
            mock_service_instance.dump.return_value = mock_result
            mock_dump_service.return_value = mock_service_instance

            exit_code = main()
            assert exit_code == 0

            # DumpService.dump should have been called with PKs from timeframe query
            mock_service_instance.dump.assert_called_once()
            call_kwargs = mock_service_instance.dump.call_args[1]
            assert call_kwargs["pk_values"] == ["1", "2", "3"]

    def test_timeframe_mode_empty_result(self) -> None:
        """Should handle empty result from timeframe query."""
        mock_table_meta = MagicMock()
        mock_table_meta.primary_keys = ["id"]

        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "localhost",
                    "--user",
                    "test",
                    "--database",
                    "test",
                    "--table",
                    "users",
                    "--timeframe",
                    "created_at:2024-01-01:2024-12-31",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
            patch("pgslice.cli.SecureCredentials"),
            patch("pgslice.cli.ConnectionManager") as mock_cm,
            patch("pgslice.cli.SchemaIntrospector") as mock_introspector,
            patch("pgslice.cli.printy") as mock_printy,
        ):
            mock_config = MagicMock()
            mock_config.db.host = "localhost"
            mock_config.db.user = "test"
            mock_config.db.database = "test"
            mock_config.db.port = 5432
            mock_config.db.schema = "public"
            mock_config.cache.enabled = False
            mock_config.connection_ttl_minutes = 30
            mock_config.create_schema = False
            mock_load.return_value = mock_config

            mock_cm_instance = MagicMock()
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []  # Empty result
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_cm_instance.get_connection.return_value = mock_conn
            mock_cm.return_value = mock_cm_instance

            mock_introspector_instance = MagicMock()
            mock_introspector_instance.get_table_metadata.return_value = mock_table_meta
            mock_introspector.return_value = mock_introspector_instance

            exit_code = main()
            assert exit_code == 0

            # Should print warning about no records found
            mock_printy.assert_any_call("[y]No records found matching the timeframe@")


class TestSchemaInfoFlags:
    """Tests for --tables and --describe CLI flags."""

    def test_tables_flag_lists_tables(self) -> None:
        """Should list tables when --tables is used."""
        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "localhost",
                    "--user",
                    "test",
                    "--database",
                    "test",
                    "--tables",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
            patch("pgslice.cli.SecureCredentials"),
            patch("pgslice.cli.ConnectionManager") as mock_cm,
            patch(
                "pgslice.operations.schema_ops.SchemaIntrospector"
            ) as mock_introspector,
            patch("pgslice.operations.schema_ops.printy") as mock_printy,
        ):
            mock_config = MagicMock()
            mock_config.db.host = "localhost"
            mock_config.db.user = "test"
            mock_config.db.database = "test"
            mock_config.db.port = 5432
            mock_config.db.schema = "public"
            mock_config.cache.enabled = False
            mock_config.connection_ttl_minutes = 30
            mock_load.return_value = mock_config

            mock_cm_instance = MagicMock()
            mock_cm.return_value = mock_cm_instance

            mock_introspector_instance = MagicMock()
            mock_introspector_instance.get_all_tables.return_value = [
                "users",
                "orders",
                "products",
            ]
            mock_introspector.return_value = mock_introspector_instance

            exit_code = main()
            assert exit_code == 0

            # Should print each table and total
            mock_printy.assert_any_call("  users")
            mock_printy.assert_any_call("  orders")
            mock_printy.assert_any_call("  products")

    def test_describe_flag_shows_table_info(self) -> None:
        """Should describe table when --describe is used."""
        mock_table = MagicMock()
        mock_table.full_name = "public.users"
        mock_table.columns = []
        mock_table.primary_keys = ["id"]
        mock_table.foreign_keys_outgoing = []
        mock_table.foreign_keys_incoming = []

        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "localhost",
                    "--user",
                    "test",
                    "--database",
                    "test",
                    "--describe",
                    "users",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
            patch("pgslice.cli.SecureCredentials"),
            patch("pgslice.cli.ConnectionManager") as mock_cm,
            patch(
                "pgslice.operations.schema_ops.SchemaIntrospector"
            ) as mock_introspector,
            patch("pgslice.operations.schema_ops.printy") as mock_printy,
            patch(
                "pgslice.operations.schema_ops.tabulate", return_value="COLUMNS TABLE"
            ),
        ):
            mock_config = MagicMock()
            mock_config.db.host = "localhost"
            mock_config.db.user = "test"
            mock_config.db.database = "test"
            mock_config.db.port = 5432
            mock_config.db.schema = "public"
            mock_config.cache.enabled = False
            mock_config.connection_ttl_minutes = 30
            mock_load.return_value = mock_config

            mock_cm_instance = MagicMock()
            mock_cm.return_value = mock_cm_instance

            mock_introspector_instance = MagicMock()
            mock_introspector_instance.get_table_metadata.return_value = mock_table
            mock_introspector.return_value = mock_introspector_instance

            exit_code = main()
            assert exit_code == 0

            # Should print table name
            mock_printy.assert_any_call("\n[c]Table: public.users@\n")

    def test_run_list_tables_function(self) -> None:
        """Should return tables from introspector."""
        mock_conn_manager = MagicMock()
        mock_conn = MagicMock()
        mock_conn_manager.get_connection.return_value = mock_conn

        with (
            patch(
                "pgslice.operations.schema_ops.SchemaIntrospector"
            ) as mock_introspector,
            patch("pgslice.operations.schema_ops.printy"),
        ):
            mock_introspector_instance = MagicMock()
            mock_introspector_instance.get_all_tables.return_value = ["table1"]
            mock_introspector.return_value = mock_introspector_instance

            result = run_list_tables(mock_conn_manager, "public")
            assert result == 0

    def test_run_describe_table_function(self) -> None:
        """Should return table metadata from introspector."""
        mock_conn_manager = MagicMock()
        mock_conn = MagicMock()
        mock_conn_manager.get_connection.return_value = mock_conn

        mock_table = MagicMock()
        mock_table.full_name = "public.users"
        mock_table.columns = []
        mock_table.primary_keys = []
        mock_table.foreign_keys_outgoing = []
        mock_table.foreign_keys_incoming = []

        with (
            patch(
                "pgslice.operations.schema_ops.SchemaIntrospector"
            ) as mock_introspector,
            patch("pgslice.operations.schema_ops.printy"),
            patch("pgslice.operations.schema_ops.tabulate", return_value=""),
        ):
            mock_introspector_instance = MagicMock()
            mock_introspector_instance.get_table_metadata.return_value = mock_table
            mock_introspector.return_value = mock_introspector_instance

            result = run_describe_table(mock_conn_manager, "public", "users")
            assert result == 0
