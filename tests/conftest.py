"""Shared pytest fixtures for pgslice tests."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import psycopg
import pytest
from faker import Faker

from pgslice.config import CacheConfig, DatabaseConfig
from pgslice.graph.models import (
    Column,
    ForeignKey,
    RecordData,
    RecordIdentifier,
    Table,
    TimeframeFilter,
)

# =============================================================================
# Faker Instance
# =============================================================================


@pytest.fixture
def fake() -> Faker:
    """Provide a Faker instance for test data generation."""
    return Faker()


# =============================================================================
# Database Mocking Fixtures
# =============================================================================


@pytest.fixture
def mock_cursor(mocker: Any) -> MagicMock:
    """Create a mock database cursor."""
    cursor = MagicMock()
    cursor.execute = MagicMock()
    cursor.fetchone = MagicMock(return_value=None)
    cursor.fetchall = MagicMock(return_value=[])
    cursor.description = None
    return cursor


@pytest.fixture
def mock_connection(mocker: Any, mock_cursor: MagicMock) -> MagicMock:
    """Create a mock psycopg connection with cursor context manager."""
    conn = MagicMock(spec=psycopg.Connection)

    # Set up cursor context manager
    cursor_cm = MagicMock()
    cursor_cm.__enter__ = MagicMock(return_value=mock_cursor)
    cursor_cm.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor_cm

    return conn


# =============================================================================
# Configuration Fixtures
# =============================================================================


@pytest.fixture
def sample_db_config() -> DatabaseConfig:
    """Provide a sample database configuration."""
    return DatabaseConfig(
        host="localhost",
        port=5432,
        database="test_db",
        user="test_user",
        schema="public",
    )


@pytest.fixture
def sample_cache_config(tmp_path: Any) -> CacheConfig:
    """Provide a sample cache configuration with temp directory."""
    return CacheConfig(
        enabled=True,
        cache_dir=str(tmp_path / ".cache"),
        ttl_hours=24,
    )


# =============================================================================
# Model Fixtures
# =============================================================================


@pytest.fixture
def sample_column() -> Column:
    """Provide a sample Column model."""
    return Column(
        name="id",
        data_type="integer",
        udt_name="int4",
        nullable=False,
        default=None,
        is_primary_key=True,
        is_auto_generated=True,
    )


@pytest.fixture
def sample_foreign_key() -> ForeignKey:
    """Provide a sample ForeignKey model."""
    return ForeignKey(
        constraint_name="fk_user_id",
        source_table="orders",
        source_column="user_id",
        target_table="users",
        target_column="id",
        on_delete="CASCADE",
    )


@pytest.fixture
def sample_table(sample_column: Column, sample_foreign_key: ForeignKey) -> Table:
    """Provide a sample Table model with columns and foreign keys."""
    return Table(
        schema_name="public",
        table_name="orders",
        columns=[
            sample_column,
            Column(
                name="user_id",
                data_type="integer",
                udt_name="int4",
                nullable=False,
            ),
            Column(
                name="total",
                data_type="numeric",
                udt_name="numeric",
                nullable=True,
            ),
        ],
        primary_keys=["id"],
        foreign_keys_outgoing=[sample_foreign_key],
        foreign_keys_incoming=[],
        unique_constraints={"uq_order_ref": ["order_ref"]},
    )


@pytest.fixture
def sample_users_table() -> Table:
    """Provide a sample users table for FK testing."""
    return Table(
        schema_name="public",
        table_name="users",
        columns=[
            Column(
                name="id",
                data_type="integer",
                udt_name="int4",
                nullable=False,
                is_primary_key=True,
                is_auto_generated=True,
            ),
            Column(
                name="name",
                data_type="text",
                udt_name="text",
                nullable=False,
            ),
            Column(
                name="email",
                data_type="text",
                udt_name="text",
                nullable=False,
            ),
        ],
        primary_keys=["id"],
        foreign_keys_outgoing=[],
        foreign_keys_incoming=[],
    )


@pytest.fixture
def sample_record_identifier() -> RecordIdentifier:
    """Provide a sample RecordIdentifier."""
    return RecordIdentifier(
        schema_name="public",
        table_name="users",
        pk_values=(1,),
    )


@pytest.fixture
def sample_record_data(sample_record_identifier: RecordIdentifier) -> RecordData:
    """Provide a sample RecordData with dependencies."""
    return RecordData(
        identifier=sample_record_identifier,
        data={"id": 1, "name": "Test User", "email": "test@example.com"},
        dependencies=set(),
    )


@pytest.fixture
def sample_timeframe_filter() -> TimeframeFilter:
    """Provide a sample TimeframeFilter."""
    return TimeframeFilter(
        table_name="orders",
        column_name="created_at",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
    )


# =============================================================================
# File System Fixtures
# =============================================================================


@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """Provide a temporary directory for file tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_file(temp_dir: str) -> str:
    """Provide a temporary file path."""
    return os.path.join(temp_dir, "test_output.sql")


