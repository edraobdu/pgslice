"""CLI argument parsing and main entry point."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import version as get_version

from printy import printy

from .config import AppConfig, load_config
from .db.connection import ConnectionManager
from .db.schema import SchemaIntrospector
from .dumper.dump_service import DumpService
from .dumper.writer import SQLWriter
from .operations import (
    describe_table,
    list_tables,
    parse_truncate_filters,
    print_tables,
)
from .repl import REPL
from .utils.exceptions import DBReverseDumpError, InvalidTimeframeError
from .utils.logging_config import get_logger, setup_logging
from .utils.security import SecureCredentials

logger = get_logger(__name__)


@dataclass
class MainTableTimeframe:
    """Timeframe filter for the main table."""

    column_name: str
    start_date: datetime
    end_date: datetime


def parse_main_timeframe(spec: str) -> MainTableTimeframe:
    """
    Parse main table timeframe specification.

    Format: column:start_date:end_date
    Example: created_at:2024-01-01:2024-12-31

    Args:
        spec: Timeframe specification string

    Returns:
        MainTableTimeframe object

    Raises:
        InvalidTimeframeError: If specification is invalid
    """
    parts = spec.split(":")
    if len(parts) != 3:
        raise InvalidTimeframeError(
            f"Invalid timeframe format: {spec}. "
            "Expected: column:start:end (e.g., created_at:2024-01-01:2024-12-31)"
        )

    column_name, start_str, end_str = parts

    try:
        start_date = datetime.fromisoformat(start_str)
    except ValueError as e:
        raise InvalidTimeframeError(f"Invalid start date: {start_str}") from e

    try:
        end_date = datetime.fromisoformat(end_str)
    except ValueError as e:
        raise InvalidTimeframeError(f"Invalid end date: {end_str}") from e

    return MainTableTimeframe(
        column_name=column_name,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_pks_by_timeframe(
    conn_manager: ConnectionManager,
    table: str,
    schema: str,
    timeframe: MainTableTimeframe,
) -> list[str]:
    """
    Fetch primary key values matching the timeframe filter.

    Args:
        conn_manager: Database connection manager
        table: Table name
        schema: Schema name
        timeframe: Timeframe filter

    Returns:
        List of primary key values as strings
    """
    printy("[y]Warning: Fetching records by timeframe may be slow for large tables@")

    conn = conn_manager.get_connection()
    introspector = SchemaIntrospector(conn)
    table_meta = introspector.get_table_metadata(schema, table)

    if not table_meta.primary_keys:
        raise DBReverseDumpError(f"Table {schema}.{table} has no primary key")

    # Use first primary key column for simplicity
    pk_col = table_meta.primary_keys[0]

    # Build and execute query
    query = f'''
        SELECT "{pk_col}"
        FROM "{schema}"."{table}"
        WHERE "{timeframe.column_name}" BETWEEN %s AND %s
    '''

    with conn.cursor() as cur:
        cur.execute(query, (timeframe.start_date, timeframe.end_date))
        rows = cur.fetchall()

    pk_values = [str(row[0]) for row in rows]
    printy(f"[c]Found {len(pk_values)} records matching timeframe@")
    return pk_values


def run_cli_dump(
    args: argparse.Namespace,
    config: AppConfig,
    conn_manager: ConnectionManager,
) -> int:
    """
    Execute dump in non-interactive CLI mode.

    Args:
        args: Parsed command line arguments
        config: Application configuration
        conn_manager: Database connection manager

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Parse truncate filters for related tables
    try:
        truncate_filters = parse_truncate_filters(args.truncate)
    except InvalidTimeframeError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    # Determine PK values - either from --pks or --timeframe
    if args.pks:
        pk_values = [v.strip() for v in args.pks.split(",")]
    elif args.timeframe:
        try:
            timeframe = parse_main_timeframe(args.timeframe)
        except InvalidTimeframeError as e:
            sys.stderr.write(f"Error: {e}\n")
            return 1

        pk_values = fetch_pks_by_timeframe(
            conn_manager, args.dump, args.schema, timeframe
        )
        if not pk_values:
            printy("[y]No records found matching the timeframe@")
            return 0
    else:
        # Should not reach here due to earlier validation
        sys.stderr.write("Error: --pks or --timeframe is required\n")
        return 1

    # Always show progress since we're writing to files (not stdout)
    # Users want to see progress for large datasets
    show_progress = True

    # Start timing
    start_time = time.time()

    # Wide mode warning
    if args.wide and show_progress:
        printy(
            "\n[gI]⚠ Note: Wide mode follows ALL relationships including self-referencing FKs.@"
        )
        printy("[gI]This may take longer and fetch more data.@\n")

    # Create dump service
    service = DumpService(conn_manager, config, show_progress=show_progress)

    # Execute dump
    result = service.dump(
        table=args.dump,
        pk_values=pk_values,
        schema=args.schema,
        wide_mode=args.wide,
        keep_pks=args.keep_pks,
        create_schema=args.create_schema,
        timeframe_filters=truncate_filters,
        show_graph=args.graph,
    )

    # Always write to file (never stdout)
    if args.output:
        output_path = args.output
    else:
        # Generate default filename like REPL mode does
        output_path = SQLWriter.get_default_output_path(
            config.output_dir,
            args.dump,  # table name
            pk_values[0] if pk_values else "multi",  # first PK for filename
            args.schema,
        )

    SQLWriter.write_to_file(result.sql_content, str(output_path))

    # Calculate and format elapsed time
    elapsed_time = time.time() - start_time
    if elapsed_time >= 60:
        time_str = f"{elapsed_time / 60:.1f}m"
    elif elapsed_time >= 1:
        time_str = f"{elapsed_time:.1f}s"
    else:
        time_str = f"{elapsed_time * 1000:.0f}ms"

    printy(
        f"[g]✓ Wrote {result.record_count} records to {output_path} (took {time_str})@"
    )

    return 0


