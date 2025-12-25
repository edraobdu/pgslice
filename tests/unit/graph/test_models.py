"""Tests for pgslice.graph.models module."""

from __future__ import annotations

from datetime import datetime

import pytest
from faker import Faker

from pgslice.graph.models import (
    Column,
    ColumnType,
    ForeignKey,
    RecordData,
    RecordIdentifier,
    Table,
    TimeframeFilter,
)

fake = Faker()


class TestColumnType:
    """Tests for ColumnType enum."""

    def test_integer_type(self) -> None:
        """Should have integer type."""
        assert ColumnType.INTEGER.value == "integer"

    def test_text_type(self) -> None:
        """Should have text type."""
        assert ColumnType.TEXT.value == "text"

    def test_timestamp_types(self) -> None:
        """Should have timestamp types."""
        assert ColumnType.TIMESTAMP.value == "timestamp"
        assert ColumnType.TIMESTAMPTZ.value == "timestamptz"

    def test_json_types(self) -> None:
        """Should have JSON types."""
        assert ColumnType.JSON.value == "json"
        assert ColumnType.JSONB.value == "jsonb"

    def test_other_type_for_unknown(self) -> None:
        """Should have OTHER type for unknown types."""
        assert ColumnType.OTHER.value == "other"

    def test_all_expected_types_exist(self) -> None:
        """All expected PostgreSQL types should exist."""
        expected_types = [
            "INTEGER",
            "BIGINT",
            "SMALLINT",
            "TEXT",
            "VARCHAR",
            "CHAR",
            "BOOLEAN",
            "TIMESTAMP",
            "TIMESTAMPTZ",
            "DATE",
            "TIME",
            "UUID",
            "JSON",
            "JSONB",
            "NUMERIC",
            "REAL",
            "DOUBLE",
            "BYTEA",
            "ARRAY",
            "OTHER",
        ]
        for type_name in expected_types:
            assert hasattr(ColumnType, type_name), f"Missing type: {type_name}"


class TestColumn:
    """Tests for Column dataclass."""

    def test_create_basic_column(self) -> None:
        """Can create a basic column."""
        col = Column(
            name="id",
            data_type="integer",
            udt_name="int4",
            nullable=False,
        )
        assert col.name == "id"
        assert col.data_type == "integer"
        assert col.udt_name == "int4"
        assert col.nullable is False

    def test_default_values(self) -> None:
        """Should have correct default values."""
        col = Column(
            name="test",
            data_type="text",
            udt_name="text",
            nullable=True,
        )
        assert col.default is None
        assert col.is_primary_key is False
        assert col.is_auto_generated is False

    def test_primary_key_column(self) -> None:
        """Can create a primary key column."""
        col = Column(
            name="id",
            data_type="integer",
            udt_name="int4",
            nullable=False,
            is_primary_key=True,
            is_auto_generated=True,
        )
        assert col.is_primary_key is True
        assert col.is_auto_generated is True

    def test_column_with_default(self) -> None:
        """Can create column with default value."""
        col = Column(
            name="created_at",
            data_type="timestamp",
            udt_name="timestamp",
            nullable=True,
            default="now()",
        )
        assert col.default == "now()"

    def test_column_is_frozen(self) -> None:
        """Column dataclass should be frozen (immutable)."""
        col = Column(
            name="test",
            data_type="text",
            udt_name="text",
            nullable=True,
        )
        with pytest.raises(AttributeError):
            col.name = "new_name"  # type: ignore


