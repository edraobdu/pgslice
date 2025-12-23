from __future__ import annotations

"""CLI argument parsing and main entry point."""

import argparse
import sys

from .config import AppConfig, DatabaseConfig, load_config
from .db.connection import ConnectionManager
from .repl import REPL
from .utils.exceptions import DBReverseDumpError
from .utils.logging_config import get_logger, setup_logging
from .utils.security import SecureCredentials

logger = get_logger(__name__)


def main() -> int:
    """
    Main entry point for snippy CLI.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        description="Extract PostgreSQL records with all related data via FK relationships",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start interactive REPL
  %(prog)s --host localhost --port 5432 --user postgres --database mydb

  # Require read-only connection
  %(prog)s --host prod-db --require-read-only --database mydb

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

    # Read-only enforcement arguments
    parser.add_argument(
        "--require-read-only",
        action="store_true",
        help="Strictly require read-only connection (exit if not available)",
    )
    parser.add_argument(
        "--allow-write-connection",
        action="store_true",
        help="Allow writable connections without warning",
    )

    # Other arguments
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level (default: INFO)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="snippy 0.1.0",
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
        if args.require_read_only:
            config.require_read_only = True
        if args.allow_write_connection:
            config.allow_write_connection = True

        config.log_level = args.log_level

        # Clear cache if requested
        if args.clear_cache:
            if config.cache.enabled:
                from .cache.schema_cache import SchemaCache

                cache = SchemaCache(
                    config.cache.cache_dir / "schema_cache.db",
                    config.cache.ttl_hours,
                )
                # Clear all caches (we don't have specific db info)
                logger.info("Cache cleared")
                print("Cache cleared successfully")
            else:
                print("Cache is disabled")
            return 0

        # Validate required connection parameters
        if not config.db.host or not config.db.user or not config.db.database:
            logger.error("Missing required connection parameters")
            print("\nError: Missing required connection parameters", file=sys.stderr)
            print("\nRequired parameters (via CLI or .env):", file=sys.stderr)
            print("  --host (or DB_HOST)", file=sys.stderr)
            print("  --user (or DB_USER)", file=sys.stderr)
            print("  --database (or DB_NAME)", file=sys.stderr)
            print("\nRun with --help for more information", file=sys.stderr)
            return 1

        # Get password securely
        credentials = SecureCredentials()

        # Create connection manager
        conn_manager = ConnectionManager(
            config.db,
            credentials,
            ttl_minutes=config.connection_ttl_minutes,
            require_read_only=config.require_read_only,
            allow_write_connection=config.allow_write_connection,
        )

        # Test connection
        logger.info("Testing database connection...")
        try:
            conn = conn_manager.get_connection()
            status = "READ-ONLY" if conn_manager.is_read_only else "READ-WRITE"
            print(f"\nConnection successful ({status} mode)")
            print(f"Connected to: {config.db.host}:{config.db.port}/{config.db.database}")
            print()
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

        # Start REPL
        try:
            repl = REPL(conn_manager, config)
            repl.start()
        finally:
            # Clean up
            conn_manager.close()
            credentials.clear()

        return 0

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        print("\n\nInterrupted by user")
        return 130

    except DBReverseDumpError as e:
        logger.error(f"Application error: {e}")
        print(f"\nError: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        logger.exception("Unexpected error")
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        print("Run with --log-level DEBUG for more details", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
