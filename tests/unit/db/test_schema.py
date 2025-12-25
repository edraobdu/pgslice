"""Tests for pgslice.db.schema module."""

from __future__ import annotations

from unittest.mock import MagicMock

import psycopg
import pytest

from pgslice.db.schema import SchemaIntrospector
from pgslice.utils.exceptions import SchemaError, SecurityError


class TestSchemaIntrospector:
    """Tests for SchemaIntrospector class."""

    @pytest.fixture
    def mock_cursor(self) -> MagicMock:
        """Create a mock cursor."""
        cursor = MagicMock()
        cursor.execute = MagicMock()
        cursor.fetchall = MagicMock(return_value=[])
        cursor.fetchone = MagicMock(return_value=None)
        return cursor

    @pytest.fixture
    def mock_connection(self, mock_cursor: MagicMock) -> MagicMock:
        """Create a mock connection."""
        conn = MagicMock(spec=psycopg.Connection)
        cursor_cm = MagicMock()
        cursor_cm.__enter__ = MagicMock(return_value=mock_cursor)
        cursor_cm.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor_cm
        return conn

    @pytest.fixture
    def introspector(self, mock_connection: MagicMock) -> SchemaIntrospector:
        """Create a SchemaIntrospector instance."""
        return SchemaIntrospector(mock_connection)