class TestForeignKey:
    """Tests for ForeignKey dataclass."""

    def test_create_basic_foreign_key(self) -> None:
        """Can create a basic foreign key."""
        fk = ForeignKey(
            constraint_name="fk_orders_user_id",
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
        )
        assert fk.constraint_name == "fk_orders_user_id"
        assert fk.source_table == "orders"
        assert fk.source_column == "user_id"
        assert fk.target_table == "users"
        assert fk.target_column == "id"

    def test_default_on_delete(self) -> None:
        """Default on_delete should be NO ACTION."""
        fk = ForeignKey(
            constraint_name="fk_test",
            source_table="a",
            source_column="b_id",
            target_table="b",
            target_column="id",
        )
        assert fk.on_delete == "NO ACTION"

    def test_cascade_on_delete(self) -> None:
        """Can set CASCADE on_delete."""
        fk = ForeignKey(
            constraint_name="fk_test",
            source_table="a",
            source_column="b_id",
            target_table="b",
            target_column="id",
            on_delete="CASCADE",
        )
        assert fk.on_delete == "CASCADE"

    def test_foreign_key_is_hashable(self) -> None:
        """ForeignKey should be hashable for use in sets."""
        fk = ForeignKey(
            constraint_name="fk_test",
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
        )
        # Should not raise
        hash_val = hash(fk)
        assert isinstance(hash_val, int)

    def test_foreign_key_in_set(self) -> None:
        """ForeignKey should work in sets."""
        fk1 = ForeignKey(
            constraint_name="fk_1",
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
        )
        fk2 = ForeignKey(
            constraint_name="fk_1",
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
        )
        # Identical ForeignKeys - should have same hash
        fk_set = {fk1, fk2}
        # Same FK, so set should have 1 element
        assert len(fk_set) == 1

    def test_foreign_key_different_constraints_in_set(self) -> None:
        """ForeignKeys with different constraint names are different."""
        fk1 = ForeignKey(
            constraint_name="fk_1",
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
        )
        fk2 = ForeignKey(
            constraint_name="fk_2",
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
        )
        # Different constraint names - different FKs
        fk_set = {fk1, fk2}
        # Different FKs, so set should have 2 elements
        assert len(fk_set) == 2

    def test_foreign_key_is_frozen(self) -> None:
        """ForeignKey dataclass should be frozen."""
        fk = ForeignKey(
            constraint_name="fk_test",
            source_table="a",
            source_column="b_id",
            target_table="b",
            target_column="id",
        )
        with pytest.raises(AttributeError):
            fk.source_table = "new_table"  # type: ignore


class TestTable:
    """Tests for Table dataclass."""

    def test_create_basic_table(self) -> None:
        """Can create a basic table."""
        col = Column(
            name="id",
            data_type="integer",
            udt_name="int4",
            nullable=False,
            is_primary_key=True,
        )
        table = Table(
            schema_name="public",
            table_name="users",
            columns=[col],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )
        assert table.schema_name == "public"
        assert table.table_name == "users"
        assert len(table.columns) == 1

    def test_full_name_property(self) -> None:
        """full_name property should return schema.table."""
        table = Table(
            schema_name="custom",
            table_name="orders",
            columns=[],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )
        assert table.full_name == "custom.orders"

    def test_table_with_foreign_keys(self) -> None:
        """Can create table with foreign keys."""
        fk = ForeignKey(
            constraint_name="fk_orders_user_id",
            source_table="orders",
            source_column="user_id",
            target_table="users",
            target_column="id",
        )
        table = Table(
            schema_name="public",
            table_name="orders",
            columns=[],
            primary_keys=["id"],
            foreign_keys_outgoing=[fk],
            foreign_keys_incoming=[],
        )
        assert len(table.foreign_keys_outgoing) == 1
        assert table.foreign_keys_outgoing[0].target_table == "users"

    def test_unique_constraints_default(self) -> None:
        """unique_constraints should default to empty dict."""
        table = Table(
            schema_name="public",
            table_name="test",
            columns=[],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )
        assert table.unique_constraints == {}

    def test_table_with_unique_constraints(self) -> None:
        """Can create table with unique constraints."""
        table = Table(
            schema_name="public",
            table_name="users",
            columns=[],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
            unique_constraints={"uq_email": ["email"]},
        )
        assert "uq_email" in table.unique_constraints
        assert table.unique_constraints["uq_email"] == ["email"]


class TestRecordIdentifier:
    """Tests for RecordIdentifier dataclass."""

    def test_create_basic_identifier(self) -> None:
        """Can create a basic record identifier."""
        rid = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        assert rid.table_name == "users"
        assert rid.schema_name == "public"
        assert rid.pk_values == ("1",)  # Normalized to string

    def test_pk_values_normalized_to_strings(self) -> None:
        """Primary key values should be normalized to strings."""
        rid = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(42,),
        )
        assert rid.pk_values == ("42",)
        assert isinstance(rid.pk_values[0], str)

    def test_composite_primary_key(self) -> None:
        """Should support composite primary keys."""
        rid = RecordIdentifier(
            table_name="order_items",
            schema_name="public",
            pk_values=(1, 2),
        )
        assert rid.pk_values == ("1", "2")

    def test_identifier_is_hashable(self) -> None:
        """RecordIdentifier should be hashable."""
        rid = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        hash_val = hash(rid)
        assert isinstance(hash_val, int)

    def test_identifier_in_set(self) -> None:
        """RecordIdentifier should work in sets."""
        rid1 = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        rid2 = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        rid3 = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(2,),
        )
        rid_set = {rid1, rid2, rid3}
        assert len(rid_set) == 2  # rid1 and rid2 are equal

    def test_identifier_equality(self) -> None:
        """Equal identifiers should be equal."""
        rid1 = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        rid2 = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        assert rid1 == rid2

    def test_identifier_inequality_different_table(self) -> None:
        """Different tables should not be equal."""
        rid1 = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        rid2 = RecordIdentifier(
            table_name="orders",
            schema_name="public",
            pk_values=(1,),
        )
        assert rid1 != rid2

    def test_identifier_inequality_different_pk(self) -> None:
        """Different PKs should not be equal."""
        rid1 = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        rid2 = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(2,),
        )
        assert rid1 != rid2

    def test_identifier_repr(self) -> None:
        """repr should show schema.table(pk)."""
        rid = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(42,),
        )
        assert repr(rid) == "public.users(42)"

    def test_identifier_repr_composite(self) -> None:
        """repr should show composite PKs."""
        rid = RecordIdentifier(
            table_name="order_items",
            schema_name="public",
            pk_values=(1, 2),
        )
        assert repr(rid) == "public.order_items(1, 2)"

    def test_identifier_not_equal_to_other_types(self) -> None:
        """RecordIdentifier should not equal other types."""
        rid = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        assert rid != "public.users(1)"
        assert rid != 1
        assert rid != None  # noqa: E711


