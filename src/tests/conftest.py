"""Shared pytest fixtures for all tests."""

import pytest
import psycopg
from pathlib import Path
from unittest.mock import Mock

from snippy.db.schema import SchemaIntrospector
from snippy.graph.models import Table, Column, ForeignKey
from snippy.config import DatabaseConfig, CacheConfig, AppConfig


@pytest.fixture(scope="session")
def test_db_url():
    """PostgreSQL test database URL."""
    return "postgresql://test_user:test_pass@localhost:5432/test_db"


@pytest.fixture(scope="session")
def test_db_connection(test_db_url):
    """Session-scoped database connection."""
    try:
        conn = psycopg.connect(test_db_url)
        yield conn
        conn.close()
    except psycopg.OperationalError:
        pytest.skip("Test database not available")


@pytest.fixture
def db_transaction(test_db_connection):
    """Transaction fixture for test isolation."""
    with test_db_connection.transaction() as txn:
        yield txn
        txn.rollback()


@pytest.fixture
def mock_introspector(mocker):
    """Mock SchemaIntrospector for unit tests."""
    introspector = mocker.Mock(spec=SchemaIntrospector)
    return introspector


@pytest.fixture
def sample_table_metadata():
    """Sample table metadata for testing."""
    return Table(
        schema_name="public",
        table_name="users",
        columns=[
            Column(
                name="id",
                data_type="integer",
                nullable=False,
                default="nextval('users_id_seq'::regclass)",
                is_primary_key=True,
            ),
            Column(
                name="username",
                data_type="character varying",
                nullable=False,
                default=None,
                is_primary_key=False,
            ),
            Column(
                name="email",
                data_type="character varying",
                nullable=False,
                default=None,
                is_primary_key=False,
            ),
            Column(
                name="role_id",
                data_type="integer",
                nullable=True,
                default=None,
                is_primary_key=False,
            ),
        ],
        primary_keys=["id"],
        foreign_keys_outgoing=[
            ForeignKey(
                constraint_name="users_role_id_fkey",
                source_table="users",
                source_column="role_id",
                target_table="roles",
                target_column="id",
            )
        ],
        foreign_keys_incoming=[],
    )


@pytest.fixture
def test_db_config():
    """Test database configuration."""
    return DatabaseConfig(
        host="localhost",
        port=5432,
        database="test_db",
        user="test_user",
        schema="public",
    )


@pytest.fixture
def test_cache_config(tmp_path):
    """Test cache configuration."""
    return CacheConfig(
        cache_dir=tmp_path / "cache",
        ttl_hours=24,
        enabled=True,
    )


@pytest.fixture
def test_app_config(test_db_config, test_cache_config):
    """Test application configuration."""
    return AppConfig(
        db=test_db_config,
        cache=test_cache_config,
        connection_ttl_minutes=30,
        max_depth=10,
        log_level="ERROR",
        require_read_only=False,
        allow_write_connection=True,
        sql_batch_size=100,
    )
