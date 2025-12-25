"""Tests for pgslice.config module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pgslice.config import AppConfig, CacheConfig, DatabaseConfig, load_config


class TestDatabaseConfig:
    """Tests for DatabaseConfig dataclass."""

    def test_create_basic_config(self) -> None:
        """Can create a basic database configuration."""
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
        )
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "test_db"
        assert config.user == "test_user"

    def test_default_schema(self) -> None:
        """Default schema should be 'public'."""
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
        )
        assert config.schema == "public"

    def test_custom_schema(self) -> None:
        """Can specify custom schema."""
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
            schema="custom_schema",
        )
        assert config.schema == "custom_schema"


class TestCacheConfig:
    """Tests for CacheConfig dataclass."""

    def test_create_basic_config(self, tmp_path: Path) -> None:
        """Can create a basic cache configuration."""
        cache_dir = tmp_path / "cache"
        config = CacheConfig(
            cache_dir=cache_dir,
            enabled=True,
        )
        assert config.cache_dir == cache_dir
        assert config.enabled is True
        assert config.ttl_hours == 24  # Default

    def test_default_values(self, tmp_path: Path) -> None:
        """Should have correct default values."""
        cache_dir = tmp_path / "cache"
        config = CacheConfig(cache_dir=cache_dir)
        assert config.ttl_hours == 24
        assert config.enabled is True

    def test_creates_cache_directory(self, tmp_path: Path) -> None:
        """Should create cache directory if enabled."""
        cache_dir = tmp_path / "new_cache_dir"
        assert not cache_dir.exists()

        CacheConfig(cache_dir=cache_dir, enabled=True)
        assert cache_dir.exists()

    def test_does_not_create_dir_when_disabled(self, tmp_path: Path) -> None:
        """Should not create cache directory when disabled."""
        cache_dir = tmp_path / "disabled_cache"
        assert not cache_dir.exists()

        CacheConfig(cache_dir=cache_dir, enabled=False)
        assert not cache_dir.exists()

    def test_custom_ttl(self, tmp_path: Path) -> None:
        """Can specify custom TTL."""
        config = CacheConfig(
            cache_dir=tmp_path / "cache",
            ttl_hours=48,
        )
        assert config.ttl_hours == 48


class TestAppConfig:
    """Tests for AppConfig dataclass."""

    def test_create_basic_config(self, tmp_path: Path) -> None:
        """Can create a basic app configuration."""
        db_config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
        )
        cache_config = CacheConfig(
            cache_dir=tmp_path / "cache",
            enabled=True,
        )
        config = AppConfig(db=db_config, cache=cache_config)

        assert config.db == db_config
        assert config.cache == cache_config

    def test_default_values(self, tmp_path: Path) -> None:
        """Should have correct default values."""
        db_config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
        )
        cache_config = CacheConfig(cache_dir=tmp_path / "cache")
        config = AppConfig(db=db_config, cache=cache_config)

        assert config.connection_ttl_minutes == 30
        assert config.max_depth is None
        assert config.log_level == "INFO"
        assert config.sql_batch_size == 100

    def test_custom_values(self, tmp_path: Path) -> None:
        """Can specify custom values."""
        db_config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
        )
        cache_config = CacheConfig(cache_dir=tmp_path / "cache")
        config = AppConfig(
            db=db_config,
            cache=cache_config,
            connection_ttl_minutes=60,
            max_depth=5,
            log_level="DEBUG",
            sql_batch_size=200,
        )

        assert config.connection_ttl_minutes == 60
        assert config.max_depth == 5
        assert config.log_level == "DEBUG"
        assert config.sql_batch_size == 200


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_with_defaults(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Should load config with default values when env vars not set."""
        # Clear all relevant env vars
        env_vars = [
            "DB_HOST",
            "DB_PORT",
            "DB_NAME",
            "DB_USER",
            "DB_SCHEMA",
            "CACHE_ENABLED",
            "CACHE_TTL_HOURS",
            "PGSLICE_CACHE_DIR",
            "CONNECTION_TTL_MINUTES",
            "MAX_DEPTH",
            "LOG_LEVEL",
            "SQL_BATCH_SIZE",
            "PGSLICE_OUTPUT_DIR",
        ]
        for var in env_vars:
            monkeypatch.delenv(var, raising=False)

        # Patch dotenv to not load actual .env file
        with patch("pgslice.config.load_dotenv"):
            config = load_config()

        assert config.db.host == "localhost"
        assert config.db.port == 5432
        assert config.db.database == ""
        assert config.db.user == ""
        assert config.db.schema == "public"
        assert config.cache.enabled is True
        assert config.cache.ttl_hours == 24
        assert config.connection_ttl_minutes == 30
        assert config.max_depth is None
        assert config.log_level == "INFO"
        assert config.sql_batch_size == 100

    def test_load_from_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should load config from environment variables."""
        monkeypatch.setenv("DB_HOST", "db.example.com")
        monkeypatch.setenv("DB_PORT", "5433")
        monkeypatch.setenv("DB_NAME", "prod_db")
        monkeypatch.setenv("DB_USER", "app_user")
        monkeypatch.setenv("DB_SCHEMA", "app")
        monkeypatch.setenv("CACHE_ENABLED", "false")
        monkeypatch.setenv("CACHE_TTL_HOURS", "48")
        monkeypatch.setenv("CONNECTION_TTL_MINUTES", "60")
        monkeypatch.setenv("MAX_DEPTH", "10")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("SQL_BATCH_SIZE", "500")

        # Patch dotenv to not load actual .env file
        with patch("pgslice.config.load_dotenv"):
            config = load_config()

        assert config.db.host == "db.example.com"
        assert config.db.port == 5433
        assert config.db.database == "prod_db"
        assert config.db.user == "app_user"
        assert config.db.schema == "app"
        assert config.cache.enabled is False
        assert config.cache.ttl_hours == 48
        assert config.connection_ttl_minutes == 60
        assert config.max_depth == 10
        assert config.log_level == "DEBUG"
        assert config.sql_batch_size == 500

    def test_max_depth_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MAX_DEPTH should be None when not set."""
        monkeypatch.delenv("MAX_DEPTH", raising=False)

        with patch("pgslice.config.load_dotenv"):
            config = load_config()

        assert config.max_depth is None

    def test_cache_enabled_parsing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CACHE_ENABLED should be parsed as boolean."""
        with patch("pgslice.config.load_dotenv"):
            monkeypatch.setenv("CACHE_ENABLED", "true")
            assert load_config().cache.enabled is True

            monkeypatch.setenv("CACHE_ENABLED", "TRUE")
            assert load_config().cache.enabled is True

            monkeypatch.setenv("CACHE_ENABLED", "True")
            assert load_config().cache.enabled is True

            monkeypatch.setenv("CACHE_ENABLED", "false")
            assert load_config().cache.enabled is False

            monkeypatch.setenv("CACHE_ENABLED", "FALSE")
            assert load_config().cache.enabled is False

            monkeypatch.setenv("CACHE_ENABLED", "0")
            assert load_config().cache.enabled is False

    def test_custom_cache_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Should use custom cache directory from env var."""
        custom_cache = tmp_path / "custom_cache"
        monkeypatch.setenv("PGSLICE_CACHE_DIR", str(custom_cache))
        # Disable cache to prevent directory creation during test
        monkeypatch.setenv("CACHE_ENABLED", "false")

        with patch("pgslice.config.load_dotenv"):
            config = load_config()

        assert config.cache.cache_dir == custom_cache

    def test_custom_output_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Should use custom output directory from env var."""
        custom_output = tmp_path / "custom_output"
        monkeypatch.setenv("PGSLICE_OUTPUT_DIR", str(custom_output))
        monkeypatch.setenv("CACHE_ENABLED", "false")

        with patch("pgslice.config.load_dotenv"):
            config = load_config()

        assert config.output_dir == custom_output
