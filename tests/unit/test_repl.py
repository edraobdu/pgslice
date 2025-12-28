"""Tests for pgslice.repl module."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pgslice.config import AppConfig, CacheConfig, DatabaseConfig
from pgslice.repl import REPL


class TestREPL:
    """Tests for REPL class."""

    @pytest.fixture
    def mock_connection_manager(self) -> MagicMock:
        """Create a mock connection manager."""
        manager = MagicMock()
        conn = MagicMock()
        manager.get_connection.return_value = conn
        return manager

    @pytest.fixture
    def app_config(self, tmp_path: Path) -> AppConfig:
        """Create an application config."""
        return AppConfig(
            db=DatabaseConfig(
                host="localhost",
                port=5432,
                user="test_user",
                database="test_db",
                schema="public",
            ),
            cache=CacheConfig(
                enabled=True,
                cache_dir=tmp_path / "cache",
                ttl_hours=24,
            ),
            connection_ttl_minutes=30,
            max_depth=10,
            sql_batch_size=100,
            output_dir=tmp_path / "output",
        )

    @pytest.fixture
    def app_config_no_cache(self, tmp_path: Path) -> AppConfig:
        """Create an application config with cache disabled."""
        return AppConfig(
            db=DatabaseConfig(
                host="localhost",
                port=5432,
                user="test_user",
                database="test_db",
                schema="public",
            ),
            cache=CacheConfig(
                enabled=False,
                cache_dir=tmp_path / "cache",
                ttl_hours=24,
            ),
            connection_ttl_minutes=30,
            max_depth=10,
            sql_batch_size=100,
            output_dir=tmp_path / "output",
        )

    @pytest.fixture
    def repl(
        self, mock_connection_manager: MagicMock, app_config: AppConfig
    ) -> Generator[REPL, None, None]:
        """Create a REPL instance with mocked SchemaCache."""
        with patch("pgslice.repl.SchemaCache") as mock_cache_class:
            mock_cache = MagicMock()
            mock_cache_class.return_value = mock_cache
            instance = REPL(mock_connection_manager, app_config)
            yield instance

    @pytest.fixture
    def repl_no_cache(
        self, mock_connection_manager: MagicMock, app_config_no_cache: AppConfig
    ) -> Generator[REPL, None, None]:
        """Create a REPL instance without cache."""
        instance = REPL(mock_connection_manager, app_config_no_cache)
        yield instance


class TestInit(TestREPL):
    """Tests for REPL initialization."""

    def test_stores_connection_manager(
        self, repl: REPL, mock_connection_manager: MagicMock
    ) -> None:
        """Should store the connection manager."""
        assert repl.conn_manager == mock_connection_manager

    def test_stores_config(self, repl: REPL, app_config: AppConfig) -> None:
        """Should store the config."""
        assert repl.config == app_config

    def test_initializes_cache_when_enabled(self, repl: REPL) -> None:
        """Should initialize cache when enabled."""
        assert repl.cache is not None

    def test_no_cache_when_disabled(self, repl_no_cache: REPL) -> None:
        """Should not initialize cache when disabled."""
        assert repl_no_cache.cache is None

    def test_registers_commands(self, repl: REPL) -> None:
        """Should register all commands."""
        expected_commands = [
            "dump",
            "help",
            "exit",
            "quit",
            "tables",
            "describe",
            "clear",
        ]
        for cmd in expected_commands:
            assert cmd in repl.commands


class TestCmdHelp(TestREPL):
    """Tests for _cmd_help method."""

    def test_displays_help(
        self, repl: REPL, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should display help information."""
        with patch("pgslice.repl.printy"):
            repl._cmd_help([])

        # Just verify it doesn't raise


class TestCmdExit(TestREPL):
    """Tests for _cmd_exit method."""

    def test_raises_eoferror(self, repl: REPL) -> None:
        """Should raise EOFError to exit REPL."""
        with patch("pgslice.repl.printy"), pytest.raises(EOFError):
            repl._cmd_exit([])


