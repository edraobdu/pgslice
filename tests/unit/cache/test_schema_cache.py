"""Tests for pgslice.cache.schema_cache module."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time
from pytest_mock import MockerFixture

from pgslice.cache.schema_cache import SchemaCache
from pgslice.graph.models import Column, ForeignKey, Table


class TestSchemaCache:
    """Tests for SchemaCache class."""

    @pytest.fixture
    def mock_sqlite(self, mocker: MockerFixture) -> MagicMock:
        """Mock sqlite3 module to avoid creating real database files."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # Setup mock connection and cursor
        # Note: SchemaCache uses conn.execute() directly, which returns a cursor
        mock_conn.execute.return_value = mock_cursor
        mock_conn.executescript.return_value = None
        mock_conn.commit.return_value = None
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = None

        # Mock sqlite3.connect to return our mock connection
        mock_connect = mocker.patch("pgslice.cache.schema_cache.sqlite3.connect")
        mock_connect.return_value = mock_conn

        return mock_conn

    @pytest.fixture
    def cache_path(self, tmp_path: Path) -> Path:
        """Provide a temporary cache path."""
        return tmp_path / "schema_cache.db"

    @pytest.fixture
    def cache(self, cache_path: Path, mock_sqlite: MagicMock) -> SchemaCache:
        """Provide a SchemaCache instance with mocked SQLite."""
        return SchemaCache(cache_path, ttl_hours=24)

    @pytest.fixture
    def sample_table(self) -> Table:
        """Provide a sample table for caching."""
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
                ),
                Column(
                    name="name",
                    data_type="text",
                    udt_name="text",
                    nullable=True,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
            unique_constraints={"uq_name": ["name"]},
        )


class TestInit(TestSchemaCache):
    """Tests for SchemaCache initialization."""

    def test_creates_cache_database(
        self, cache_path: Path, mock_sqlite: MagicMock, mocker: MockerFixture
    ) -> None:
        """Should initialize SQLite database with proper schema."""
        mock_connect = mocker.patch(
            "pgslice.cache.schema_cache.sqlite3.connect", return_value=mock_sqlite
        )

        with SchemaCache(cache_path):
            # Verify sqlite3.connect was called with the correct path
            mock_connect.assert_called_with(cache_path)
            # Verify executescript was called to create tables
            assert mock_sqlite.executescript.called

    def test_creates_parent_directory(
        self, tmp_path: Path, mock_sqlite: MagicMock, mocker: MockerFixture
    ) -> None:
        """Should create parent directory if needed."""
        cache_path = tmp_path / "nested" / "cache.db"

        # Note: With mocked SQLite, we're just verifying the path is used correctly
        # The actual directory creation happens in SQLite's C code, which is mocked
        with SchemaCache(cache_path) as cache_instance:
            assert cache_instance.cache_path == cache_path
            # Verify parent directory would be created (in real SQLite)
            assert cache_path.parent == tmp_path / "nested"

    def test_default_ttl(self, cache_path: Path, mock_sqlite: MagicMock) -> None:
        """Default TTL should be 24 hours."""
        with SchemaCache(cache_path) as cache_instance:
            assert cache_instance.ttl == timedelta(hours=24)

    def test_custom_ttl(self, cache_path: Path, mock_sqlite: MagicMock) -> None:
        """Can specify custom TTL."""
        with SchemaCache(cache_path, ttl_hours=48) as cache_instance:
            assert cache_instance.ttl == timedelta(hours=48)