def run_list_tables(conn_manager: ConnectionManager, schema: str) -> int:
    """
    List all tables in the specified schema.

    Args:
        conn_manager: Database connection manager
        schema: Schema name

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        tables = list_tables(conn_manager, schema)
        print_tables(tables, schema)
        return 0
    except Exception as e:
        printy(f"[r]Error: {e}@")
        return 1


def run_describe_table(
    conn_manager: ConnectionManager, schema: str, table_name: str
) -> int:
    """
    Describe table structure and relationships.

    Args:
        conn_manager: Database connection manager
        schema: Schema name
        table_name: Table name to describe

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        describe_table(conn_manager, schema, table_name)
        return 0
    except Exception as e:
        printy(f"[r]Error: {e}@")
        return 1


def main() -> int:
    """
    Main entry point for pgslice CLI.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        description="Extract PostgreSQL records with all related data via FK relationships",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dump to auto-generated file (shows progress)
  PGPASSWORD=xxx %(prog)s --host localhost --database mydb --dump users --pks 42

  # Dump by timeframe (instead of PKs)
  %(prog)s --host localhost --database mydb --dump orders --timeframe "created_at:2024-01-01:2024-12-31"

  # Dump to specific file with truncate filter for related tables
  %(prog)s --dump users --pks 1 --truncate "orders:created_at:2024-01-01:2024-12-31" --output user.sql

  # List all tables
  %(prog)s --host localhost --database mydb --tables

  # Describe table structure
  %(prog)s --host localhost --database mydb --describe users

  # Interactive REPL
  %(prog)s --host localhost --database mydb

  # Clear cache and exit
  %(prog)s --clear-cache
        """,
    )

    # Database connection arguments
    parser.add_argument(
        "--host",
        help="Database host (default: from .env or localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Database port (default: from .env or 5432)",
    )
    parser.add_argument(
        "--user",
        help="Database user (default: from .env)",
    )
    parser.add_argument(
        "--database",
        help="Database name (default: from .env)",
    )
    parser.add_argument(
        "--schema",
        default="public",
        help="Database schema (default: public)",
    )

    # Cache arguments
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable schema caching",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear schema cache and exit",
    )
    parser.add_argument(
        "--create-schema",
        action="store_true",
        help="Include DDL statements (CREATE DATABASE/SCHEMA/TABLE) in SQL dumps",
    )

    # Schema information arguments
    info_group = parser.add_argument_group("Schema Information")
    info_group.add_argument(
        "--tables",
        action="store_true",
        help="List all tables in the schema",
    )
    info_group.add_argument(
        "--describe",
        metavar="TABLE",
        help="Show table structure and relationships",
    )

    # Dump operation arguments (non-interactive CLI mode)
    dump_group = parser.add_argument_group("Dump Operation (CLI mode)")
    dump_group.add_argument(
        "--dump",
        "-d",
        help="Table name to dump (same as 'dump' command in REPL mode)",
    )

    # --pks and --timeframe are mutually exclusive ways to select records
    pk_source_group = dump_group.add_mutually_exclusive_group()
    pk_source_group.add_argument(
        "--pks",
        help="Primary key value(s), comma-separated (e.g., '42' or '1,2,3')",
    )
    pk_source_group.add_argument(
        "--timeframe",
        metavar="COLUMN:START:END",
        help="Filter main table by timeframe (e.g., 'created_at:2024-01-01:2024-12-31'). "
        "Mutually exclusive with --pks.",
    )

    dump_group.add_argument(
        "--wide",
        action="store_true",
        help="Wide mode: follow all relationships including self-referencing FKs",
    )
    dump_group.add_argument(
        "--keep-pks",
        action="store_true",
        help="Keep original primary key values (default: remap auto-generated PKs)",
    )
    dump_group.add_argument(
        "--graph",
        action="store_true",
        help="Display table relationship graph after dump completes",
    )
    dump_group.add_argument(
        "--truncate",
        action="append",
        help="Truncate filter for related tables (format: table:column:start:end). Can be repeated.",
    )
    dump_group.add_argument(
        "--output",
        "-o",
        help="Output file path (default: stdout)",
    )

    # Other arguments
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Log level (default: disabled unless specified)",
    )
    # Get version dynamically from package metadata
    try:
        pkg_version = get_version("pgslice")
    except Exception:
        # Fallback for development or if package not installed
        pkg_version = "development"

    parser.add_argument(
        "--version",
        action="version",
        version=f"pgslice {pkg_version}",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level)

    try:
        # Load configuration from environment
        config = load_config()

        # Override with CLI arguments
        if args.host:
            config.db.host = args.host
        if args.port:
            config.db.port = args.port
        if args.user:
            config.db.user = args.user
        if args.database:
            config.db.database = args.database
        if args.schema:
            config.db.schema = args.schema
        if args.no_cache:
            config.cache.enabled = False
        if args.create_schema:
            config.create_schema = True

        if args.log_level:
            config.log_level = args.log_level

        # Validate CLI dump mode arguments
        if args.dump and not args.pks and not args.timeframe:
            sys.stderr.write(
                "Error: --pks or --timeframe is required when using --dump\n"
            )
            return 1

        # Clear cache if requested
        if args.clear_cache:
            if config.cache.enabled:
                from .cache.schema_cache import SchemaCache

                SchemaCache(
                    config.cache.cache_dir / "schema_cache.db",
                    config.cache.ttl_hours,
                )
                # Clear all caches (we don't have specific db info)
                printy("[g]Cache cleared successfully@")
            else:
                pass
            return 0

        # Validate required connection parameters
        if not config.db.host or not config.db.user or not config.db.database:
            logger.error("Missing required connection parameters")
            return 1

        # Get password securely
        credentials = SecureCredentials()

        # Create connection manager
        conn_manager = ConnectionManager(
            config.db,
            credentials,
            ttl_minutes=config.connection_ttl_minutes,
        )

        # Test connection
        try:
            conn_manager.get_connection()
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

        # Route: Schema info, CLI dump mode, or REPL mode
        try:
            # Handle --tables
            if args.tables:
                return run_list_tables(conn_manager, args.schema)

            # Handle --describe
            if args.describe:
                return run_describe_table(conn_manager, args.schema, args.describe)

            if args.dump:
                # Non-interactive CLI dump mode
                return run_cli_dump(args, config, conn_manager)
            else:
                # Interactive REPL mode
                repl = REPL(conn_manager, config)
                repl.start()
                return 0
        finally:
            # Clean up
            conn_manager.close()
            credentials.clear()

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130

    except DBReverseDumpError as e:
        logger.error(f"Application error: {e}")
        return 1

    except Exception:
        logger.exception("Unexpected error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