class TestRecordData:
    """Tests for RecordData dataclass."""

    def test_create_basic_record_data(self) -> None:
        """Can create basic record data."""
        rid = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        data = RecordData(
            identifier=rid,
            data={"id": 1, "name": "Test User"},
        )
        assert data.identifier == rid
        assert data.data["id"] == 1
        assert data.data["name"] == "Test User"

    def test_dependencies_default_empty(self) -> None:
        """Dependencies should default to empty set."""
        rid = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        data = RecordData(identifier=rid, data={})
        assert data.dependencies == set()

    def test_record_data_with_dependencies(self) -> None:
        """Can create record with dependencies."""
        user_rid = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        order_rid = RecordIdentifier(
            table_name="orders",
            schema_name="public",
            pk_values=(100,),
        )
        order_data = RecordData(
            identifier=order_rid,
            data={"id": 100, "user_id": 1},
            dependencies={user_rid},
        )
        assert user_rid in order_data.dependencies

    def test_record_data_is_hashable(self) -> None:
        """RecordData should be hashable (based on identifier)."""
        rid = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        data = RecordData(identifier=rid, data={"id": 1})
        hash_val = hash(data)
        assert isinstance(hash_val, int)

    def test_record_data_equality_based_on_identifier(self) -> None:
        """RecordData equality should be based on identifier."""
        rid = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        data1 = RecordData(identifier=rid, data={"id": 1, "name": "User 1"})
        data2 = RecordData(identifier=rid, data={"id": 1, "name": "Different"})
        assert data1 == data2  # Same identifier

    def test_record_data_in_set(self) -> None:
        """RecordData should work in sets."""
        rid1 = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        rid2 = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(2,),
        )
        data1 = RecordData(identifier=rid1, data={"id": 1})
        data2 = RecordData(identifier=rid1, data={"id": 1, "extra": "field"})
        data3 = RecordData(identifier=rid2, data={"id": 2})

        data_set = {data1, data2, data3}
        assert len(data_set) == 2  # data1 and data2 have same identifier

    def test_record_data_not_equal_to_other_types(self) -> None:
        """RecordData should not equal other types."""
        rid = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        data = RecordData(identifier=rid, data={"id": 1})
        assert data != rid  # Not equal to just the identifier
        assert data != {"id": 1}
        assert data != None  # noqa: E711


class TestTimeframeFilter:
    """Tests for TimeframeFilter dataclass."""

    def test_create_basic_filter(self) -> None:
        """Can create a basic timeframe filter."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        tf = TimeframeFilter(
            table_name="orders",
            column_name="created_at",
            start_date=start,
            end_date=end,
        )
        assert tf.table_name == "orders"
        assert tf.column_name == "created_at"
        assert tf.start_date == start
        assert tf.end_date == end

    def test_filter_repr(self) -> None:
        """repr should show readable date range."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        tf = TimeframeFilter(
            table_name="orders",
            column_name="created_at",
            start_date=start,
            end_date=end,
        )
        repr_str = repr(tf)
        assert "orders.created_at" in repr_str
        assert "2024-01-01" in repr_str
        assert "2024-12-31" in repr_str

    def test_filter_with_different_column(self) -> None:
        """Can filter on different columns."""
        tf = TimeframeFilter(
            table_name="events",
            column_name="event_date",
            start_date=datetime(2024, 6, 1),
            end_date=datetime(2024, 6, 30),
        )
        assert tf.column_name == "event_date"