class TestGetTableMetadata(TestSchemaIntrospector):
    """Tests for get_table_metadata method."""

    def test_returns_table_object(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should return a Table object with all metadata."""
        # Setup mock returns for each query
        mock_cursor.fetchall.side_effect = [
            # columns query
            [
                ("id", "integer", "int4", "NO", None),
                ("name", "text", "text", "YES", None),
            ],
            # primary keys query
            [("id",)],
            # foreign keys outgoing query
            [],
            # foreign keys incoming query
            [],
            # unique constraints query
            [],
        ]
        mock_cursor.fetchone.return_value = (False, False, None)  # auto-gen check

        table = introspector.get_table_metadata("public", "users")

        assert table.schema_name == "public"
        assert table.table_name == "users"
        assert len(table.columns) == 2
        assert table.primary_keys == ["id"]

    def test_raises_schema_error_for_missing_table(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should raise SchemaError when table not found."""
        mock_cursor.fetchall.return_value = []  # No columns = table not found

        with pytest.raises(SchemaError, match="not found"):
            introspector.get_table_metadata("public", "nonexistent")

    def test_validates_identifiers(self, introspector: SchemaIntrospector) -> None:
        """Should validate schema and table names."""
        with pytest.raises(SecurityError):
            introspector.get_table_metadata("bad;schema", "users")

        with pytest.raises(SecurityError):
            introspector.get_table_metadata("public", "bad;table")

    def test_handles_database_error(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should wrap psycopg errors in SchemaError."""
        mock_cursor.execute.side_effect = psycopg.Error("Database error")

        with pytest.raises(SchemaError, match="Failed to introspect"):
            introspector.get_table_metadata("public", "users")

    def test_marks_primary_key_columns(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should mark primary key columns correctly."""
        mock_cursor.fetchall.side_effect = [
            [
                ("id", "integer", "int4", "NO", None),
                ("name", "text", "text", "YES", None),
            ],
            [("id",)],  # id is primary key
            [],
            [],
            [],
        ]
        mock_cursor.fetchone.return_value = (True, False, None)  # has_sequence

        table = introspector.get_table_metadata("public", "users")

        id_col = next(c for c in table.columns if c.name == "id")
        name_col = next(c for c in table.columns if c.name == "name")

        assert id_col.is_primary_key is True
        assert name_col.is_primary_key is False


class TestGetColumns(TestSchemaIntrospector):
    """Tests for _get_columns method."""

    def test_returns_column_list(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should return list of Column objects."""
        mock_cursor.fetchall.return_value = [
            ("id", "integer", "int4", "NO", None),
            ("created_at", "timestamp", "timestamp", "YES", "now()"),
        ]

        columns = introspector._get_columns("public", "users")

        assert len(columns) == 2
        assert columns[0].name == "id"
        assert columns[0].nullable is False
        assert columns[1].name == "created_at"
        assert columns[1].nullable is True
        assert columns[1].default == "now()"

    def test_raises_for_empty_columns(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should raise SchemaError when no columns found."""
        mock_cursor.fetchall.return_value = []

        with pytest.raises(SchemaError, match="not found or has no columns"):
            introspector._get_columns("public", "nonexistent")


class TestGetPrimaryKeys(TestSchemaIntrospector):
    """Tests for _get_primary_keys method."""

    def test_returns_pk_list(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should return list of primary key column names."""
        mock_cursor.fetchall.return_value = [("id",)]

        pks = introspector._get_primary_keys("public", "users")

        assert pks == ["id"]

    def test_returns_empty_for_no_pk(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should return empty list when no PK exists."""
        mock_cursor.fetchall.return_value = []

        pks = introspector._get_primary_keys("public", "no_pk_table")

        assert pks == []

    def test_handles_composite_pk(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should handle composite primary keys."""
        mock_cursor.fetchall.return_value = [("order_id",), ("product_id",)]

        pks = introspector._get_primary_keys("public", "order_items")

        assert pks == ["order_id", "product_id"]


class TestGetForeignKeysOutgoing(TestSchemaIntrospector):
    """Tests for _get_foreign_keys_outgoing method."""

    def test_returns_fk_list(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should return list of ForeignKey objects."""
        mock_cursor.fetchall.return_value = [
            (
                "fk_orders_user_id",
                "public.orders",
                "user_id",
                "public.users",
                "id",
                "CASCADE",
            )
        ]

        fks = introspector._get_foreign_keys_outgoing("public", "orders")

        assert len(fks) == 1
        assert fks[0].constraint_name == "fk_orders_user_id"
        assert fks[0].source_column == "user_id"
        assert fks[0].target_table == "public.users"
        assert fks[0].on_delete == "CASCADE"

    def test_returns_empty_for_no_fks(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should return empty list when no FKs exist."""
        mock_cursor.fetchall.return_value = []

        fks = introspector._get_foreign_keys_outgoing("public", "users")

        assert fks == []


class TestGetForeignKeysIncoming(TestSchemaIntrospector):
    """Tests for _get_foreign_keys_incoming method."""

    def test_returns_incoming_fks(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should return FKs pointing to this table."""
        mock_cursor.fetchall.return_value = [
            (
                "fk_orders_user_id",
                "public.orders",
                "user_id",
                "public.users",
                "id",
                "NO ACTION",
            )
        ]

        fks = introspector._get_foreign_keys_incoming("public", "users")

        assert len(fks) == 1
        assert fks[0].target_table == "public.users"
        assert fks[0].source_table == "public.orders"


class TestIsAutoGeneratedColumn(TestSchemaIntrospector):
    """Tests for _is_auto_generated_column method."""

    def test_detects_serial_column(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should detect SERIAL columns via sequence."""
        mock_cursor.fetchone.return_value = (True, False, None)  # has_sequence

        result = introspector._is_auto_generated_column("public", "users", "id")

        assert result is True

    def test_detects_identity_column(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should detect IDENTITY columns."""
        mock_cursor.fetchone.return_value = (False, True, None)  # is_identity

        result = introspector._is_auto_generated_column("public", "users", "id")

        assert result is True

    def test_detects_nextval_default(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should detect nextval() default."""
        mock_cursor.fetchone.return_value = (
            False,
            False,
            "nextval('users_id_seq'::regclass)",
        )

        result = introspector._is_auto_generated_column("public", "users", "id")

        assert result is True

    def test_returns_false_for_regular_column(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should return False for non-auto-generated columns."""
        mock_cursor.fetchone.return_value = (False, False, None)

        result = introspector._is_auto_generated_column("public", "users", "name")

        assert result is False

    def test_returns_false_on_exception(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should return False when exception occurs."""
        mock_cursor.execute.side_effect = Exception("Query failed")

        result = introspector._is_auto_generated_column("public", "users", "id")

        assert result is False


class TestGetUniqueConstraints(TestSchemaIntrospector):
    """Tests for _get_unique_constraints method."""

    def test_returns_constraints_dict(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should return dict of constraint name to column list."""
        mock_cursor.fetchall.return_value = [
            ("uq_email", ["email"]),
            ("uq_username", ["username"]),
        ]

        constraints = introspector._get_unique_constraints("public", "users")

        assert "uq_email" in constraints
        assert constraints["uq_email"] == ["email"]
        assert constraints["uq_username"] == ["username"]

    def test_handles_composite_unique(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should handle composite unique constraints."""
        mock_cursor.fetchall.return_value = [
            ("uq_order_product", ["order_id", "product_id"]),
        ]

        constraints = introspector._get_unique_constraints("public", "order_items")

        assert constraints["uq_order_product"] == ["order_id", "product_id"]


class TestGetAllTables(TestSchemaIntrospector):
    """Tests for get_all_tables method."""

    def test_returns_table_names(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Should return list of table names."""
        mock_cursor.fetchall.return_value = [
            ("users",),
            ("orders",),
            ("products",),
        ]

        tables = introspector.get_all_tables("public")

        assert tables == ["users", "orders", "products"]

    def test_validates_schema_name(self, introspector: SchemaIntrospector) -> None:
        """Should validate schema name."""
        with pytest.raises(SecurityError):
            introspector.get_all_tables("bad;schema")

    def test_default_schema_is_public(
        self, introspector: SchemaIntrospector, mock_cursor: MagicMock
    ) -> None:
        """Default schema should be public."""
        mock_cursor.fetchall.return_value = []

        introspector.get_all_tables()

        # Check that 'public' was passed to the query
        call_args = mock_cursor.execute.call_args
        assert call_args[0][1] == ("public",)
