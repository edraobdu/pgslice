"""Interactive REPL for database dumping."""

from __future__ import annotations

import shlex
from datetime import datetime
from pathlib import Path

from printy import printy, raw_format
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from tabulate import tabulate

from .cache.schema_cache import SchemaCache
from .config import AppConfig
from .db.connection import ConnectionManager
from .db.schema import SchemaIntrospector
from .dumper.dump_service import DumpService
from .dumper.writer import SQLWriter
from .graph.models import TimeframeFilter
from .utils.exceptions import DBReverseDumpError, InvalidTimeframeError
from .utils.logging_config import get_logger

logger = get_logger(__name__)


class REPL:
    """Interactive REPL for database dumping."""

    def __init__(
        self, connection_manager: ConnectionManager, config: AppConfig
    ) -> None:
        """
        Initialize REPL.

        Args:
            connection_manager: Database connection manager
            config: Application configuration
        """
        self.conn_manager = connection_manager
        self.config = config
        self.session: PromptSession[str] | None = None

        # Initialize cache if enabled
        self.cache: SchemaCache | None = None
        if config.cache.enabled:
            cache_path = config.cache.cache_dir / "schema_cache.db"
            self.cache = SchemaCache(cache_path, config.cache.ttl_hours)

        # Command mapping
        self.commands = {
            "dump": self._cmd_dump,
            "help": self._cmd_help,
            "exit": self._cmd_exit,
            "quit": self._cmd_exit,
            "tables": self._cmd_list_tables,
            "describe": self._cmd_describe_table,
            "clear": self._cmd_clear_cache,
        }

    def start(self) -> None:
        """Start the interactive REPL."""
        # Create prompt session with history
        history_file = Path.home() / ".pgslice_history"
        self.session = PromptSession(
            history=FileHistory(str(history_file)),
            completer=WordCompleter(list(self.commands.keys()), ignore_case=True),
        )

        printy("[cB]pgslice REPL@")
        printy("Type 'help' for commands, 'exit' to quit\n")

        while True:
            try:
                # Get user input
                user_input = self.session.prompt("pgslice> ")

                if not user_input.strip():
                    continue

                # Parse command
                try:
                    parts = shlex.split(user_input)
                except ValueError as e:
                    printy(f"[r]Error parsing command: {e}@")
                    continue

                command = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []

                # Execute command
                if command in self.commands:
                    self.commands[command](args)
                else:
                    printy(f"[r]Unknown command: {command}@")
                    printy("Type 'help' for available commands")

            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            except Exception as e:
                logger.exception("Error executing command")
                printy(f"[r]Error: {e}@")

    def _cmd_dump(self, args: list[str]) -> None:
        """
        Execute dump command.

        Format: dump "table_name" pk_value[,pk_value,...] [--output file.sql] [--schema schema_name] [--truncate "table:col:start:end"] [--wide]
        """
        if len(args) < 2:
            printy('[y]Usage: dump "table_name" pk_value [options]@')
            printy("\nOptions:")
            printy("  --output FILE         Output file path")
            printy("  --schema SCHEMA       Schema name (default: public)")
            printy(
                "  --truncate SPEC       Truncate filter for related tables (table:column:start:end)"
            )
            printy(
                "  --wide                Wide mode: follow all relationships (default: strict)"
            )
            printy(
                "  --keep-pks            Keep original primary key values (default: remap auto-generated PKs)"
            )
            printy(
                "  --create-schema       Include CREATE DATABASE/SCHEMA/TABLE statements"
            )
            return

        table_name = args[0]
        pk_values_str = args[1]

        # Parse multiple PKs (comma-separated)
        pk_values = [v.strip() for v in pk_values_str.split(",")]

        # Parse optional flags
        output_file: str | None = None
        schema = self.config.db.schema
        timeframe_specs: list[str] = []
        wide_mode = False
        keep_pks = False  # Default: remap auto-generated PKs
        create_schema_ddl = self.config.create_schema  # Default from config

        i = 2
        while i < len(args):
            if args[i] == "--output" and i + 1 < len(args):
                output_file = args[i + 1]
                i += 2
            elif args[i] == "--schema" and i + 1 < len(args):
                schema = args[i + 1]
                i += 2
            elif args[i] == "--truncate" and i + 1 < len(args):
                timeframe_specs.append(args[i + 1])
                i += 2
            elif args[i] == "--wide":
                wide_mode = True
                i += 1
            elif args[i] == "--keep-pks":
                keep_pks = True
                i += 1
            elif args[i] == "--create-schema":
                create_schema_ddl = True
                i += 1
            else:
                i += 1

        # Parse timeframe filters
        timeframe_filters: list[TimeframeFilter] = []
        for spec in timeframe_specs:
            try:
                tf = self._parse_timeframe(spec)
                timeframe_filters.append(tf)
            except InvalidTimeframeError as e:
                printy(f"[r]Invalid truncate filter: {e}@")
                return

        # Execute dump
        pk_display = ", ".join(str(pk) for pk in pk_values)
        mode_display = "wide" if wide_mode else "strict"
        printy(
            f"\n[c]Dumping {schema}.{table_name} with PK(s): {pk_display} ({mode_display} mode)@"
        )

        if timeframe_filters:
            printy("\n[y]Truncate filters:@")
            for tf in timeframe_filters:
                printy(f"  - {tf}")

        try:
            # Use DumpService for the actual dump
            service = DumpService(self.conn_manager, self.config, show_progress=False)
            result = service.dump(
                table=table_name,
                pk_values=pk_values,
                schema=schema,
                wide_mode=wide_mode,
                keep_pks=keep_pks,
                create_schema=create_schema_ddl,
                timeframe_filters=timeframe_filters,
            )

            printy(f"\n[g]Found {result.record_count} related records@")

            # Output
            if output_file:
                SQLWriter.write_to_file(result.sql_content, output_file)
                printy(
                    f"[g]Wrote {result.record_count} INSERT statements to {output_file}@"
                )
            else:
                # Use default output path
                default_path = SQLWriter.get_default_output_path(
                    self.config.output_dir,
                    table_name,
                    pk_values[0],  # Use first PK for filename
                    schema,
                )
                SQLWriter.write_to_file(result.sql_content, str(default_path))
                printy(
                    f"[g]Wrote {result.record_count} INSERT statements to {default_path}@"
                )

        except DBReverseDumpError as e:
            printy(f"[r]Error: {e}@")
        except Exception as e:
            logger.exception("Error during dump")
            printy(f"[r]Unexpected error: {e}@")

    def _cmd_help(self, args: list[str]) -> None:
        """Display help information."""
        printy("\n[IB]Available Commands@\n")
        help_data = [
            [
                "dump TABLE PK [options]",
                "Extract a record and all related records\nOptions: --output FILE, --schema SCHEMA, --truncate SPEC",
            ],
            ["tables [--schema SCHEMA]", "List all tables in the database"],
            ["describe TABLE [--schema]", "Show table structure and relationships"],
            ["clear", "Clear schema cache"],
            ["help", "Show this help message"],
            ["exit, quit", "Exit the REPL"],
        ]
        print(
            tabulate(
                help_data,
                headers=[
                    raw_format("Command", flags="B"),
                    raw_format("Description", flags="B"),
                ],
                tablefmt="simple",
            )
        )
        printy("\n[y]Examples:@")
        print('  dump "users" 42 --output user_42.sql')
        print('  dump "users" 42,123,456 --output users.sql')
        print('  dump "users" 42 --truncate "orders:created_at:2024-01-01:2024-12-31"')
        print("  tables")
        print('  describe "users"')
        print()

    def _cmd_exit(self, args: list[str]) -> None:
        """Exit the REPL."""
        printy("\n[c]Goodbye!@")
        raise EOFError()

    def _cmd_list_tables(self, args: list[str]) -> None:
        """List all tables."""
        schema = self.config.db.schema

        # Parse --schema flag
        if len(args) >= 2 and args[0] == "--schema":
            schema = args[1]

        try:
            conn = self.conn_manager.get_connection()
            introspector = SchemaIntrospector(conn)
            tables = introspector.get_all_tables(schema)

            printy(f"\n[c]Tables in schema '{schema}':@\n")
            for table in tables:
                printy(f"  {table}")
            printy(f"\n[g]Total: {len(tables)} tables@\n")

        except Exception as e:
            printy(f"[r]Error: {e}@")

    def _cmd_describe_table(self, args: list[str]) -> None:
        """Describe table structure."""
        if not args:
            printy('[y]Usage: describe "table_name" [--schema schema]@')
            return

        table_name = args[0]
        schema = self.config.db.schema

        # Parse --schema flag
        if len(args) >= 3 and args[1] == "--schema":
            schema = args[2]

        try:
            conn = self.conn_manager.get_connection()
            introspector = SchemaIntrospector(conn)
            table = introspector.get_table_metadata(schema, table_name)

            printy(f"\n[c]Table: {table.full_name}@\n")

            # Columns
            printy("\n[cB]Columns@")
            col_data = []
            for col in table.columns:
                pk_indicator = "✓" if col.is_primary_key else ""
                col_data.append(
                    [
                        col.name,
                        col.data_type,
                        "YES" if col.nullable else "NO",
                        col.default or "",
                        pk_indicator,
                    ]
                )
            table_str = tabulate(
                col_data,
                headers=["Name", "Type", "Nullable", "Default", "PK"],
                tablefmt="simple",
            )
            printy(table_str)

            # Primary keys
            if table.primary_keys:
                printy(f"\n[g]Primary Keys:@ {', '.join(table.primary_keys)}")

            # Foreign keys outgoing
            if table.foreign_keys_outgoing:
                printy("\n[y]Foreign Keys (Outgoing):@")
                for fk in table.foreign_keys_outgoing:
                    printy(
                        f"  {fk.source_column} → {fk.target_table}.{fk.target_column}"
                    )

            # Foreign keys incoming
            if table.foreign_keys_incoming:
                printy("\n[b]Referenced By (Incoming):@")
                for fk in table.foreign_keys_incoming:
                    printy(
                        f"  {fk.source_table}.{fk.source_column} → {fk.target_column}"
                    )

            printy()

        except Exception as e:
            printy(f"[r]Error: {e}@")

    def _cmd_clear_cache(self, args: list[str]) -> None:
        """Clear schema cache."""
        if not self.config.cache.enabled:
            printy("[y]Cache is disabled@")
            return

        if self.cache:
            # Clear cache for current database
            self.cache.invalidate_cache(self.config.db.host, self.config.db.database)
            printy("[g]Cache cleared successfully@")
        else:
            printy("[y]Cache not initialized@")

    def _parse_timeframe(self, spec: str) -> TimeframeFilter:
        """
        Parse timeframe specification.

        Format: table:column:start_date:end_date
        Or: table:start_date:end_date (assumes 'created_at' column)

        Args:
            spec: Timeframe specification string

        Returns:
            TimeframeFilter object

        Raises:
            InvalidTimeframeError: If specification is invalid
        """
        parts = spec.split(":")

        if len(parts) == 3:
            # Format: table:start:end (assume created_at)
            table_name, start_str, end_str = parts
            column_name = "created_at"
        elif len(parts) == 4:
            # Format: table:column:start:end
            table_name, column_name, start_str, end_str = parts
        else:
            raise InvalidTimeframeError(
                f"Invalid timeframe format: {spec}. "
                "Expected: table:column:start:end or table:start:end"
            )

        # Parse dates
        try:
            start_date = datetime.fromisoformat(start_str)
        except ValueError as e:
            raise InvalidTimeframeError(f"Invalid start date: {start_str}") from e

        try:
            end_date = datetime.fromisoformat(end_str)
        except ValueError as e:
            raise InvalidTimeframeError(f"Invalid end date: {end_str}") from e

        return TimeframeFilter(
            table_name=table_name,
            column_name=column_name,
            start_date=start_date,
            end_date=end_date,
        )
