"""Configuration management for pgslice."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class DatabaseConfig:
    """Database connection configuration."""

    host: str
    port: int
    database: str
    user: str
    schema: str = "public"


@dataclass
class CacheConfig:
    """Cache configuration."""

    cache_dir: Path
    ttl_hours: int = 24
    enabled: bool = True

    def __post_init__(self) -> None:
        """Ensure cache directory exists."""
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class AppConfig:
    """Application configuration."""

    db: DatabaseConfig
    cache: CacheConfig
    connection_ttl_minutes: int = 30
    max_depth: int | None = None
    log_level: str = "INFO"
    sql_batch_size: int = 100
    output_dir: Path = Path.home() / ".pgslice" / "dumps"
    create_schema: bool = False


def load_config() -> AppConfig:
    """
    Load configuration from environment variables.

    Returns:
        Application configuration

    Environment variables:
        DB_HOST: Database host
        DB_PORT: Database port
        DB_NAME: Database name
        DB_USER: Database user
        DB_SCHEMA: Database schema (default: public)
        CACHE_ENABLED: Enable caching (default: true)
        CACHE_TTL_HOURS: Cache TTL in hours (default: 24)
        PGSLICE_CACHE_DIR: Cache directory
        CONNECTION_TTL_MINUTES: Connection TTL in minutes (default: 30)
        MAX_DEPTH: Maximum traversal depth (optional)
        LOG_LEVEL: Log level (default: INFO)
        SQL_BATCH_SIZE: Number of rows per INSERT statement (default: 100, 0 for unlimited)
    """
    load_dotenv()

    # Determine cache directory
    cache_dir_str = os.getenv(
        "PGSLICE_CACHE_DIR",
        str(Path.home() / ".cache" / "pgslice"),
    )
    cache_dir = Path(cache_dir_str).expanduser()

    return AppConfig(
        db=DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", ""),
            user=os.getenv("DB_USER", ""),
            schema=os.getenv("DB_SCHEMA", "public"),
        ),
        cache=CacheConfig(
            cache_dir=cache_dir,
            ttl_hours=int(os.getenv("CACHE_TTL_HOURS", "24")),
            enabled=os.getenv("CACHE_ENABLED", "true").lower() == "true",
        ),
        connection_ttl_minutes=int(os.getenv("CONNECTION_TTL_MINUTES", "30")),
        max_depth=int(max_depth_str)
        if (max_depth_str := os.getenv("MAX_DEPTH"))
        else None,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        sql_batch_size=int(os.getenv("SQL_BATCH_SIZE", "100")),
        output_dir=Path(
            os.getenv("PGSLICE_OUTPUT_DIR", str(Path.home() / ".pgslice" / "dumps"))
        ).expanduser(),
    )
