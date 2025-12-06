"""Tests for configuration management."""

import pytest
import os
from pathlib import Path
from unittest.mock import patch

from snippy.config import DatabaseConfig, CacheConfig, AppConfig, load_config


class TestDatabaseConfig:
    """Tests for DatabaseConfig dataclass."""

    def test_creation(self):
        """Test DatabaseConfig creation."""
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
            schema="public",
        )

        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "test_db"
        assert config.user == "test_user"
        assert config.schema == "public"

    def test_default_schema(self):
        """Test DatabaseConfig uses default schema."""
        config = DatabaseConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
        )

        assert config.schema == "public"


class TestCacheConfig:
    """Tests for CacheConfig dataclass."""

    def test_creation(self, tmp_path):
        """Test CacheConfig creation."""
        cache_dir = tmp_path / "cache"
        config = CacheConfig(
            cache_dir=cache_dir,
            ttl_hours=24,
            enabled=True,
        )

        assert config.cache_dir == cache_dir
        assert config.ttl_hours == 24
        assert config.enabled is True

    def test_default_values(self, tmp_path):
        """Test CacheConfig default values."""
        config = CacheConfig(cache_dir=tmp_path)

        assert config.ttl_hours == 24
        assert config.enabled is True

    def test_directory_creation_when_enabled(self, tmp_path):
        """Test cache directory is created when enabled."""
        cache_dir = tmp_path / "cache" / "nested"
        assert not cache_dir.exists()

        config = CacheConfig(cache_dir=cache_dir, enabled=True)

        assert cache_dir.exists()
        assert cache_dir.is_dir()

    def test_directory_not_created_when_disabled(self, tmp_path):
        """Test cache directory is not created when disabled."""
        cache_dir = tmp_path / "cache" / "should_not_exist"
        assert not cache_dir.exists()

        config = CacheConfig(cache_dir=cache_dir, enabled=False)

        assert not cache_dir.exists()


class TestAppConfig:
    """Tests for AppConfig dataclass."""

    def test_creation(self, test_db_config, test_cache_config):
        """Test AppConfig creation."""
        config = AppConfig(
            db=test_db_config,
            cache=test_cache_config,
            connection_ttl_minutes=30,
            max_depth=10,
            log_level="INFO",
            require_read_only=False,
            allow_write_connection=True,
            sql_batch_size=100,
        )

        assert config.db == test_db_config
        assert config.cache == test_cache_config
        assert config.connection_ttl_minutes == 30
        assert config.max_depth == 10
        assert config.log_level == "INFO"
        assert config.require_read_only is False
        assert config.allow_write_connection is True
        assert config.sql_batch_size == 100

    def test_default_values(self, test_db_config, test_cache_config):
        """Test AppConfig default values."""
        config = AppConfig(db=test_db_config, cache=test_cache_config)

        assert config.connection_ttl_minutes == 30
        assert config.max_depth is None
        assert config.log_level == "INFO"
        assert config.require_read_only is False
        assert config.allow_write_connection is False
        assert config.sql_batch_size == 100


class TestLoadConfig:
    """Tests for load_config() function."""

    def test_load_from_environment(self, monkeypatch, tmp_path):
        """Test loading configuration from environment variables."""
        monkeypatch.setenv("DB_HOST", "testhost")
        monkeypatch.setenv("DB_PORT", "5433")
        monkeypatch.setenv("DB_NAME", "testdb")
        monkeypatch.setenv("DB_USER", "testuser")
        monkeypatch.setenv("DB_SCHEMA", "testschema")
        monkeypatch.setenv("CACHE_ENABLED", "true")
        monkeypatch.setenv("CACHE_TTL_HOURS", "48")
        monkeypatch.setenv("SNIPPY_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv("CONNECTION_TTL_MINUTES", "60")
        monkeypatch.setenv("MAX_DEPTH", "5")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("SQL_BATCH_SIZE", "50")

        config = load_config()

        assert config.db.host == "testhost"
        assert config.db.port == 5433
        assert config.db.database == "testdb"
        assert config.db.user == "testuser"
        assert config.db.schema == "testschema"
        assert config.cache.enabled is True
        assert config.cache.ttl_hours == 48
        assert config.connection_ttl_minutes == 60
        assert config.max_depth == 5
        assert config.log_level == "DEBUG"
        assert config.sql_batch_size == 50

    def test_default_cache_directory(self, monkeypatch):
        """Test default cache directory uses home directory."""
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "5432")
        monkeypatch.setenv("DB_NAME", "test_db")
        monkeypatch.setenv("DB_USER", "test_user")
        # Don't set SNIPPY_CACHE_DIR to test default

        config = load_config()

        expected_dir = Path.home() / ".cache" / "snippy"
        assert config.cache.cache_dir == expected_dir

    def test_cache_disabled(self, monkeypatch):
        """Test cache can be disabled via environment."""
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "5432")
        monkeypatch.setenv("DB_NAME", "test_db")
        monkeypatch.setenv("DB_USER", "test_user")
        monkeypatch.setenv("CACHE_ENABLED", "false")

        config = load_config()

        assert config.cache.enabled is False

    def test_max_depth_optional(self, monkeypatch):
        """Test max_depth is optional (None if not set)."""
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "5432")
        monkeypatch.setenv("DB_NAME", "test_db")
        monkeypatch.setenv("DB_USER", "test_user")
        # Don't set MAX_DEPTH

        config = load_config()

        assert config.max_depth is None

    def test_type_conversion(self, monkeypatch):
        """Test environment variables are converted to correct types."""
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "5432")  # String "5432" should become int
        monkeypatch.setenv("DB_NAME", "test_db")
        monkeypatch.setenv("DB_USER", "test_user")
        monkeypatch.setenv("CACHE_TTL_HOURS", "12")  # String should become int
        monkeypatch.setenv("SQL_BATCH_SIZE", "200")  # String should become int

        config = load_config()

        assert isinstance(config.db.port, int)
        assert config.db.port == 5432
        assert isinstance(config.cache.ttl_hours, int)
        assert config.cache.ttl_hours == 12
        assert isinstance(config.sql_batch_size, int)
        assert config.sql_batch_size == 200
