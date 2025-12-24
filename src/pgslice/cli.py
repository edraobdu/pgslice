"""CLI argument parsing and main entry point."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version as get_version

from .config import load_config
from .db.connection import ConnectionManager
from .repl import REPL
from .utils.exceptions import DBReverseDumpError
from .utils.logging_config import get_logger, setup_logging
from .utils.security import SecureCredentials

logger = get_logger(__name__)


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

    # Other arguments
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level (default: INFO)",
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

        config.log_level = args.log_level

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
        return 130

    except DBReverseDumpError as e:
        logger.error(f"Application error: {e}")
        return 1

    except Exception:
        logger.exception("Unexpected error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