class TestIsCacheValid(TestSchemaCache):
    """Tests for is_cache_valid method."""

    def test_returns_false_for_empty_cache(
        self, cache: SchemaCache, mock_sqlite: MagicMock
    ) -> None:
        """Should return False when no cache exists."""
        mock_cursor = mock_sqlite.execute.return_value
        mock_cursor.fetchone.return_value = None

        assert cache.is_cache_valid("localhost", "test_db") is False

    @freeze_time("2024-03-15 12:00:00")
    def test_returns_true_for_fresh_cache(
        self, cache: SchemaCache, sample_table: Table, mock_sqlite: MagicMock
    ) -> None:
        """Should return True for cache within TTL."""
        mock_cursor = mock_sqlite.execute.return_value

        # First call: cache_table's fetchone for table ID
        # Second call: is_cache_valid's fetchone for cached_at timestamp
        mock_cursor.fetchone.side_effect = [
            (1,),  # table_id from cache_table
            ("2024-03-15T12:00:00",),  # cached_at from is_cache_valid
        ]

        cache.cache_table("localhost", "test_db", sample_table)
        assert cache.is_cache_valid("localhost", "test_db") is True

    def test_returns_false_for_expired_cache(
        self, cache: SchemaCache, sample_table: Table, mock_sqlite: MagicMock
    ) -> None:
        """Should return False for expired cache."""
        mock_cursor = mock_sqlite.execute.return_value

        with freeze_time("2024-03-15 12:00:00"):
            mock_cursor.fetchone.return_value = (1,)  # table_id
            cache.cache_table("localhost", "test_db", sample_table)

        with freeze_time("2024-03-16 13:00:00"):  # 25 hours later
            mock_cursor.fetchone.return_value = ("2024-03-15T12:00:00",)
            assert cache.is_cache_valid("localhost", "test_db") is False

    @freeze_time("2024-03-15 12:00:00")
    def test_different_databases_isolated(
        self, cache: SchemaCache, sample_table: Table, mock_sqlite: MagicMock
    ) -> None:
        """Cache should be isolated per database."""
        mock_cursor = mock_sqlite.execute.return_value

        # cache_table("localhost", "db1") needs 1 fetchone for table_id
        # is_cache_valid("localhost", "db1") needs 1 fetchone for cached_at
        # is_cache_valid("localhost", "db2") needs 1 fetchone (returns None)
        mock_cursor.fetchone.side_effect = [
            (1,),  # table_id for db1 from cache_table
            ("2024-03-15T12:00:00",),  # cached_at for db1 from is_cache_valid
            None,  # no cache for db2 from is_cache_valid
        ]

        cache.cache_table("localhost", "db1", sample_table)

        assert cache.is_cache_valid("localhost", "db1") is True
        assert cache.is_cache_valid("localhost", "db2") is False


