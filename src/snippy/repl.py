"""Interactive REPL for database dumping."""

from __future__ import annotations

import shlex
from datetime import datetime
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.table import Table as RichTable

from .cache.schema_cache import SchemaCache
from .config import AppConfig
from .db.connection import ConnectionManager
from .db.schema import SchemaIntrospector
from .dumper.dependency_sorter import DependencySorter
from .dumper.sql_generator import SQLGenerator
from .dumper.writer import SQLWriter
from .graph.models import TimeframeFilter
from .graph.traverser import RelationshipTraverser
from .graph.visited_tracker import VisitedTracker
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
        self.console = Console()
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
        """Start the REPL."""
        # Create prompt session with history
        history_file = Path.home() / ".snippy_history"
        self.session = PromptSession(
            history=FileHistory(str(history_file)),
            completer=WordCompleter(list(self.commands.keys()), ignore_case=True),
        )

        self.console.print("\n[bold cyan]snippy REPL[/bold cyan]")
        self.console.print("Type 'help' for commands, 'exit' to quit\n")

        while True:
            try:
                # Get user input
                user_input = self.session.prompt("db> ")

                if not user_input.strip():
                    continue

                # Parse command
                try:
                    parts = shlex.split(user_input)
                except ValueError as e:
                    self.console.print(f"[red]Error parsing command: {e}[/red]")
                    continue

                command = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []

                # Execute command
                if command in self.commands:
                    self.commands[command](args)
                else:
                    self.console.print(f"[red]Unknown command: {command}[/red]")
                    self.console.print("Type 'help' for available commands")

            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            except Exception as e:
                logger.exception("Error executing command")
                self.console.print(f"[red]Error: {e}[/red]")

    def _cmd_dump(self, args: list[str]) -> None:
        """
        Execute dump command.

        Format: dump "table_name" pk_value[,pk_value,...] [--output file.sql] [--schema schema_name] [--timeframe "table:col:start:end"] [--wide]
        """
        if len(args) < 2:
            self.console.print(
                '[yellow]Usage: dump "table_name" pk_value [options][/yellow]'
            )
            self.console.print("\nOptions:")
            self.console.print("  --output FILE         Output file path")
            self.console.print("  --schema SCHEMA       Schema name (default: public)")
            self.console.print(
                "  --timeframe SPEC      Timeframe filter (table:column:start:end)"
            )
            self.console.print(
                "  --wide                Wide mode: follow all relationships (default: strict)"
            )
            self.console.print(
                "  --keep-pks            Keep original primary key values (default: remap auto-generated PKs)"
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

        i = 2
        while i < len(args):
            if args[i] == "--output" and i + 1 < len(args):
                output_file = args[i + 1]
                i += 2
            elif args[i] == "--schema" and i + 1 < len(args):
                schema = args[i + 1]
                i += 2
            elif args[i] == "--timeframe" and i + 1 < len(args):
                timeframe_specs.append(args[i + 1])
                i += 2
            elif args[i] == "--wide":
                wide_mode = True
                i += 1
            elif args[i] == "--keep-pks":
                keep_pks = True
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
                self.console.print(f"[red]Invalid timeframe: {e}[/red]")
                return

        # Execute dump
        pk_display = ", ".join(str(pk) for pk in pk_values)
        mode_display = "wide" if wide_mode else "strict"
        self.console.print(
            f"\n[cyan]Dumping {schema}.{table_name} with PK(s): {pk_display} ({mode_display} mode)[/cyan]"
        )

        if timeframe_filters:
            self.console.print("\n[yellow]Timeframe filters:[/yellow]")
            for tf in timeframe_filters:
                self.console.print(f"  - {tf}")

        try:
            # Get connection
            conn = self.conn_manager.get_connection()

            # Create introspector
            introspector = SchemaIntrospector(conn)

            # Create traverser
            visited = VisitedTracker()
            traverser = RelationshipTraverser(
                conn, introspector, visited, timeframe_filters, wide_mode=wide_mode
            )

            # Traverse relationships
            if len(pk_values) == 1:
                records = traverser.traverse(
                    table_name, pk_values[0], schema, self.config.max_depth
                )
            else:
                records = traverser.traverse_multiple(
                    table_name, pk_values, schema, self.config.max_depth
                )

            self.console.print(f"\n[green]Found {len(records)} related records[/green]")

            # Sort by dependencies
            sorter = DependencySorter()
            sorted_records = sorter.sort(records)

            # Generate SQL
            generator = SQLGenerator(
                introspector, batch_size=self.config.sql_batch_size
            )
            sql = generator.generate_batch(sorted_records, keep_pks=keep_pks)

            # Output
            if output_file:
                SQLWriter.write_to_file(sql, output_file)
                self.console.print(
                    f"[green]Wrote {len(sorted_records)} INSERT statements to {output_file}[/green]"
                )
            else:
                self.console.print("\n[dim]--- SQL Output ---[/dim]")
                self.console.print("[dim]--- End SQL ---[/dim]\n")

        except DBReverseDumpError as e:
            self.console.print(f"[red]Error: {e}[/red]")
        except Exception as e:
            logger.exception("Error during dump")
            self.console.print(f"[red]Unexpected error: {e}[/red]")

    def _cmd_help(self, args: list[str]) -> None:
        """Display help information."""
        help_table = RichTable(title="Available Commands", show_header=True)
        help_table.add_column("Command", style="cyan", no_wrap=True)
        help_table.add_column("Description")

        help_table.add_row(
            "dump TABLE PK [options]",
            "Extract a record and all related records\n"
            "Options: --output FILE, --schema SCHEMA, --timeframe SPEC",
        )
        help_table.add_row(
            "tables [--schema SCHEMA]", "List all tables in the database"
        )
        help_table.add_row(
            "describe TABLE [--schema SCHEMA]", "Show table structure and relationships"
        )
        help_table.add_row("clear", "Clear schema cache")
        help_table.add_row("help", "Show this help message")
        help_table.add_row("exit, quit", "Exit the REPL")

        self.console.print("\n")
        self.console.print(help_table)
        self.console.print("\n[yellow]Examples:[/yellow]")
        self.console.print('  dump "users" 42 --output user_42.sql')
        self.console.print('  dump "users" 42,123,456 --output users.sql')
        self.console.print(
            '  dump "users" 42 --timeframe "orders:created_at:2024-01-01:2024-12-31"'
        )
        self.console.print("  tables")
        self.console.print('  describe "users"')
        self.console.print()

    def _cmd_exit(self, args: list[str]) -> None:
        """Exit the REPL."""
        self.console.print("\n[cyan]Goodbye![/cyan]")
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

            self.console.print(f"\n[cyan]Tables in schema '{schema}':[/cyan]\n")
            for table in tables:
                self.console.print(f"  {table}")
            self.console.print(f"\n[green]Total: {len(tables)} tables[/green]\n")

        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")

    def _cmd_describe_table(self, args: list[str]) -> None:
        """Describe table structure."""
        if not args:
            self.console.print(
                '[yellow]Usage: describe "table_name" [--schema schema][/yellow]'
            )
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

            self.console.print(f"\n[cyan]Table: {table.full_name}[/cyan]\n")

            # Columns
            col_table = RichTable(title="Columns", show_header=True)
            col_table.add_column("Name", style="cyan")
            col_table.add_column("Type", style="yellow")
            col_table.add_column("Nullable", style="magenta")
            col_table.add_column("Default")
            col_table.add_column("PK", style="green")

            for col in table.columns:
                col_table.add_row(
                    col.name,
                    col.data_type,
                    "YES" if col.nullable else "NO",
                    col.default or "",
                    "✓" if col.is_primary_key else "",
                )

            self.console.print(col_table)

            # Primary keys
            if table.primary_keys:
                self.console.print(
                    f"\n[green]Primary Keys:[/green] {', '.join(table.primary_keys)}"
                )

            # Foreign keys outgoing
            if table.foreign_keys_outgoing:
                self.console.print("\n[yellow]Foreign Keys (Outgoing):[/yellow]")
                for fk in table.foreign_keys_outgoing:
                    self.console.print(
                        f"  {fk.source_column} → {fk.target_table}.{fk.target_column}"
                    )

            # Foreign keys incoming
            if table.foreign_keys_incoming:
                self.console.print("\n[blue]Referenced By (Incoming):[/blue]")
                for fk in table.foreign_keys_incoming:
                    self.console.print(
                        f"  {fk.source_table}.{fk.source_column} → {fk.target_column}"
                    )

            self.console.print()

        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")

    def _cmd_clear_cache(self, args: list[str]) -> None:
        """Clear schema cache."""
        if not self.config.cache.enabled:
            self.console.print("[yellow]Cache is disabled[/yellow]")
            return

        if self.cache:
            # Clear cache for current database
            self.cache.invalidate_cache(self.config.db.host, self.config.db.database)
            self.console.print("[green]Cache cleared successfully[/green]")
        else:
            self.console.print("[yellow]Cache not initialized[/yellow]")

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