class TestCmdListTables(TestREPL):
    """Tests for _cmd_list_tables method."""

    def test_lists_tables_in_default_schema(
        self, repl: REPL, mock_connection_manager: MagicMock
    ) -> None:
        """Should list tables in default schema."""
        with patch(
            "pgslice.operations.schema_ops.SchemaIntrospector"
        ) as mock_introspector:
            mock_instance = MagicMock()
            mock_instance.get_all_tables.return_value = ["users", "orders"]
            mock_introspector.return_value = mock_instance

            with patch("pgslice.operations.schema_ops.printy"):
                repl._cmd_list_tables([])

            mock_instance.get_all_tables.assert_called_once_with("public")

    def test_lists_tables_with_custom_schema(
        self, repl: REPL, mock_connection_manager: MagicMock
    ) -> None:
        """Should list tables in custom schema."""
        with patch(
            "pgslice.operations.schema_ops.SchemaIntrospector"
        ) as mock_introspector:
            mock_instance = MagicMock()
            mock_instance.get_all_tables.return_value = ["custom_table"]
            mock_introspector.return_value = mock_instance

            with patch("pgslice.operations.schema_ops.printy"):
                repl._cmd_list_tables(["--schema", "custom"])

            mock_instance.get_all_tables.assert_called_once_with("custom")

    def test_handles_error(
        self, repl: REPL, mock_connection_manager: MagicMock
    ) -> None:
        """Should handle errors gracefully."""
        with patch(
            "pgslice.operations.schema_ops.SchemaIntrospector"
        ) as mock_introspector:
            mock_introspector.side_effect = Exception("Connection error")

            with (
                patch("pgslice.repl.printy"),
                patch("pgslice.operations.schema_ops.printy"),
            ):
                # Should not raise
                repl._cmd_list_tables([])


