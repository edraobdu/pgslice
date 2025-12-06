"""Tests for graph data models."""

import pytest
from datetime import datetime

from snippy.graph.models import (
    RecordIdentifier,
    RecordData,
    ForeignKey,
    TimeframeFilter,
)


class TestRecordIdentifier:
    """Tests for RecordIdentifier model."""

    def test_creation(self):
        """Test RecordIdentifier creation."""
        record_id = RecordIdentifier("public", "users", {"id": 1})

        assert record_id.schema_name == "public"
        assert record_id.table_name == "users"
        assert record_id.pk_values == {"id": 1}

    def test_equality(self):
        """Test RecordIdentifier equality comparison."""
        id1 = RecordIdentifier("public", "users", {"id": 1})
        id2 = RecordIdentifier("public", "users", {"id": 1})
        id3 = RecordIdentifier("public", "users", {"id": 2})
        id4 = RecordIdentifier("public", "orders", {"id": 1})

        assert id1 == id2
        assert id1 != id3
        assert id1 != id4

    def test_hashing_consistency(self):
        """Test RecordIdentifier hashing is consistent."""
        id1 = RecordIdentifier("public", "users", {"id": 1})
        id2 = RecordIdentifier("public", "users", {"id": 1})

        assert hash(id1) == hash(id2)
        assert id1 in {id2}  # Can be used in sets

    def test_composite_primary_key(self):
        """Test RecordIdentifier with composite primary key."""
        record_id = RecordIdentifier("public", "user_groups", {"user_id": 1, "group_id": 2})

        assert record_id.pk_values == {"user_id": 1, "group_id": 2}

    def test_full_name_property(self):
        """Test RecordIdentifier full_name property."""
        record_id = RecordIdentifier("public", "users", {"id": 1})

        assert record_id.full_name == "public.users"

    def test_immutability(self):
        """Test RecordIdentifier is immutable (frozen dataclass)."""
        record_id = RecordIdentifier("public", "users", {"id": 1})

        with pytest.raises(Exception):  # FrozenInstanceError
            record_id.schema_name = "other"


class TestRecordData:
    """Tests for RecordData model."""

    def test_creation(self):
        """Test RecordData creation."""
        identifier = RecordIdentifier("public", "users", {"id": 1})
        data = {"id": 1, "username": "alice", "email": "alice@example.com"}
        dependencies = [RecordIdentifier("public", "roles", {"id": 1})]

        record = RecordData(
            identifier=identifier,
            data=data,
            dependencies=dependencies,
        )

        assert record.identifier == identifier
        assert record.data == data
        assert record.dependencies == dependencies

    def test_no_dependencies(self):
        """Test RecordData with no dependencies."""
        identifier = RecordIdentifier("public", "roles", {"id": 1})
        data = {"id": 1, "name": "admin"}

        record = RecordData(
            identifier=identifier,
            data=data,
            dependencies=[],
        )

        assert len(record.dependencies) == 0

    def test_immutability(self):
        """Test RecordData is immutable (frozen dataclass)."""
        identifier = RecordIdentifier("public", "users", {"id": 1})
        record = RecordData(
            identifier=identifier,
            data={"id": 1},
            dependencies=[],
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            record.data = {"id": 2}


class TestForeignKey:
    """Tests for ForeignKey model."""

    def test_creation(self):
        """Test ForeignKey creation."""
        fk = ForeignKey(
            source_table="users",
            source_column="role_id",
            target_table="roles",
            target_column="id",
        )

        assert fk.source_table == "users"
        assert fk.source_column == "role_id"
        assert fk.target_table == "roles"
        assert fk.target_column == "id"

    def test_immutability(self):
        """Test ForeignKey is immutable (frozen dataclass)."""
        fk = ForeignKey(
            source_table="users",
            source_column="role_id",
            target_table="roles",
            target_column="id",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            fk.source_table = "orders"


class TestTimeframeFilter:
    """Tests for TimeframeFilter model."""

    def test_creation(self):
        """Test TimeframeFilter creation."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)

        tf = TimeframeFilter(
            table_name="transactions",
            column_name="created_at",
            start_date=start,
            end_date=end,
        )

        assert tf.table_name == "transactions"
        assert tf.column_name == "created_at"
        assert tf.start_date == start
        assert tf.end_date == end

    def test_string_representation(self):
        """Test TimeframeFilter __str__ method."""
        tf = TimeframeFilter(
            table_name="transactions",
            column_name="created_at",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
        )

        str_repr = str(tf)
        assert "transactions" in str_repr
        assert "created_at" in str_repr

    def test_immutability(self):
        """Test TimeframeFilter is immutable (frozen dataclass)."""
        tf = TimeframeFilter(
            table_name="transactions",
            column_name="created_at",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            tf.table_name = "orders"