# =============================================================================
# Environment Variable Fixtures
# =============================================================================


@pytest.fixture
def mock_env(mocker: Any) -> Generator[dict[str, str], None, None]:
    """Provide a mock environment with clean state."""
    env: dict[str, str] = {}

    def getenv_mock(key: str, default: str | None = None) -> str | None:
        return env.get(key, default)

    mocker.patch("os.getenv", side_effect=getenv_mock)
    yield env


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove relevant environment variables for clean testing."""
    env_vars = [
        "PGPASSWORD",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_SCHEMA",
        "CACHE_ENABLED",
        "CACHE_TTL_HOURS",
        "LOG_LEVEL",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)


# =============================================================================
# Schema Introspector Mock
# =============================================================================


@pytest.fixture
def mock_schema_introspector(mocker: Any, sample_table: Table) -> MagicMock:
    """Create a mock SchemaIntrospector."""
    introspector = MagicMock()
    introspector.get_table_metadata.return_value = sample_table
    return introspector


# =============================================================================
# Complex Record Fixtures for Dependency Testing
# =============================================================================


@pytest.fixture
def record_chain() -> list[RecordData]:
    """
    Provide a chain of records with dependencies: A -> B -> C.

    Order for insertion should be: C, B, A (dependencies first).
    """
    record_c = RecordData(
        identifier=RecordIdentifier(
            schema_name="public",
            table_name="table_c",
            pk_values=(3,),
        ),
        data={"id": 3, "name": "C"},
        dependencies=set(),
    )

    record_b = RecordData(
        identifier=RecordIdentifier(
            schema_name="public",
            table_name="table_b",
            pk_values=(2,),
        ),
        data={"id": 2, "name": "B", "c_id": 3},
        dependencies={record_c.identifier},
    )

    record_a = RecordData(
        identifier=RecordIdentifier(
            schema_name="public",
            table_name="table_a",
            pk_values=(1,),
        ),
        data={"id": 1, "name": "A", "b_id": 2},
        dependencies={record_b.identifier},
    )

    return [record_a, record_b, record_c]


@pytest.fixture
def diamond_dependency_records() -> set[RecordData]:
    """
    Provide records with diamond dependency: A depends on B and C, both depend on D.

    Structure:
        A
       / \\
      B   C
       \\ /
        D

    Order for insertion should be: D, B, C, A.
    """
    record_d = RecordData(
        identifier=RecordIdentifier(
            schema_name="public",
            table_name="base",
            pk_values=(4,),
        ),
        data={"id": 4, "name": "D"},
        dependencies=set(),
    )

    record_b = RecordData(
        identifier=RecordIdentifier(
            schema_name="public",
            table_name="middle_b",
            pk_values=(2,),
        ),
        data={"id": 2, "name": "B", "d_id": 4},
        dependencies={record_d.identifier},
    )

    record_c = RecordData(
        identifier=RecordIdentifier(
            schema_name="public",
            table_name="middle_c",
            pk_values=(3,),
        ),
        data={"id": 3, "name": "C", "d_id": 4},
        dependencies={record_d.identifier},
    )

    record_a = RecordData(
        identifier=RecordIdentifier(
            schema_name="public",
            table_name="top",
            pk_values=(1,),
        ),
        data={"id": 1, "name": "A", "b_id": 2, "c_id": 3},
        dependencies={record_b.identifier, record_c.identifier},
    )

    return {record_a, record_b, record_c, record_d}
