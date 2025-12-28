"""CLI argument parsing and main entry point."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from importlib.metadata import version as get_version

from .config import AppConfig, load_config
from .db.connection import ConnectionManager
from .dumper.dump_service import DumpService
from .dumper.writer import SQLWriter
from .graph.models import TimeframeFilter
from .repl import REPL
from .utils.exceptions import DBReverseDumpError, InvalidTimeframeError
from .utils.logging_config import get_logger, setup_logging
from .utils.security import SecureCredentials

logger = get_logger(__name__)


def parse_timeframe(spec: str) -> TimeframeFilter:
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


def parse_timeframes(specs: list[str] | None) -> list[TimeframeFilter]:
    """
    Parse multiple timeframe specifications.

    Args:
        specs: List of timeframe specification strings

    Returns:
        List of TimeframeFilter objects
    """
    if not specs:
        return []

    filters = []
    for spec in specs:
        filters.append(parse_timeframe(spec))
    return filters


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
    # Parse timeframe filters
    try:
        timeframe_filters = parse_timeframes(args.timeframe)
    except InvalidTimeframeError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    # Show progress only if stderr is a TTY (not piped)
    show_progress = sys.stderr.isatty()

    # Create dump service
    service = DumpService(conn_manager, config, show_progress=show_progress)

    # Parse PK values
    pk_values = [v.strip() for v in args.pks.split(",")]

    # Execute dump
    result = service.dump(
        table=args.table,
        pk_values=pk_values,
        schema=args.schema,
        wide_mode=args.wide,
        keep_pks=args.keep_pks,
        create_schema=args.create_schema,
        timeframe_filters=timeframe_filters,
    )

    # Output SQL
    if args.output:
        SQLWriter.write_to_file(result.sql_content, args.output)
        sys.stderr.write(f"Wrote {result.record_count} records to {args.output}\n")
    else:
        SQLWriter.write_to_stdout(result.sql_content)

    return 0


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
  # CLI mode: dump to stdout (recommended)
  PGPASSWORD=xxx %(prog)s --host localhost --database mydb --table users --pks 42

  # CLI mode: dump to file
  %(prog)s --host localhost --database mydb --table users --pks 1,2,3 --output users.sql

  # CLI mode: wide mode with DDL
  %(prog)s --host localhost --database mydb --table customer --pks 42 --wide --create-schema

  # Interactive REPL (deprecated)
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

    # Dump operation arguments (non-interactive CLI mode)
    dump_group = parser.add_argument_group("Dump Operation (CLI mode)")
    dump_group.add_argument(
        "--table",
        help="Table name to dump (enables non-interactive CLI mode)",
    )
    dump_group.add_argument(
        "--pks",
        help="Primary key value(s), comma-separated (e.g., '42' or '1,2,3')",
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
        "--timeframe",
        action="append",
        help="Timeframe filter (format: table:column:start:end). Can be repeated.",
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
        if args.table and not args.pks:
            sys.stderr.write("Error: --pks is required when using --table\n")
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
                logger.info("Cache cleared")
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
        logger.info("Testing database connection...")
        try:
            conn_manager.get_connection()
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

        # Route: CLI dump mode vs REPL mode
        try:
            if args.table:
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
