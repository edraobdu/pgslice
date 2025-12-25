"""Tests for pgslice.repl module."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pgslice.config import AppConfig, CacheConfig, DatabaseConfig
from pgslice.repl import REPL
from pgslice.utils.exceptions import InvalidTimeframeError


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
        with patch("pgslice.repl.SchemaIntrospector") as mock_introspector:
            mock_instance = MagicMock()
            mock_instance.get_all_tables.return_value = ["users", "orders"]
            mock_introspector.return_value = mock_instance

            with patch("pgslice.repl.printy"):
                repl._cmd_list_tables([])

            mock_instance.get_all_tables.assert_called_once_with("public")

    def test_lists_tables_with_custom_schema(
        self, repl: REPL, mock_connection_manager: MagicMock
    ) -> None:
        """Should list tables in custom schema."""
        with patch("pgslice.repl.SchemaIntrospector") as mock_introspector:
            mock_instance = MagicMock()
            mock_instance.get_all_tables.return_value = ["custom_table"]
            mock_introspector.return_value = mock_instance

            with patch("pgslice.repl.printy"):
                repl._cmd_list_tables(["--schema", "custom"])

            mock_instance.get_all_tables.assert_called_once_with("custom")

    def test_handles_error(
        self, repl: REPL, mock_connection_manager: MagicMock
    ) -> None:
        """Should handle errors gracefully."""
        with patch("pgslice.repl.SchemaIntrospector") as mock_introspector:
            mock_introspector.side_effect = Exception("Connection error")

            with patch("pgslice.repl.printy"):
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

        with patch("pgslice.repl.SchemaIntrospector") as mock_introspector:
            mock_instance = MagicMock()
            mock_instance.get_table_metadata.return_value = mock_table
            mock_introspector.return_value = mock_instance

            with (
                patch("pgslice.repl.printy"),
                patch("pgslice.repl.tabulate", return_value=""),
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

        with patch("pgslice.repl.SchemaIntrospector") as mock_introspector:
            mock_instance = MagicMock()
            mock_instance.get_table_metadata.return_value = mock_table
            mock_introspector.return_value = mock_instance

            with (
                patch("pgslice.repl.printy"),
                patch("pgslice.repl.tabulate", return_value=""),
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
        """Should execute dump command."""
        from pgslice.graph.models import Column, RecordData, RecordIdentifier, Table

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
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_record = RecordData(
            identifier=RecordIdentifier(
                schema_name="public",
                table_name="users",
                pk_values=("42",),
            ),
            data={"id": 42},
        )

        with patch("pgslice.repl.SchemaIntrospector") as mock_introspector:
            mock_intro_instance = MagicMock()
            mock_intro_instance.get_table_metadata.return_value = mock_table
            mock_introspector.return_value = mock_intro_instance

            with patch("pgslice.repl.RelationshipTraverser") as mock_traverser:
                mock_trav_instance = MagicMock()
                mock_trav_instance.traverse.return_value = {mock_record}
                mock_traverser.return_value = mock_trav_instance

                with patch("pgslice.repl.DependencySorter") as mock_sorter:
                    mock_sorter_instance = MagicMock()
                    mock_sorter_instance.sort.return_value = [mock_record]
                    mock_sorter.return_value = mock_sorter_instance

                    with patch("pgslice.repl.SQLGenerator") as mock_generator:
                        mock_gen_instance = MagicMock()
                        mock_gen_instance.generate_batch.return_value = (
                            "INSERT INTO users (id) VALUES (42);"
                        )
                        mock_generator.return_value = mock_gen_instance

                        with patch("pgslice.repl.SQLWriter") as mock_writer:
                            mock_writer.get_default_output_path.return_value = (
                                tmp_path / "users_42.sql"
                            )

                            with patch("pgslice.repl.printy"):
                                repl._cmd_dump(["users", "42"])

                            mock_trav_instance.traverse.assert_called_once()
                            mock_sorter_instance.sort.assert_called_once()
                            mock_gen_instance.generate_batch.assert_called_once()

    def test_executes_dump_with_output_file(
        self, repl: REPL, mock_connection_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Should execute dump with specified output file."""
        from pgslice.graph.models import Column, RecordData, RecordIdentifier, Table

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
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_record = RecordData(
            identifier=RecordIdentifier(
                schema_name="public",
                table_name="users",
                pk_values=("42",),
            ),
            data={"id": 42},
        )

        output_file = str(tmp_path / "custom_output.sql")

        with patch("pgslice.repl.SchemaIntrospector") as mock_introspector:
            mock_intro_instance = MagicMock()
            mock_intro_instance.get_table_metadata.return_value = mock_table
            mock_introspector.return_value = mock_intro_instance

            with patch("pgslice.repl.RelationshipTraverser") as mock_traverser:
                mock_trav_instance = MagicMock()
                mock_trav_instance.traverse.return_value = {mock_record}
                mock_traverser.return_value = mock_trav_instance

                with patch("pgslice.repl.DependencySorter") as mock_sorter:
                    mock_sorter_instance = MagicMock()
                    mock_sorter_instance.sort.return_value = [mock_record]
                    mock_sorter.return_value = mock_sorter_instance

                    with patch("pgslice.repl.SQLGenerator") as mock_generator:
                        mock_gen_instance = MagicMock()
                        mock_gen_instance.generate_batch.return_value = (
                            "INSERT INTO users (id) VALUES (42);"
                        )
                        mock_generator.return_value = mock_gen_instance

                        with patch("pgslice.repl.SQLWriter") as mock_writer:
                            with patch("pgslice.repl.printy"):
                                repl._cmd_dump(["users", "42", "--output", output_file])

                            mock_writer.write_to_file.assert_called_once()
                            call_args = mock_writer.write_to_file.call_args
                            assert call_args[0][1] == output_file

    def test_executes_dump_with_multiple_pks(
        self, repl: REPL, mock_connection_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Should execute dump with multiple PKs."""
        from pgslice.graph.models import RecordData, RecordIdentifier

        mock_record = RecordData(
            identifier=RecordIdentifier(
                schema_name="public",
                table_name="users",
                pk_values=("42",),
            ),
            data={"id": 42},
        )

        with (
            patch("pgslice.repl.SchemaIntrospector"),
            patch("pgslice.repl.RelationshipTraverser") as mock_traverser,
            patch("pgslice.repl.DependencySorter") as mock_sorter,
            patch("pgslice.repl.SQLGenerator") as mock_generator,
            patch("pgslice.repl.SQLWriter") as mock_writer,
            patch("pgslice.repl.printy"),
        ):
            mock_trav_instance = MagicMock()
            mock_trav_instance.traverse_multiple.return_value = {mock_record}
            mock_traverser.return_value = mock_trav_instance

            mock_sorter_instance = MagicMock()
            mock_sorter_instance.sort.return_value = [mock_record]
            mock_sorter.return_value = mock_sorter_instance

            mock_gen_instance = MagicMock()
            mock_gen_instance.generate_batch.return_value = "INSERT..."
            mock_generator.return_value = mock_gen_instance

            mock_writer.get_default_output_path.return_value = tmp_path / "out.sql"

            repl._cmd_dump(["users", "42,43,44"])

            mock_trav_instance.traverse_multiple.assert_called_once()

    def test_handles_wide_mode_flag(
        self, repl: REPL, mock_connection_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Should handle --wide flag."""
        from pgslice.graph.models import RecordData, RecordIdentifier

        mock_record = RecordData(
            identifier=RecordIdentifier(
                schema_name="public",
                table_name="users",
                pk_values=("42",),
            ),
            data={"id": 42},
        )

        with (
            patch("pgslice.repl.SchemaIntrospector"),
            patch("pgslice.repl.RelationshipTraverser") as mock_traverser,
            patch("pgslice.repl.DependencySorter") as mock_sorter,
            patch("pgslice.repl.SQLGenerator") as mock_generator,
            patch("pgslice.repl.SQLWriter") as mock_writer,
            patch("pgslice.repl.printy"),
        ):
            mock_trav_instance = MagicMock()
            mock_trav_instance.traverse.return_value = {mock_record}
            mock_traverser.return_value = mock_trav_instance

            mock_sorter_instance = MagicMock()
            mock_sorter_instance.sort.return_value = [mock_record]
            mock_sorter.return_value = mock_sorter_instance

            mock_gen_instance = MagicMock()
            mock_gen_instance.generate_batch.return_value = "INSERT..."
            mock_generator.return_value = mock_gen_instance

            mock_writer.get_default_output_path.return_value = tmp_path / "out.sql"

            repl._cmd_dump(["users", "42", "--wide"])

            # Check that wide_mode=True was passed to traverser
            call_args = mock_traverser.call_args
            assert call_args[1]["wide_mode"] is True

    def test_handles_timeframe_flag(
        self, repl: REPL, mock_connection_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Should handle --timeframe flag."""
        from pgslice.graph.models import RecordData, RecordIdentifier

        mock_record = RecordData(
            identifier=RecordIdentifier(
                schema_name="public",
                table_name="users",
                pk_values=("42",),
            ),
            data={"id": 42},
        )

        with (
            patch("pgslice.repl.SchemaIntrospector"),
            patch("pgslice.repl.RelationshipTraverser") as mock_traverser,
            patch("pgslice.repl.DependencySorter") as mock_sorter,
            patch("pgslice.repl.SQLGenerator") as mock_generator,
            patch("pgslice.repl.SQLWriter") as mock_writer,
            patch("pgslice.repl.printy"),
        ):
            mock_trav_instance = MagicMock()
            mock_trav_instance.traverse.return_value = {mock_record}
            mock_traverser.return_value = mock_trav_instance

            mock_sorter_instance = MagicMock()
            mock_sorter_instance.sort.return_value = [mock_record]
            mock_sorter.return_value = mock_sorter_instance

            mock_gen_instance = MagicMock()
            mock_gen_instance.generate_batch.return_value = "INSERT..."
            mock_generator.return_value = mock_gen_instance

            mock_writer.get_default_output_path.return_value = tmp_path / "out.sql"

            repl._cmd_dump(
                [
                    "users",
                    "42",
                    "--timeframe",
                    "orders:created_at:2024-01-01:2024-12-31",
                ]
            )

            # Check that timeframe was passed
            call_args = mock_traverser.call_args
            assert len(call_args[0][3]) == 1  # timeframe_filters

    def test_handles_invalid_timeframe(self, repl: REPL) -> None:
        """Should handle invalid timeframe."""
        with patch("pgslice.repl.printy"):
            # Invalid format
            repl._cmd_dump(["users", "42", "--timeframe", "invalid"])

    def test_handles_dump_error(
        self, repl: REPL, mock_connection_manager: MagicMock
    ) -> None:
        """Should handle errors during dump."""
        from pgslice.utils.exceptions import RecordNotFoundError

        with patch("pgslice.repl.SchemaIntrospector") as mock_introspector:
            mock_introspector.side_effect = RecordNotFoundError("Not found")

            with patch("pgslice.repl.printy"):
                # Should not raise
                repl._cmd_dump(["users", "42"])


class TestParseTimeframe(TestREPL):
    """Tests for _parse_timeframe method."""

    def test_parses_four_part_format(self, repl: REPL) -> None:
        """Should parse table:column:start:end format."""
        result = repl._parse_timeframe("orders:created_at:2024-01-01:2024-12-31")

        assert result.table_name == "orders"
        assert result.column_name == "created_at"
        assert result.start_date == datetime(2024, 1, 1)
        assert result.end_date == datetime(2024, 12, 31)

    def test_parses_three_part_format(self, repl: REPL) -> None:
        """Should parse table:start:end format with default column."""
        result = repl._parse_timeframe("orders:2024-01-01:2024-12-31")

        assert result.table_name == "orders"
        assert result.column_name == "created_at"
        assert result.start_date == datetime(2024, 1, 1)
        assert result.end_date == datetime(2024, 12, 31)

    def test_raises_for_invalid_format(self, repl: REPL) -> None:
        """Should raise for invalid format."""
        with pytest.raises(InvalidTimeframeError, match="Invalid timeframe format"):
            repl._parse_timeframe("orders")

        with pytest.raises(InvalidTimeframeError, match="Invalid timeframe format"):
            repl._parse_timeframe("a:b:c:d:e")

    def test_raises_for_invalid_start_date(self, repl: REPL) -> None:
        """Should raise for invalid start date."""
        with pytest.raises(InvalidTimeframeError, match="Invalid start date"):
            repl._parse_timeframe("orders:invalid:2024-12-31")

    def test_raises_for_invalid_end_date(self, repl: REPL) -> None:
        """Should raise for invalid end date."""
        with pytest.raises(InvalidTimeframeError, match="Invalid end date"):
            repl._parse_timeframe("orders:2024-01-01:invalid")


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
