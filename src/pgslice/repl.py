"""Interactive REPL for database dumping."""

from __future__ import annotations

import shlex
import time
from pathlib import Path

from printy import printy, raw
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from tabulate import tabulate

from .cache.schema_cache import SchemaCache
from .config import AppConfig
from .db.connection import ConnectionManager
from .dumper.dump_service import DumpService
from .dumper.writer import SQLWriter
from .graph.models import TimeframeFilter
from .operations import describe_table, list_tables, parse_truncate_filter, print_tables
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
            printy("  --graph               Display relationship graph after dump")
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
        show_graph = False

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
            elif args[i] == "--graph":
                show_graph = True
                i += 1
            else:
                i += 1

        # Parse timeframe filters using shared function
        timeframe_filters: list[TimeframeFilter] = []
        for spec in timeframe_specs:
            try:
                tf = parse_truncate_filter(spec)
                timeframe_filters.append(tf)
            except InvalidTimeframeError as e:
                printy(f"[r]Invalid truncate filter: {e}@")
                return

        # Execute dump
        pk_display = ", ".join(str(pk) for pk in pk_values)
        mode_display = "wide" if wide_mode else "strict"
        printy(
            f"\n  [c]Dumping {schema}.{table_name} with PK(s): {pk_display} ({mode_display} mode)@\n"
        )

        # Wide mode warning
        if wide_mode:
            printy(
                "\n[gI]⚠ Note: Wide mode follows ALL relationships including self-referencing FKs.@"
            )
            printy("[gI]This may take longer and fetch more data.@\n")

        if timeframe_filters:
            printy("  [y]Truncate filters:@")
            for tf in timeframe_filters:
                printy(f"    - {tf}")
            printy("")  # Empty line after filters

        try:
            # Start timing
            start_time = time.time()

            # Use DumpService for the actual dump
            # REPL always writes to files, so progress bar is safe to show
            service = DumpService(self.conn_manager, self.config, show_progress=True)
            result = service.dump(
                table=table_name,
                pk_values=pk_values,
                schema=schema,
                wide_mode=wide_mode,
                keep_pks=keep_pks,
                create_schema=create_schema_ddl,
                timeframe_filters=timeframe_filters,
                show_graph=show_graph,
            )

            # Calculate and format elapsed time
            elapsed_time = time.time() - start_time
            if elapsed_time >= 60:
                time_str = f"{elapsed_time / 60:.1f}m"
            elif elapsed_time >= 1:
                time_str = f"{elapsed_time:.1f}s"
            else:
                time_str = f"{elapsed_time * 1000:.0f}ms"

            printy(f"\n  [g]✓ Found {result.record_count} related records@")

            # Output
            if output_file:
                SQLWriter.write_to_file(result.sql_content, output_file)
                printy(
                    f"  [g]✓ Wrote {result.record_count} INSERT statements to {output_file} (took {time_str})@\n"
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
                    f"  [g]✓ Wrote {result.record_count} INSERT statements to {default_path} (took {time_str})@\n"
                )

        except DBReverseDumpError as e:
            printy(f"\n  [r]Error: {e}@\n")
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
                    raw("Command", flags="B"),
                    raw("Description", flags="B"),
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
            tables = list_tables(self.conn_manager, schema)
            print_tables(tables, schema)
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
            describe_table(self.conn_manager, schema, table_name)
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
