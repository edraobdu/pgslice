"""Tests for pgslice.cli module."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pgslice.cli import main, parse_timeframe, parse_timeframes
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


class TestParseTimeframe:
    """Tests for parse_timeframe function."""

    def test_parses_four_part_format(self) -> None:
        """Should parse table:column:start:end format."""
        result = parse_timeframe("orders:created_at:2024-01-01:2024-12-31")

        assert result.table_name == "orders"
        assert result.column_name == "created_at"
        assert result.start_date == datetime(2024, 1, 1)
        assert result.end_date == datetime(2024, 12, 31)

    def test_parses_three_part_format(self) -> None:
        """Should parse table:start:end format with default column."""
        result = parse_timeframe("orders:2024-01-01:2024-12-31")

        assert result.table_name == "orders"
        assert result.column_name == "created_at"
        assert result.start_date == datetime(2024, 1, 1)
        assert result.end_date == datetime(2024, 12, 31)

    def test_raises_for_invalid_format(self) -> None:
        """Should raise for invalid format."""
        with pytest.raises(InvalidTimeframeError, match="Invalid timeframe format"):
            parse_timeframe("orders")

        with pytest.raises(InvalidTimeframeError, match="Invalid timeframe format"):
            parse_timeframe("a:b:c:d:e")

    def test_raises_for_invalid_start_date(self) -> None:
        """Should raise for invalid start date."""
        with pytest.raises(InvalidTimeframeError, match="Invalid start date"):
            parse_timeframe("orders:invalid:2024-12-31")

    def test_raises_for_invalid_end_date(self) -> None:
        """Should raise for invalid end date."""
        with pytest.raises(InvalidTimeframeError, match="Invalid end date"):
            parse_timeframe("orders:2024-01-01:invalid")


class TestParseTimeframes:
    """Tests for parse_timeframes function."""

    def test_returns_empty_for_none(self) -> None:
        """Should return empty list for None."""
        assert parse_timeframes(None) == []

    def test_returns_empty_for_empty_list(self) -> None:
        """Should return empty list for empty list."""
        assert parse_timeframes([]) == []

    def test_parses_single_timeframe(self) -> None:
        """Should parse single timeframe."""
        result = parse_timeframes(["orders:2024-01-01:2024-12-31"])
        assert len(result) == 1
        assert result[0].table_name == "orders"

    def test_parses_multiple_timeframes(self) -> None:
        """Should parse multiple timeframes."""
        result = parse_timeframes(
            [
                "orders:2024-01-01:2024-12-31",
                "users:created_at:2024-06-01:2024-06-30",
            ]
        )
        assert len(result) == 2
        assert result[0].table_name == "orders"
        assert result[1].table_name == "users"


class TestCLIDumpMode:
    """Tests for CLI dump mode (non-interactive)."""

    def test_table_without_pks_fails(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should fail when --table is provided without --pks."""
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
            assert "--pks is required" in captured.err

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
                    "--timeframe",
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