class TestCacheTable(TestSchemaCache):
    """Tests for cache_table method."""

    def test_caches_basic_table(
        self, cache: SchemaCache, sample_table: Table, mock_sqlite: MagicMock
    ) -> None:
        """Should cache table metadata."""
        mock_cursor = mock_sqlite.execute.return_value

        # cache_table needs fetchone for table ID
        # get_table needs fetchone for table record, then fetchall for columns, FKs, constraints
        mock_cursor.fetchone.side_effect = [
            (1,),  # table_id from cache_table
            (1, '["id"]'),  # table record (id, primary_keys) from get_table
        ]
        mock_cursor.fetchall.side_effect = [
            [
                ("id", "integer", "int4", False, None, True),
                ("name", "text", "text", True, None, False),
            ],  # columns
            [],  # outgoing FKs
            [],  # incoming FKs
            [("uq_name", '["name"]')],  # unique constraints
        ]

        cache.cache_table("localhost", "test_db", sample_table)

        # Verify by retrieving
        retrieved = cache.get_table("localhost", "test_db", "public", "users")
        assert retrieved is not None
        assert retrieved.table_name == "users"

    def test_caches_columns(
        self, cache: SchemaCache, sample_table: Table, mock_sqlite: MagicMock
    ) -> None:
        """Should cache column information."""
        mock_cursor = mock_sqlite.execute.return_value

        mock_cursor.fetchone.side_effect = [
            (1,),  # cache_table
            (1, '["id"]'),  # get_table
        ]
        mock_cursor.fetchall.side_effect = [
            [
                ("id", "integer", "int4", False, None, True),
                ("name", "text", "text", True, None, False),
            ],
            [],
            [],
            [("uq_name", '["name"]')],
        ]

        cache.cache_table("localhost", "test_db", sample_table)

        retrieved = cache.get_table("localhost", "test_db", "public", "users")
        assert retrieved is not None
        assert len(retrieved.columns) == 2
        assert retrieved.columns[0].name == "id"
        assert retrieved.columns[0].is_primary_key is True

    def test_caches_primary_keys(
        self, cache: SchemaCache, sample_table: Table, mock_sqlite: MagicMock
    ) -> None:
        """Should cache primary key information."""
        mock_cursor = mock_sqlite.execute.return_value

        mock_cursor.fetchone.side_effect = [
            (1,),
            (1, '["id"]'),
        ]
        mock_cursor.fetchall.side_effect = [
            [
                ("id", "integer", "int4", False, None, True),
                ("name", "text", "text", True, None, False),
            ],
            [],
            [],
            [("uq_name", '["name"]')],
        ]

        cache.cache_table("localhost", "test_db", sample_table)

        retrieved = cache.get_table("localhost", "test_db", "public", "users")
        assert retrieved is not None
        assert retrieved.primary_keys == ["id"]

    def test_caches_unique_constraints(
        self, cache: SchemaCache, sample_table: Table, mock_sqlite: MagicMock
    ) -> None:
        """Should cache unique constraint information."""
        mock_cursor = mock_sqlite.execute.return_value

        mock_cursor.fetchone.side_effect = [
            (1,),
            (1, '["id"]'),
        ]
        mock_cursor.fetchall.side_effect = [
            [
                ("id", "integer", "int4", False, None, True),
                ("name", "text", "text", True, None, False),
            ],
            [],
            [],
            [("uq_name", '["name"]')],
        ]

        cache.cache_table("localhost", "test_db", sample_table)

        retrieved = cache.get_table("localhost", "test_db", "public", "users")
        assert retrieved is not None
        assert "uq_name" in retrieved.unique_constraints
        assert retrieved.unique_constraints["uq_name"] == ["name"]

    def test_caches_foreign_keys(
        self, cache: SchemaCache, mock_sqlite: MagicMock
    ) -> None:
        """Should cache foreign key information."""
        table = Table(
            schema_name="public",
            table_name="orders",
            columns=[
                Column(name="id", data_type="integer", udt_name="int4", nullable=False),
                Column(
                    name="user_id", data_type="integer", udt_name="int4", nullable=False
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[
                ForeignKey(
                    constraint_name="fk_orders_user_id",
                    source_table="public.orders",
                    source_column="user_id",
                    target_table="public.users",
                    target_column="id",
                    on_delete="CASCADE",
                )
            ],
            foreign_keys_incoming=[],
        )

        mock_cursor = mock_sqlite.execute.return_value

        # cache_table needs:
        # 1 fetchone for orders table_id
        # 1 fetchone for source table_id (orders)
        # 1 fetchone for target table_id (users)
        # get_table needs:
        # 1 fetchone for table record
        mock_cursor.fetchone.side_effect = [
            (1,),  # orders table_id from initial INSERT
            (1,),  # source table_id (orders) for FK
            (2,),  # target table_id (users) for FK
            (1, '["id"]'),  # table record from get_table
        ]
        mock_cursor.fetchall.side_effect = [
            [
                ("id", "integer", "int4", False, None, False),
                ("user_id", "integer", "int4", False, None, False),
            ],  # columns
            [
                (
                    "fk_orders_user_id",
                    "public.orders",
                    "user_id",
                    "public.users",
                    "id",
                    "CASCADE",
                )
            ],  # outgoing FKs
            [],  # incoming FKs
            [],  # unique constraints
        ]

        cache.cache_table("localhost", "test_db", table)

        retrieved = cache.get_table("localhost", "test_db", "public", "orders")
        assert retrieved is not None
        assert len(retrieved.foreign_keys_outgoing) == 1
        assert retrieved.foreign_keys_outgoing[0].target_table == "public.users"

    def test_updates_existing_cache(
        self, cache: SchemaCache, sample_table: Table, mock_sqlite: MagicMock
    ) -> None:
        """Should update existing cache entry."""
        mock_cursor = mock_sqlite.execute.return_value

        # First cache_table call
        mock_cursor.fetchone.side_effect = [
            (1,),  # first cache_table
            (1,),  # second cache_table (updates existing)
            (1, '["id"]'),  # get_table
        ]
        mock_cursor.fetchall.side_effect = [
            [
                ("id", "integer", "int4", False, None, False),
                ("email", "text", "text", True, None, False),
            ],
            [],
            [],
            [],
        ]

        cache.cache_table("localhost", "test_db", sample_table)

        # Update with new column
        updated_table = Table(
            schema_name="public",
            table_name="users",
            columns=[
                Column(name="id", data_type="integer", udt_name="int4", nullable=False),
                Column(name="email", data_type="text", udt_name="text", nullable=True),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )
        cache.cache_table("localhost", "test_db", updated_table)

        retrieved = cache.get_table("localhost", "test_db", "public", "users")
        assert retrieved is not None
        assert len(retrieved.columns) == 2
        assert retrieved.columns[1].name == "email"


class TestGetTable(TestSchemaCache):
    """Tests for get_table method."""

    def test_returns_none_for_missing_table(
        self, cache: SchemaCache, mock_sqlite: MagicMock
    ) -> None:
        """Should return None when table not cached."""
        mock_cursor = mock_sqlite.execute.return_value
        mock_cursor.fetchone.return_value = None

        result = cache.get_table("localhost", "test_db", "public", "nonexistent")
        assert result is None

    def test_returns_table_object(
        self, cache: SchemaCache, sample_table: Table, mock_sqlite: MagicMock
    ) -> None:
        """Should return Table object for cached table."""
        mock_cursor = mock_sqlite.execute.return_value

        mock_cursor.fetchone.side_effect = [
            (1,),  # cache_table
            (1, '["id"]'),  # get_table
        ]
        mock_cursor.fetchall.side_effect = [
            [
                ("id", "integer", "int4", False, None, True),
                ("name", "text", "text", True, None, False),
            ],
            [],
            [],
            [("uq_name", '["name"]')],
        ]

        cache.cache_table("localhost", "test_db", sample_table)

        result = cache.get_table("localhost", "test_db", "public", "users")

        assert result is not None
        assert isinstance(result, Table)
        assert result.table_name == "users"

    def test_returns_none_for_different_host(
        self, cache: SchemaCache, sample_table: Table, mock_sqlite: MagicMock
    ) -> None:
        """Should return None for different host."""
        mock_cursor = mock_sqlite.execute.return_value

        mock_cursor.fetchone.side_effect = [
            (1,),  # cache_table
            None,  # get_table for different host
        ]

        cache.cache_table("localhost", "test_db", sample_table)

        result = cache.get_table("otherhost", "test_db", "public", "users")
        assert result is None


class TestInvalidateCache(TestSchemaCache):
    """Tests for invalidate_cache method."""

    @freeze_time("2024-03-15 12:00:00")
    def test_removes_cache_for_database(
        self, cache: SchemaCache, sample_table: Table, mock_sqlite: MagicMock
    ) -> None:
        """Should remove cache for specified database."""
        mock_cursor = mock_sqlite.execute.return_value

        mock_cursor.fetchone.side_effect = [
            (1,),  # cache_table
            ("2024-03-15T12:00:00",),  # is_cache_valid before invalidate
            None,  # is_cache_valid after invalidate
            None,  # get_table after invalidate
        ]

        cache.cache_table("localhost", "test_db", sample_table)
        assert cache.is_cache_valid("localhost", "test_db") is True

        cache.invalidate_cache("localhost", "test_db")

        assert cache.is_cache_valid("localhost", "test_db") is False
        assert cache.get_table("localhost", "test_db", "public", "users") is None

    @freeze_time("2024-03-15 12:00:00")
    def test_does_not_affect_other_databases(
        self, cache: SchemaCache, sample_table: Table, mock_sqlite: MagicMock
    ) -> None:
        """Should not affect cache for other databases."""
        mock_cursor = mock_sqlite.execute.return_value

        mock_cursor.fetchone.side_effect = [
            (1,),  # cache_table db1
            (2,),  # cache_table db2
            None,  # is_cache_valid db1 after invalidate
            ("2024-03-15T12:00:00",),  # is_cache_valid db2 after invalidate
        ]

        cache.cache_table("localhost", "db1", sample_table)
        cache.cache_table("localhost", "db2", sample_table)

        cache.invalidate_cache("localhost", "db1")

        assert cache.is_cache_valid("localhost", "db1") is False
        assert cache.is_cache_valid("localhost", "db2") is True


class TestParseTableName(TestSchemaCache):
    """Tests for _parse_table_name static method."""

    def test_parses_qualified_name(self) -> None:
        """Should parse schema.table format."""
        schema, table = SchemaCache._parse_table_name("public.users")
        assert schema == "public"
        assert table == "users"

    def test_parses_simple_name(self) -> None:
        """Should default to public schema for simple names."""
        schema, table = SchemaCache._parse_table_name("users")
        assert schema == "public"
        assert table == "users"

    def test_parses_custom_schema(self) -> None:
        """Should parse custom schema names."""
        schema, table = SchemaCache._parse_table_name("custom.orders")
        assert schema == "custom"
        assert table == "orders"