class TestCmdDescribeTable(TestREPL):
    """Tests for _cmd_describe_table method."""

    def test_shows_usage_without_args(
        self, repl: REPL, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Should show usage when no table specified."""
        with patch("pgslice.repl.printy") as mock_printy:
            repl._cmd_describe_table([])
            mock_printy.assert_called()

    def test_describes_table(
        self, repl: REPL, mock_connection_manager: MagicMock
    ) -> None:
        """Should describe table structure."""
        from pgslice.graph.models import Column, ForeignKey, Table

        mock_table = Table(
            schema_name="public",
            table_name="users",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                ),
                Column(
                    name="name",
                    data_type="text",
                    udt_name="text",
                    nullable=True,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[
                ForeignKey(
                    constraint_name="fk_org",
                    source_table="public.users",
                    source_column="org_id",
                    target_table="public.orgs",
                    target_column="id",
                )
            ],
            foreign_keys_incoming=[
                ForeignKey(
                    constraint_name="fk_orders_user",
                    source_table="public.orders",
                    source_column="user_id",
                    target_table="public.users",
                    target_column="id",
                )
            ],
        )

        with patch(
            "pgslice.operations.schema_ops.SchemaIntrospector"
        ) as mock_introspector:
            mock_instance = MagicMock()
            mock_instance.get_table_metadata.return_value = mock_table
            mock_introspector.return_value = mock_instance

            with (
                patch("pgslice.operations.schema_ops.printy"),
                patch("pgslice.operations.schema_ops.tabulate", return_value=""),
            ):
                repl._cmd_describe_table(["users"])

            mock_instance.get_table_metadata.assert_called_once_with("public", "users")

    def test_describes_table_with_custom_schema(
        self, repl: REPL, mock_connection_manager: MagicMock
    ) -> None:
        """Should describe table in custom schema."""
        from pgslice.graph.models import Column, Table

        mock_table = Table(
            schema_name="custom",
            table_name="data",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        with patch(
            "pgslice.operations.schema_ops.SchemaIntrospector"
        ) as mock_introspector:
            mock_instance = MagicMock()
            mock_instance.get_table_metadata.return_value = mock_table
            mock_introspector.return_value = mock_instance

            with (
                patch("pgslice.operations.schema_ops.printy"),
                patch("pgslice.operations.schema_ops.tabulate", return_value=""),
            ):
                repl._cmd_describe_table(["data", "--schema", "custom"])

            mock_instance.get_table_metadata.assert_called_once_with("custom", "data")


class TestCmdClearCache(TestREPL):
    """Tests for _cmd_clear_cache method."""

    def test_clears_cache_when_enabled(self, repl: REPL) -> None:
        """Should clear cache when enabled."""
        mock_cache = MagicMock()
        repl.cache = mock_cache

        with patch("pgslice.repl.printy"):
            repl._cmd_clear_cache([])

        mock_cache.invalidate_cache.assert_called_once_with("localhost", "test_db")

    def test_warns_when_cache_disabled(self, repl_no_cache: REPL) -> None:
        """Should warn when cache is disabled."""
        with patch("pgslice.repl.printy") as mock_printy:
            repl_no_cache._cmd_clear_cache([])
            mock_printy.assert_called_with("[y]Cache is disabled@")


class TestCmdDump(TestREPL):
    """Tests for _cmd_dump method."""

    def test_shows_usage_without_args(self, repl: REPL) -> None:
        """Should show usage when insufficient args."""
        with patch("pgslice.repl.printy"):
            repl._cmd_dump([])
            repl._cmd_dump(["users"])

    def test_executes_dump(
        self, repl: REPL, mock_connection_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Should execute dump command using DumpService."""
        from pgslice.dumper.dump_service import DumpResult

        mock_result = DumpResult(
            sql_content="INSERT INTO users (id) VALUES (42);",
            record_count=1,
            tables_involved={"users"},
        )

        with (
            patch("pgslice.repl.DumpService") as mock_dump_service,
            patch("pgslice.repl.SQLWriter") as mock_writer,
            patch("pgslice.repl.printy"),
        ):
            mock_service_instance = MagicMock()
            mock_service_instance.dump.return_value = mock_result
            mock_dump_service.return_value = mock_service_instance

            mock_writer.get_default_output_path.return_value = tmp_path / "users_42.sql"

            repl._cmd_dump(["users", "42"])

            mock_service_instance.dump.assert_called_once()
            call_kwargs = mock_service_instance.dump.call_args[1]
            assert call_kwargs["table"] == "users"
            assert call_kwargs["pk_values"] == ["42"]

    def test_executes_dump_with_output_file(
        self, repl: REPL, mock_connection_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Should execute dump with specified output file."""
        from pgslice.dumper.dump_service import DumpResult

        mock_result = DumpResult(
            sql_content="INSERT INTO users (id) VALUES (42);",
            record_count=1,
            tables_involved={"users"},
        )

        output_file = str(tmp_path / "custom_output.sql")

        with (
            patch("pgslice.repl.DumpService") as mock_dump_service,
            patch("pgslice.repl.SQLWriter") as mock_writer,
            patch("pgslice.repl.printy"),
        ):
            mock_service_instance = MagicMock()
            mock_service_instance.dump.return_value = mock_result
            mock_dump_service.return_value = mock_service_instance

            repl._cmd_dump(["users", "42", "--output", output_file])

            mock_writer.write_to_file.assert_called_once()
            call_args = mock_writer.write_to_file.call_args
            assert call_args[0][1] == output_file

    def test_executes_dump_with_multiple_pks(
        self, repl: REPL, mock_connection_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Should execute dump with multiple PKs."""
        from pgslice.dumper.dump_service import DumpResult

        mock_result = DumpResult(
            sql_content="INSERT...",
            record_count=3,
            tables_involved={"users"},
        )

        with (
            patch("pgslice.repl.DumpService") as mock_dump_service,
            patch("pgslice.repl.SQLWriter") as mock_writer,
            patch("pgslice.repl.printy"),
        ):
            mock_service_instance = MagicMock()
            mock_service_instance.dump.return_value = mock_result
            mock_dump_service.return_value = mock_service_instance

            mock_writer.get_default_output_path.return_value = tmp_path / "out.sql"

            repl._cmd_dump(["users", "42,43,44"])

            call_kwargs = mock_service_instance.dump.call_args[1]
            assert call_kwargs["pk_values"] == ["42", "43", "44"]

    def test_handles_wide_mode_flag(
        self, repl: REPL, mock_connection_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Should handle --wide flag."""
        from pgslice.dumper.dump_service import DumpResult

        mock_result = DumpResult(
            sql_content="INSERT...",
            record_count=1,
            tables_involved={"users"},
        )

        with (
            patch("pgslice.repl.DumpService") as mock_dump_service,
            patch("pgslice.repl.SQLWriter") as mock_writer,
            patch("pgslice.repl.printy"),
        ):
            mock_service_instance = MagicMock()
            mock_service_instance.dump.return_value = mock_result
            mock_dump_service.return_value = mock_service_instance

            mock_writer.get_default_output_path.return_value = tmp_path / "out.sql"

            repl._cmd_dump(["users", "42", "--wide"])

            # Check that wide_mode=True was passed to DumpService.dump()
            call_kwargs = mock_service_instance.dump.call_args[1]
            assert call_kwargs["wide_mode"] is True

    def test_handles_truncate_flag(
        self, repl: REPL, mock_connection_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Should handle --truncate flag."""
        from pgslice.dumper.dump_service import DumpResult

        mock_result = DumpResult(
            sql_content="INSERT...",
            record_count=1,
            tables_involved={"users"},
        )

        with (
            patch("pgslice.repl.DumpService") as mock_dump_service,
            patch("pgslice.repl.SQLWriter") as mock_writer,
            patch("pgslice.repl.printy"),
        ):
            mock_service_instance = MagicMock()
            mock_service_instance.dump.return_value = mock_result
            mock_dump_service.return_value = mock_service_instance

            mock_writer.get_default_output_path.return_value = tmp_path / "out.sql"

            repl._cmd_dump(
                [
                    "users",
                    "42",
                    "--truncate",
                    "orders:created_at:2024-01-01:2024-12-31",
                ]
            )

            # Check that timeframe_filters was passed to DumpService.dump()
            call_kwargs = mock_service_instance.dump.call_args[1]
            assert len(call_kwargs["timeframe_filters"]) == 1

    def test_handles_invalid_truncate(self, repl: REPL) -> None:
        """Should handle invalid truncate filter."""
        with patch("pgslice.repl.printy"):
            # Invalid format - should not raise, just print error
            repl._cmd_dump(["users", "42", "--truncate", "invalid"])

    def test_handles_dump_error(
        self, repl: REPL, mock_connection_manager: MagicMock
    ) -> None:
        """Should handle errors during dump."""
        from pgslice.utils.exceptions import RecordNotFoundError

        with (
            patch("pgslice.repl.DumpService") as mock_dump_service,
            patch("pgslice.repl.printy"),
        ):
            mock_service_instance = MagicMock()
            mock_service_instance.dump.side_effect = RecordNotFoundError("Not found")
            mock_dump_service.return_value = mock_service_instance

            # Should not raise
            repl._cmd_dump(["users", "42"])


class TestStart(TestREPL):
    """Tests for start method."""

    def test_creates_prompt_session(self, repl: REPL, tmp_path: Path) -> None:
        """Should create a prompt session."""
        with patch("pgslice.repl.PromptSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.prompt.side_effect = EOFError()
            mock_session_class.return_value = mock_session

            with (
                patch("pgslice.repl.printy"),
                patch("pgslice.repl.FileHistory"),
            ):
                repl.start()

            mock_session_class.assert_called_once()

    def test_handles_keyboard_interrupt(self, repl: REPL) -> None:
        """Should handle keyboard interrupt."""
        with patch("pgslice.repl.PromptSession") as mock_session_class:
            mock_session = MagicMock()
            # First call raises KeyboardInterrupt, second raises EOFError to exit
            mock_session.prompt.side_effect = [KeyboardInterrupt(), EOFError()]
            mock_session_class.return_value = mock_session

            with (
                patch("pgslice.repl.printy"),
                patch("pgslice.repl.FileHistory"),
            ):
                repl.start()

    def test_handles_empty_input(self, repl: REPL) -> None:
        """Should ignore empty input."""
        with patch("pgslice.repl.PromptSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.prompt.side_effect = ["", "  ", EOFError()]
            mock_session_class.return_value = mock_session

            with (
                patch("pgslice.repl.printy"),
                patch("pgslice.repl.FileHistory"),
            ):
                repl.start()

    def test_executes_known_command(self, repl: REPL) -> None:
        """Should execute known command."""
        # Create a mock for the help command
        mock_help = MagicMock()
        repl.commands["help"] = mock_help

        with patch("pgslice.repl.PromptSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.prompt.side_effect = ["help", EOFError()]
            mock_session_class.return_value = mock_session

            with (
                patch("pgslice.repl.printy"),
                patch("pgslice.repl.FileHistory"),
            ):
                repl.start()
                mock_help.assert_called_once_with([])

    def test_handles_unknown_command(self, repl: REPL) -> None:
        """Should handle unknown command."""
        with patch("pgslice.repl.PromptSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.prompt.side_effect = ["unknowncmd", EOFError()]
            mock_session_class.return_value = mock_session

            with patch("pgslice.repl.printy") as mock_printy:
                with patch("pgslice.repl.FileHistory"):
                    repl.start()

                # Should have printed unknown command message
                calls = [str(c) for c in mock_printy.call_args_list]
                assert any("Unknown command" in str(c) for c in calls)

    def test_handles_shlex_parsing_error(self, repl: REPL) -> None:
        """Should handle shlex parsing error."""
        with patch("pgslice.repl.PromptSession") as mock_session_class:
            mock_session = MagicMock()
            # Unclosed quote will cause shlex.split to fail
            mock_session.prompt.side_effect = ['"unclosed', EOFError()]
            mock_session_class.return_value = mock_session

            with (
                patch("pgslice.repl.printy") as mock_printy,
                patch("pgslice.repl.FileHistory"),
            ):
                repl.start()

                # Should have printed error message
                calls = [str(c) for c in mock_printy.call_args_list]
                assert any("Error parsing command" in str(c) for c in calls)

    def test_handles_general_exception(self, repl: REPL) -> None:
        """Should handle general exceptions during command execution."""
        with patch("pgslice.repl.PromptSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.prompt.side_effect = ["help", EOFError()]
            mock_session_class.return_value = mock_session

            with (
                patch("pgslice.repl.printy"),
                patch("pgslice.repl.FileHistory"),
                patch.object(repl, "_cmd_help", side_effect=RuntimeError("Boom")),
            ):
                # Should not raise, but log error
                repl.start()
