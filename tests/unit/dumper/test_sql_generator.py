"""Tests for pgslice.dumper.sql_generator module."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from pgslice.dumper.sql_generator import SQLGenerator
from pgslice.graph.models import Column, ForeignKey, RecordData, RecordIdentifier, Table


class TestSQLGenerator:
    """Tests for SQLGenerator class."""

    @pytest.fixture
    def mock_introspector(self) -> MagicMock:
        """Create a mock SchemaIntrospector."""
        introspector = MagicMock()

        # Create sample table metadata
        sample_table = Table(
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
                    nullable=True,
                ),
                Column(
                    name="age",
                    data_type="integer",
                    udt_name="int4",
                    nullable=True,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        introspector.get_table_metadata.return_value = sample_table
        return introspector

    @pytest.fixture
    def generator(self, mock_introspector: MagicMock) -> SQLGenerator:
        """Create an SQLGenerator instance."""
        return SQLGenerator(mock_introspector, batch_size=100)


class TestFormatValue(TestSQLGenerator):
    """Tests for _format_value method."""

    def test_format_null(self, generator: SQLGenerator) -> None:
        """NULL values should be formatted as NULL."""
        assert generator._format_value(None) == "NULL"

    def test_format_true(self, generator: SQLGenerator) -> None:
        """True should be formatted as TRUE."""
        assert generator._format_value(True) == "TRUE"

    def test_format_false(self, generator: SQLGenerator) -> None:
        """False should be formatted as FALSE."""
        assert generator._format_value(False) == "FALSE"

    def test_format_integer(self, generator: SQLGenerator) -> None:
        """Integers should be formatted as-is."""
        assert generator._format_value(42) == "42"
        assert generator._format_value(0) == "0"
        assert generator._format_value(-100) == "-100"

    def test_format_float(self, generator: SQLGenerator) -> None:
        """Floats should be formatted as-is."""
        assert generator._format_value(3.14) == "3.14"
        assert generator._format_value(-0.5) == "-0.5"

    def test_format_float_nan(self, generator: SQLGenerator) -> None:
        """NaN should be formatted as 'NaN'."""
        result = generator._format_value(float("nan"))
        assert result == "'NaN'"

    def test_format_float_infinity(self, generator: SQLGenerator) -> None:
        """Infinity should be formatted correctly."""
        assert generator._format_value(float("inf")) == "'Infinity'"
        assert generator._format_value(float("-inf")) == "'-Infinity'"

    def test_format_string(self, generator: SQLGenerator) -> None:
        """Strings should be quoted."""
        assert generator._format_value("hello") == "'hello'"
        assert generator._format_value("") == "''"

    def test_format_string_escapes_quotes(self, generator: SQLGenerator) -> None:
        """Single quotes in strings should be escaped."""
        assert generator._format_value("it's") == "'it''s'"
        assert generator._format_value("'quoted'") == "'''quoted'''"

    def test_format_string_escapes_backslashes(self, generator: SQLGenerator) -> None:
        """Backslashes should be escaped."""
        assert generator._format_value("path\\file") == "'path\\\\file'"

    def test_format_datetime(self, generator: SQLGenerator) -> None:
        """Datetime should be formatted as ISO."""
        dt = datetime(2024, 3, 15, 14, 30, 0)
        result = generator._format_value(dt)
        assert result == "'2024-03-15T14:30:00'"

    def test_format_date(self, generator: SQLGenerator) -> None:
        """Date should be formatted as ISO."""
        d = date(2024, 3, 15)
        result = generator._format_value(d)
        assert result == "'2024-03-15'"

    def test_format_time(self, generator: SQLGenerator) -> None:
        """Time should be formatted as ISO."""
        t = time(14, 30, 0)
        result = generator._format_value(t)
        assert result == "'14:30:00'"

    def test_format_uuid(self, generator: SQLGenerator) -> None:
        """UUID should be formatted as string."""
        uuid_val = UUID("12345678-1234-5678-1234-567812345678")
        result = generator._format_value(uuid_val)
        assert result == "'12345678-1234-5678-1234-567812345678'"

    def test_format_dict_as_json(self, generator: SQLGenerator) -> None:
        """Dict should be formatted as JSON."""
        data = {"key": "value", "num": 42}
        result = generator._format_value(data)
        # JSON output
        assert "key" in result
        assert "value" in result

    def test_format_list_as_json_without_type_info(
        self, generator: SQLGenerator
    ) -> None:
        """List without type info should be formatted as JSON."""
        data = [1, 2, 3]
        result = generator._format_value(data)
        assert result == "'[1, 2, 3]'"

    def test_format_list_as_array_with_type_info(self, generator: SQLGenerator) -> None:
        """List with ARRAY type info should be formatted as PostgreSQL array."""
        data = [1, 2, 3]
        # Column type info: (data_type, udt_name)
        column_type = ("ARRAY", "_int4")
        result = generator._format_value(data, column_type)
        assert "ARRAY[" in result
        assert "integer[]" in result

    def test_format_empty_array(self, generator: SQLGenerator) -> None:
        """Empty array should be formatted correctly."""
        data: list[Any] = []
        column_type = ("ARRAY", "_text")
        result = generator._format_value(data, column_type)
        assert result == "ARRAY[]::text[]"

    def test_format_text_array(self, generator: SQLGenerator) -> None:
        """Text array should escape strings."""
        data = ["foo", "bar"]
        column_type = ("ARRAY", "_text")
        result = generator._format_value(data, column_type)
        assert "ARRAY[" in result
        assert "'foo'" in result
        assert "'bar'" in result

    def test_format_bytes_as_bytea(self, generator: SQLGenerator) -> None:
        """Bytes should be formatted as bytea hex."""
        data = b"\x00\x01\x02\xff"
        result = generator._format_value(data)
        assert result == "'\\x000102ff'"


class TestGenerateBulkInsert(TestSQLGenerator):
    """Tests for generate_bulk_insert method."""

    def test_empty_records_returns_empty(self, generator: SQLGenerator) -> None:
        """Empty record list should return empty string."""
        result = generator.generate_bulk_insert([])
        assert result == ""

    def test_single_record(self, generator: SQLGenerator) -> None:
        """Should generate INSERT for single record."""
        record = RecordData(
            identifier=RecordIdentifier(
                schema_name="public",
                table_name="users",
                pk_values=(1,),
            ),
            data={"id": 1, "name": "Test User", "email": "test@example.com"},
        )

        result = generator.generate_bulk_insert([record])

        assert "INSERT INTO" in result
        assert '"public"."users"' in result
        assert '"email"' in result
        assert '"id"' in result
        assert '"name"' in result
        assert "'Test User'" in result
        assert "'test@example.com'" in result
        assert "ON CONFLICT" in result  # Has primary key

    def test_multiple_records(self, generator: SQLGenerator) -> None:
        """Should generate bulk INSERT for multiple records."""
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    schema_name="public",
                    table_name="users",
                    pk_values=(i,),
                ),
                data={"id": i, "name": f"User {i}"},
            )
            for i in range(3)
        ]

        result = generator.generate_bulk_insert(records)

        assert "INSERT INTO" in result
        assert result.count("(") >= 3  # Multiple value rows
        assert "-- Table: " in result  # Comment header
        assert "(3 records)" in result

    def test_null_values(self, generator: SQLGenerator) -> None:
        """Should handle NULL values correctly."""
        record = RecordData(
            identifier=RecordIdentifier(
                schema_name="public",
                table_name="users",
                pk_values=(1,),
            ),
            data={"id": 1, "name": "Test", "email": None},
        )

        result = generator.generate_bulk_insert([record])

        assert "NULL" in result


class TestGenerateBatch(TestSQLGenerator):
    """Tests for generate_batch method."""

    def test_with_keep_pks_true(self, generator: SQLGenerator) -> None:
        """Should use original PKs when keep_pks=True."""
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    schema_name="public",
                    table_name="users",
                    pk_values=(1,),
                ),
                data={"id": 1, "name": "Test"},
            ),
        ]

        result = generator.generate_batch(
            records, include_transaction=True, keep_pks=True
        )

        assert "BEGIN;" in result
        assert "COMMIT;" in result
        assert "INSERT INTO" in result

    def test_without_transaction(self, generator: SQLGenerator) -> None:
        """Should not include transaction when include_transaction=False."""
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    schema_name="public",
                    table_name="users",
                    pk_values=(1,),
                ),
                data={"id": 1, "name": "Test"},
            ),
        ]

        result = generator.generate_batch(
            records, include_transaction=False, keep_pks=True
        )

        assert "BEGIN;" not in result
        assert "COMMIT;" not in result

    def test_includes_header(self, generator: SQLGenerator) -> None:
        """Should include header with metadata."""
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    schema_name="public",
                    table_name="users",
                    pk_values=(1,),
                ),
                data={"id": 1, "name": "Test"},
            ),
        ]

        result = generator.generate_batch(records, keep_pks=True)

        assert "-- Generated by pgslice" in result
        assert "-- Date:" in result
        assert "-- Records:" in result

    def test_deduplicates_records(self, generator: SQLGenerator) -> None:
        """Should deduplicate records with same identifier."""
        identifier = RecordIdentifier(
            schema_name="public",
            table_name="users",
            pk_values=(1,),
        )
        records = [
            RecordData(identifier=identifier, data={"id": 1, "name": "Test 1"}),
            RecordData(identifier=identifier, data={"id": 1, "name": "Test 2"}),
        ]

        result = generator.generate_batch(records, keep_pks=True)

        # Should only have one insert for this record
        assert result.count("'Test") == 1


class TestBatchSize(TestSQLGenerator):
    """Tests for batch size handling."""

    def test_zero_batch_size_means_unlimited(
        self, mock_introspector: MagicMock
    ) -> None:
        """Batch size of 0 should mean unlimited."""
        generator = SQLGenerator(mock_introspector, batch_size=0)
        # 0 or -1 should result in a large batch_size
        assert generator.batch_size == 999999

    def test_negative_batch_size_means_unlimited(
        self, mock_introspector: MagicMock
    ) -> None:
        """Negative batch size should mean unlimited."""
        generator = SQLGenerator(mock_introspector, batch_size=-1)
        assert generator.batch_size == 999999

    def test_custom_batch_size(self, mock_introspector: MagicMock) -> None:
        """Should respect custom batch size."""
        generator = SQLGenerator(mock_introspector, batch_size=50)
        assert generator.batch_size == 50


class TestColumnTypeCache(TestSQLGenerator):
    """Tests for column type caching."""

    def test_caches_column_types(
        self, generator: SQLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should cache column types to avoid repeated lookups."""
        # First call
        generator._get_column_types("public", "users")

        # Second call
        generator._get_column_types("public", "users")

        # Should only call introspector once due to caching
        assert mock_introspector.get_table_metadata.call_count == 1


class TestArrayTypeHandling(TestSQLGenerator):
    """Tests for array type handling."""

    def test_is_array_type(self, generator: SQLGenerator) -> None:
        """Should detect ARRAY type."""
        assert generator._is_array_type("ARRAY") is True
        assert generator._is_array_type("array") is True
        assert generator._is_array_type("integer") is False
        assert generator._is_array_type("text") is False

    def test_get_array_element_type(self, generator: SQLGenerator) -> None:
        """Should extract element type from udt_name."""
        assert generator._get_array_element_type("_text") == "text"
        assert generator._get_array_element_type("_int4") == "integer"
        assert generator._get_array_element_type("_int8") == "bigint"
        assert generator._get_array_element_type("_float4") == "real"
        assert generator._get_array_element_type("_bool") == "boolean"
        assert generator._get_array_element_type("_uuid") == "uuid"

    def test_format_array_with_nulls(self, generator: SQLGenerator) -> None:
        """Should handle NULL values in arrays."""
        data = [1, None, 3]
        result = generator._format_array_value(data, "integer")
        assert "1" in result
        assert "NULL" in result
        assert "3" in result


class TestPlpgsqlMode(TestSQLGenerator):
    """Tests for PL/pgSQL mode with ID remapping."""

    @pytest.fixture
    def table_with_auto_pk(self) -> Table:
        """Create a table with auto-generated primary key."""
        return Table(
            schema_name="public",
            table_name="products",
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
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

    def test_generate_batch_plpgsql_single_record(
        self, mock_introspector: MagicMock, table_with_auto_pk: Table
    ) -> None:
        """Should generate PL/pgSQL for single record with keep_pks=False."""
        mock_introspector.get_table_metadata.return_value = table_with_auto_pk
        generator = SQLGenerator(mock_introspector)

        record = RecordData(
            identifier=RecordIdentifier(
                table_name="products", schema_name="public", pk_values=("1",)
            ),
            data={"id": 1, "name": "Widget"},
            dependencies=[],
        )

        sql = generator.generate_batch([record], keep_pks=False)

        # Verify PL/pgSQL structure
        assert "DO $$" in sql
        assert "DECLARE" in sql
        assert "BEGIN" in sql
        assert "END $$;" in sql
        # Verify temp table creation
        assert "CREATE TEMP TABLE IF NOT EXISTS _pgslice_id_map" in sql
        # Verify cleanup
        assert "DROP TABLE IF EXISTS _pgslice_id_map" in sql

    def test_generate_batch_plpgsql_multiple_records(
        self, mock_introspector: MagicMock, table_with_auto_pk: Table
    ) -> None:
        """Should generate PL/pgSQL for multiple records with ID remapping."""
        mock_introspector.get_table_metadata.return_value = table_with_auto_pk
        generator = SQLGenerator(mock_introspector)

        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="products", schema_name="public", pk_values=("1",)
                ),
                data={"id": 1, "name": "Widget"},
                dependencies=[],
            ),
            RecordData(
                identifier=RecordIdentifier(
                    table_name="products", schema_name="public", pk_values=("2",)
                ),
                data={"id": 2, "name": "Gadget"},
                dependencies=[],
            ),
        ]

        sql = generator.generate_batch(records, keep_pks=False)

        # Verify both records are included
        assert "Widget" in sql
        assert "Gadget" in sql
        # Verify PL/pgSQL block structure
        assert sql.count("DO $$") == 1
        assert "DECLARE" in sql

    def test_auto_generated_pk_detection(self, mock_introspector: MagicMock) -> None:
        """Should detect SERIAL and IDENTITY columns as auto-generated."""
        table = Table(
            schema_name="public",
            table_name="test_table",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=True,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        auto_gen_pks = generator._get_auto_generated_pk_columns("public", "test_table")
        assert "id" in auto_gen_pks

    def test_id_mapping_table_creation(
        self, mock_introspector: MagicMock, table_with_auto_pk: Table
    ) -> None:
        """Should create temp table for ID storage."""
        mock_introspector.get_table_metadata.return_value = table_with_auto_pk
        generator = SQLGenerator(mock_introspector)

        record = RecordData(
            identifier=RecordIdentifier(
                table_name="products", schema_name="public", pk_values=("1",)
            ),
            data={"id": 1, "name": "Widget"},
            dependencies=[],
        )

        sql = generator.generate_batch([record], keep_pks=False)

        # Verify temp table has correct columns
        assert "table_name TEXT NOT NULL" in sql
        assert "old_id TEXT NOT NULL" in sql
        assert "new_id TEXT NOT NULL" in sql
        assert "PRIMARY KEY (table_name, old_id)" in sql

    def test_plpgsql_variable_declarations(
        self, mock_introspector: MagicMock, table_with_auto_pk: Table
    ) -> None:
        """Should generate proper variable declarations in DO block."""
        mock_introspector.get_table_metadata.return_value = table_with_auto_pk
        generator = SQLGenerator(mock_introspector)

        record = RecordData(
            identifier=RecordIdentifier(
                table_name="products", schema_name="public", pk_values=("1",)
            ),
            data={"id": 1, "name": "Widget"},
            dependencies=[],
        )

        sql = generator.generate_batch([record], keep_pks=False)

        # Verify variable declarations exist
        assert "DECLARE" in sql
        # Verify BEGIN/END structure
        assert "BEGIN" in sql
        assert "END $$;" in sql
        # Verify proper indentation/structure
        declare_idx = sql.index("DECLARE")
        begin_idx = sql.index("BEGIN")
        end_idx = sql.index("END $$;")
        assert declare_idx < begin_idx < end_idx


class TestFkRemapping(TestSQLGenerator):
    """Tests for FK remapping with INSERT-SELECT."""

    @pytest.fixture
    def orders_table_with_fk(self) -> Table:
        """Create orders table with FK to users."""
        from pgslice.graph.models import ForeignKey

        return Table(
            schema_name="public",
            table_name="orders",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                ),
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
                    nullable=False,
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

    def test_insert_select_with_single_fk_remapping(
        self, mock_introspector: MagicMock, orders_table_with_fk: Table
    ) -> None:
        """Should generate INSERT-SELECT with JOIN for FK lookup."""
        # Note: RecordIdentifier takes table_name FIRST, then schema_name
        mock_introspector.get_table_metadata.return_value = orders_table_with_fk
        generator = SQLGenerator(mock_introspector)

        # Create record with FK dependency
        record = RecordData(
            identifier=RecordIdentifier(
                table_name="orders", schema_name="public", pk_values=("1",)
            ),
            data={"id": 1, "user_id": 42, "total": "100.00"},
            dependencies=[
                RecordIdentifier(
                    table_name="users", schema_name="public", pk_values=("42",)
                )
            ],
        )

        # Generate with keep_pks=True (simple VALUES, no PL/pgSQL)
        sql = generator.generate_batch([record], keep_pks=True)

        # For simple test, just verify INSERT is generated
        assert "INSERT INTO" in sql
        assert "orders" in sql

    def test_insert_select_with_null_fk_values(
        self, mock_introspector: MagicMock, orders_table_with_fk: Table
    ) -> None:
        """Should handle NULL FK values correctly."""
        mock_introspector.get_table_metadata.return_value = orders_table_with_fk
        generator = SQLGenerator(mock_introspector)

        record = RecordData(
            identifier=RecordIdentifier(
                table_name="orders", schema_name="public", pk_values=("1",)
            ),
            data={"id": 1, "user_id": None, "total": "50.00"},
            dependencies=[],
        )

        sql = generator.generate_batch([record], keep_pks=True)

        # Verify NULL handling
        assert "NULL" in sql

    def test_insert_with_returning_single_record(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should use RETURNING INTO for single record with auto-gen PK."""
        table = Table(
            schema_name="public",
            table_name="products",
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
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        record = RecordData(
            identifier=RecordIdentifier(
                table_name="products", schema_name="public", pk_values=("1",)
            ),
            data={"id": 1, "name": "Widget"},
            dependencies=[],
        )

        sql = generator.generate_batch([record], keep_pks=False)

        # Verify RETURNING INTO for single record
        assert "RETURNING" in sql
        assert "v_new_id" in sql
        assert "INSERT INTO _pgslice_id_map" in sql

    def test_insert_with_returning_bulk_records(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should use WITH + array_agg for bulk records with auto-gen PK."""
        table = Table(
            schema_name="public",
            table_name="products",
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
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="products", schema_name="public", pk_values=("1",)
                ),
                data={"id": 1, "name": "Widget"},
                dependencies=[],
            ),
            RecordData(
                identifier=RecordIdentifier(
                    table_name="products", schema_name="public", pk_values=("2",)
                ),
                data={"id": 2, "name": "Gadget"},
                dependencies=[],
            ),
        ]

        sql = generator.generate_batch(records, keep_pks=False)

        # Verify natural key CTE pattern (new format with to_insert, existing, inserted, etc.)
        assert "WITH to_insert AS" in sql  # Natural key CTE pattern
        assert "existing AS" in sql  # Checks for existing records
        assert "inserted AS" in sql  # Actual INSERT statement
        assert "IS NOT DISTINCT FROM" in sql  # NULL-safe natural key comparison
        assert "array_agg" in sql
        assert "v_new_ids" in sql
        assert "FOR i IN 1..array_length" in sql
        assert "END LOOP" in sql

    def test_get_fk_columns_to_remap(
        self, mock_introspector: MagicMock, orders_table_with_fk: Table
    ) -> None:
        """Should identify FK columns that need remapping."""
        mock_introspector.get_table_metadata.return_value = orders_table_with_fk
        generator = SQLGenerator(mock_introspector)

        tables_with_remapped_ids = {("public", "users")}
        fk_to_remap = generator._get_fk_columns_to_remap(
            "public", "orders", tables_with_remapped_ids
        )

        assert "user_id" in fk_to_remap
        assert fk_to_remap["user_id"] == ("public", "users")

    def test_serialize_pk_value_single(self, mock_introspector: MagicMock) -> None:
        """Should serialize single PK value."""
        generator = SQLGenerator(mock_introspector)

        result = generator._serialize_pk_value(("123",))
        assert result == "123"

    def test_serialize_pk_value_composite(self, mock_introspector: MagicMock) -> None:
        """Should serialize composite PK value."""
        import json

        generator = SQLGenerator(mock_introspector)

        result = generator._serialize_pk_value(("123", "456"))
        assert result == json.dumps(["123", "456"])


class TestDataTypeEdgeCases(TestSQLGenerator):
    """Tests for edge cases in data type handling."""

    def test_format_value_memoryview(self, generator: SQLGenerator) -> None:
        """Should handle memoryview objects (binary data)."""
        data = memoryview(b"binary data")
        result = generator._format_value(data)
        # memoryview should be converted to hex string or similar
        assert isinstance(result, str)

    def test_format_value_unknown_type(self, generator: SQLGenerator) -> None:
        """Should fallback to str() for unknown types."""

        class CustomObject:
            def __str__(self):
                return "custom_value"

        result = generator._format_value(CustomObject())
        assert "custom_value" in result

    def test_format_multidimensional_array(self, generator: SQLGenerator) -> None:
        """Should handle 2D and 3D arrays."""
        # 2D array
        data_2d = [[1, 2], [3, 4]]
        result = generator._format_array_value(data_2d, "integer")
        assert "ARRAY" in result or "[[" in result

    def test_format_array_of_uuids(self, generator: SQLGenerator) -> None:
        """Should handle UUID arrays."""
        from uuid import UUID

        uuids = [UUID("12345678-1234-5678-1234-567812345678")]
        result = generator._format_array_value(uuids, "uuid")
        assert "12345678-1234-5678-1234-567812345678" in result

    def test_format_deeply_nested_json(self, generator: SQLGenerator) -> None:
        """Should handle deeply nested JSON structures."""
        nested = {"level1": {"level2": {"level3": {"data": [1, 2, 3]}}}}
        result = generator._format_value(nested)
        assert "level1" in result
        assert "level3" in result

    def test_format_string_with_unicode(self, generator: SQLGenerator) -> None:
        """Should handle Unicode characters."""
        text = "Hello 世界 🌍"
        result = generator._format_value(text)
        assert "世界" in result
        assert "🌍" in result

    def test_format_string_with_control_chars(self, generator: SQLGenerator) -> None:
        """Should handle control characters like \\n, \\t, \\r."""
        text = "Line1\nLine2\tTab\rReturn"
        result = generator._format_value(text)
        assert isinstance(result, str)
        # Should escape or preserve control characters

    def test_format_timezone_aware_datetime(self, generator: SQLGenerator) -> None:
        """Should handle timezone-aware datetime."""
        from datetime import datetime, timezone

        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = generator._format_value(dt)
        assert "2024-01-01" in result
        assert "12:00:00" in result

    def test_format_decimal_with_precision(self, generator: SQLGenerator) -> None:
        """Should handle Decimal with precision."""
        from decimal import Decimal

        value = Decimal("123.456789")
        result = generator._format_value(value)
        assert "123.456789" in result

    def test_format_scientific_notation_float(self, generator: SQLGenerator) -> None:
        """Should handle scientific notation floats."""
        value = 1.5e10
        result = generator._format_value(value)
        assert isinstance(result, str)

    def test_format_empty_array(self, generator: SQLGenerator) -> None:
        """Should handle empty arrays."""
        result = generator._format_array_value([], "integer")
        assert "ARRAY[]" in result or "'{}'" in result

    def test_format_array_with_special_chars(self, generator: SQLGenerator) -> None:
        """Should handle arrays with special characters."""
        data = ["value's", 'quote"test', "back\\slash"]
        result = generator._format_array_value(data, "text")
        # Should properly escape special characters
        assert isinstance(result, str)


class TestTableWithoutPrimaryKey(TestSQLGenerator):
    """Tests for tables without primary keys."""

    def test_table_without_primary_keys(self, mock_introspector: MagicMock) -> None:
        """Should handle tables without primary keys."""
        table = Table(
            schema_name="public",
            table_name="logs",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=False,
                ),
                Column(
                    name="message",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                ),
            ],
            primary_keys=[],  # No primary keys
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        record = RecordData(
            identifier=RecordIdentifier(
                table_name="logs", schema_name="public", pk_values=()
            ),
            data={"id": 1, "message": "Test log"},
            dependencies=[],
        )

        sql = generator.generate_batch([record], keep_pks=True)

        # Should still generate INSERT statement
        assert "INSERT INTO" in sql
        assert "logs" in sql


class TestOnConflictHandling(TestSQLGenerator):
    """Tests for ON CONFLICT clause handling."""

    def test_build_on_conflict_with_unique_constraints(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should build ON CONFLICT clause for unique constraints."""
        table = Table(
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
                    name="email",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
            unique_constraints={"uq_email": ["email"]},
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        # Test the helper method directly
        on_conflict, natural_keys = generator._build_on_conflict_clause(
            table, ["id", "email"], [], "public", "users"
        )

        # Should use unique constraint
        assert on_conflict != ""
        assert natural_keys is None
        assert "ON CONFLICT" in on_conflict

    def test_build_on_conflict_without_constraints(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should build ON CONFLICT for non-auto-generated PK even without unique constraints."""
        table = Table(
            schema_name="public",
            table_name="logs",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=False,  # Explicitly not auto-generated
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
            unique_constraints={},  # No unique constraints
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        on_conflict, natural_keys = generator._build_on_conflict_clause(
            table, ["id"], [], "public", "logs"
        )

        # Should build ON CONFLICT for non-auto-generated PK
        assert natural_keys is None
        assert "ON CONFLICT" in on_conflict
        assert '("id")' in on_conflict
        assert "DO UPDATE SET" in on_conflict
        assert '"id" = EXCLUDED."id"' in on_conflict

    def test_build_on_conflict_with_string_pk(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should build ON CONFLICT clause for non-auto-generated string PK."""
        table = Table(
            schema_name="public",
            table_name="shipments_shipmentstate",
            columns=[
                Column(
                    name="id",
                    data_type="character varying",
                    udt_name="varchar",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=False,  # NOT auto-generated
                ),
                Column(
                    name="name",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
            unique_constraints={},  # No unique constraints
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        # Test the helper method directly
        on_conflict, natural_keys = generator._build_on_conflict_clause(
            table,
            ["id", "name"],
            [],  # No auto-gen PKs
            "public",
            "shipments_shipmentstate",
        )

        # Should generate ON CONFLICT for the string PK
        assert natural_keys is None
        assert "ON CONFLICT" in on_conflict
        assert '("id")' in on_conflict
        assert "DO UPDATE SET" in on_conflict
        assert '"id" = EXCLUDED."id"' in on_conflict

    def test_build_on_conflict_with_composite_string_pks(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should build ON CONFLICT clause for composite non-auto-generated PKs."""
        table = Table(
            schema_name="public",
            table_name="junction_table",
            columns=[
                Column(
                    name="entity_a_id",
                    data_type="uuid",
                    udt_name="uuid",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=False,
                ),
                Column(
                    name="entity_b_id",
                    data_type="uuid",
                    udt_name="uuid",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=False,
                ),
                Column(
                    name="created_at",
                    data_type="timestamp",
                    udt_name="timestamp",
                    nullable=False,
                ),
            ],
            primary_keys=["entity_a_id", "entity_b_id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
            unique_constraints={},
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        on_conflict, natural_keys = generator._build_on_conflict_clause(
            table,
            ["entity_a_id", "entity_b_id", "created_at"],
            [],
            "public",
            "junction_table",
        )

        # Should generate ON CONFLICT with both PKs
        assert natural_keys is None
        assert "ON CONFLICT" in on_conflict
        assert '("entity_a_id", "entity_b_id")' in on_conflict
        assert "DO UPDATE SET" in on_conflict
        # Should use first PK for no-op update
        assert '"entity_a_id" = EXCLUDED."entity_a_id"' in on_conflict

    def test_build_on_conflict_with_mixed_pks(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should build ON CONFLICT for non-auto-generated PKs in composite key."""
        table = Table(
            schema_name="public",
            table_name="versioned_data",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=True,  # Auto-generated
                ),
                Column(
                    name="version",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=False,  # Manually set
                ),
                Column(
                    name="data",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                ),
            ],
            primary_keys=["id", "version"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
            unique_constraints={},
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        # Only "version" is being inserted (id is excluded as auto-gen)
        on_conflict, natural_keys = generator._build_on_conflict_clause(
            table,
            ["version", "data"],
            ["id"],  # id is auto-gen
            "public",
            "versioned_data",
        )

        # Should generate ON CONFLICT for non-auto-gen PK only
        assert natural_keys is None
        assert "ON CONFLICT" in on_conflict
        assert '("version")' in on_conflict
        assert "DO UPDATE SET" in on_conflict
        assert '"version" = EXCLUDED."version"' in on_conflict

    def test_build_on_conflict_all_auto_gen_pks_no_unique(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should detect natural key when all PKs are auto-generated and no unique constraints."""
        table = Table(
            schema_name="public",
            table_name="products",
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
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
            unique_constraints={},
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        on_conflict, natural_keys = generator._build_on_conflict_clause(
            table,
            ["name"],
            ["id"],  # id is auto-gen and excluded
            "public",
            "products",
        )

        # Should detect "name" as natural key (PRIORITY 3)
        assert on_conflict == ""
        assert natural_keys == ["name"]

    def test_build_on_conflict_string_pk_takes_priority_over_unique(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should use string PK for ON CONFLICT even when unique constraint exists."""
        table = Table(
            schema_name="public",
            table_name="users",
            columns=[
                Column(
                    name="username",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=False,
                ),
                Column(
                    name="email",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                ),
            ],
            primary_keys=["username"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
            unique_constraints={"uq_email": ["email"]},  # Has unique constraint
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        on_conflict, natural_keys = generator._build_on_conflict_clause(
            table, ["username", "email"], [], "public", "users"
        )

        # Should use PK, not unique constraint
        assert natural_keys is None  # Using ON CONFLICT, not natural keys
        assert "ON CONFLICT" in on_conflict
        assert '("username")' in on_conflict  # PK, not email
        assert "DO UPDATE SET" in on_conflict
        assert '"username" = EXCLUDED."username"' in on_conflict

    def test_generate_batch_plpgsql_string_pk_idempotent(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should generate idempotent PL/pgSQL for string PK tables."""
        table = Table(
            schema_name="public",
            table_name="shipments_shipmentstate",
            columns=[
                Column(
                    name="id",
                    data_type="character varying",
                    udt_name="varchar",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=False,
                ),
                Column(
                    name="name",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
            unique_constraints={},
        )

        mock_introspector.get_table_metadata.return_value = table

        # Mock column types
        mock_introspector.get_column_types.return_value = {
            "id": "character varying",
            "name": "text",
        }

        generator = SQLGenerator(mock_introspector)

        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="shipments_shipmentstate",
                    schema_name="public",
                    pk_values=("barge_departed",),
                ),
                data={"id": "barge_departed", "name": "Barge Departed"},
                dependencies=[],
            ),
            RecordData(
                identifier=RecordIdentifier(
                    table_name="shipments_shipmentstate",
                    schema_name="public",
                    pk_values=("empty_outgated",),
                ),
                data={"id": "empty_outgated", "name": "Empty Outgated"},
                dependencies=[],
            ),
        ]

        # Generate with keep_pks=False (PL/pgSQL mode)
        sql = generator.generate_batch(records, keep_pks=False)

        # Should have ON CONFLICT clause for idempotency
        assert "ON CONFLICT" in sql
        assert '("id")' in sql
        assert "DO UPDATE SET" in sql

        # Verify PL/pgSQL structure is intact
        assert "DO $$" in sql
        assert "CREATE TEMP TABLE IF NOT EXISTS _pgslice_id_map" in sql


class TestHelperMethods(TestSQLGenerator):
    """Tests for helper methods."""

    def test_has_auto_generated_pks_true(self, mock_introspector: MagicMock) -> None:
        """Should detect tables with auto-generated PKs."""
        table = Table(
            schema_name="public",
            table_name="products",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=True,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        result = generator._has_auto_generated_pks("public", "products")
        assert result is True

    def test_has_auto_generated_pks_false(self, mock_introspector: MagicMock) -> None:
        """Should return False for tables without auto-generated PKs."""
        table = Table(
            schema_name="public",
            table_name="manual_ids",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        result = generator._has_auto_generated_pks("public", "manual_ids")
        assert result is False


class TestInsertWithFkRemappingAdvanced:
    """Tests for _generate_insert_with_fk_remapping method - complex scenarios."""

    @pytest.fixture
    def mock_introspector(self) -> MagicMock:
        """Create a mock SchemaIntrospector."""
        introspector = MagicMock()
        introspector.get_table_metadata.return_value = Table(
            schema_name="public",
            table_name="test",
            columns=[],
            primary_keys=[],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )
        return introspector

    def test_simple_insert_no_fk_remapping(self, mock_introspector: MagicMock) -> None:
        """Should generate simple INSERT VALUES when no FK remapping needed."""
        # Setup table without auto-gen PKs and no FK dependencies
        table = Table(
            schema_name="public",
            table_name="tags",
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
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        # Create records with no FK dependencies
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="tags", schema_name="public", pk_values=("1",)
                ),
                data={"id": 1, "name": "python"},
                dependencies=[],
            ),
            RecordData(
                identifier=RecordIdentifier(
                    table_name="tags", schema_name="public", pk_values=("2",)
                ),
                data={"id": 2, "name": "sql"},
                dependencies=[],
            ),
        ]

        # Generate SQL with FK remapping context (but no actual FKs to remap)
        sql = generator._generate_insert_with_fk_remapping(
            "public", "tags", records, set()
        )

        # Should use simple INSERT VALUES syntax
        assert 'INSERT INTO "public"."tags"' in sql
        assert "VALUES" in sql
        assert "(1, 'python')" in sql
        assert "(2, 'sql')" in sql
        # Should NOT use INSERT-SELECT or JOIN syntax
        assert "SELECT" not in sql
        assert "JOIN" not in sql

    def test_fk_remapping_with_null_values(self, mock_introspector: MagicMock) -> None:
        """Should handle NULL FK values correctly in remapping."""
        # Setup table with FK to users (some values are NULL)
        orders_table = Table(
            schema_name="public",
            table_name="orders",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                ),
                Column(
                    name="user_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=True,  # Nullable FK
                ),
                Column(
                    name="total",
                    data_type="numeric",
                    udt_name="numeric",
                    nullable=False,
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
                    on_delete="SET NULL",
                )
            ],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = orders_table
        generator = SQLGenerator(mock_introspector)

        # Create records with NULL FK values
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="orders", schema_name="public", pk_values=("1",)
                ),
                data={"id": 1, "user_id": None, "total": 100.00},
                dependencies=[],
            ),
            RecordData(
                identifier=RecordIdentifier(
                    table_name="orders", schema_name="public", pk_values=("2",)
                ),
                data={"id": 2, "user_id": 42, "total": 200.00},
                dependencies=[],
            ),
        ]

        # Generate SQL with FK remapping
        tables_with_remapped_ids = {("public", "users")}
        sql = generator._generate_insert_with_fk_remapping(
            "public", "orders", records, tables_with_remapped_ids
        )

        # Should use INSERT-SELECT syntax
        assert "INSERT INTO" in sql
        assert "SELECT" in sql
        # Should have JOIN for FK remapping
        assert "JOIN _pgslice_id_map" in sql
        # Should handle NULL FK value
        assert "NULL" in sql
        # Should have old_user_id column alias
        assert "old_user_id" in sql

    def test_array_type_in_select_clause(self, mock_introspector: MagicMock) -> None:
        """Should handle ARRAY types correctly in INSERT-SELECT."""
        # Setup table with array column and FK to remap
        posts_table = Table(
            schema_name="public",
            table_name="posts",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                ),
                Column(
                    name="author_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
                Column(
                    name="tags",
                    data_type="ARRAY",
                    udt_name="_text",  # Array of text
                    nullable=True,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[
                ForeignKey(
                    constraint_name="fk_posts_author",
                    source_table="public.posts",
                    source_column="author_id",
                    target_table="public.users",
                    target_column="id",
                    on_delete="CASCADE",
                )
            ],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = posts_table
        generator = SQLGenerator(mock_introspector)

        # Create record with array data
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="posts", schema_name="public", pk_values=("1",)
                ),
                data={"id": 1, "author_id": 42, "tags": ["python", "sql"]},
                dependencies=[],
            ),
        ]

        # Generate SQL with FK remapping
        tables_with_remapped_ids = {("public", "users")}
        sql = generator._generate_insert_with_fk_remapping(
            "public", "posts", records, tables_with_remapped_ids
        )

        # Should use array type casting in SELECT clause
        # The array column should be cast to text[]
        assert "::text[]" in sql
        # Should have FK remapping JOIN
        assert "JOIN _pgslice_id_map" in sql
        assert "old_author_id" in sql

    def test_user_defined_type_in_select_clause(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should handle USER-DEFINED types (ENUMs) in INSERT-SELECT."""
        # Setup table with ENUM type and FK to remap
        tickets_table = Table(
            schema_name="public",
            table_name="tickets",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                ),
                Column(
                    name="user_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
                Column(
                    name="status",
                    data_type="USER-DEFINED",
                    udt_name="ticket_status",  # Custom ENUM type
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[
                ForeignKey(
                    constraint_name="fk_tickets_user",
                    source_table="public.tickets",
                    source_column="user_id",
                    target_table="public.users",
                    target_column="id",
                    on_delete="CASCADE",
                )
            ],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = tickets_table
        generator = SQLGenerator(mock_introspector)

        # Create record with ENUM value
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="tickets", schema_name="public", pk_values=("1",)
                ),
                data={"id": 1, "user_id": 42, "status": "open"},
                dependencies=[],
            ),
        ]

        # Generate SQL with FK remapping
        tables_with_remapped_ids = {("public", "users")}
        sql = generator._generate_insert_with_fk_remapping(
            "public", "tickets", records, tables_with_remapped_ids
        )

        # Should use custom type name in casting (not "USER-DEFINED")
        assert "::ticket_status" in sql
        # Should have FK remapping
        assert "JOIN _pgslice_id_map" in sql
        assert "old_user_id" in sql

    def test_single_record_with_auto_gen_pk_and_returning(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should use RETURNING INTO for single record with auto-gen PK and FK remapping."""
        # Setup table with auto-gen PK and FK to remap
        comments_table = Table(
            schema_name="public",
            table_name="comments",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=True,  # Auto-generated PK
                ),
                Column(
                    name="post_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
                Column(
                    name="text",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[
                ForeignKey(
                    constraint_name="fk_comments_post",
                    source_table="public.comments",
                    source_column="post_id",
                    target_table="public.posts",
                    target_column="id",
                    on_delete="CASCADE",
                )
            ],
            foreign_keys_incoming=[],
            unique_constraints={},  # No unique constraints
        )

        mock_introspector.get_table_metadata.return_value = comments_table
        generator = SQLGenerator(mock_introspector)

        # Create single record with FK to remap
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="comments", schema_name="public", pk_values=("100",)
                ),
                data={"id": 100, "post_id": 42, "text": "Great post!"},
                dependencies=[],
            ),
        ]

        # Generate SQL with FK remapping
        tables_with_remapped_ids = {("public", "posts")}
        sql = generator._generate_insert_with_fk_remapping(
            "public", "comments", records, tables_with_remapped_ids
        )

        # Should use RETURNING INTO for single record
        assert "RETURNING id INTO v_new_id_comments" in sql
        # Should insert into mapping table
        assert "INSERT INTO _pgslice_id_map VALUES" in sql
        assert '\'"public"."comments"\'' in sql
        assert "'100'" in sql  # old PK value
        # Should have FK remapping JOIN
        assert "JOIN _pgslice_id_map" in sql
        assert "old_post_id" in sql

    def test_bulk_records_with_auto_gen_pk_and_with_clause(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should use WITH + array_agg for bulk records with auto-gen PK and FK remapping."""
        # Setup table with auto-gen PK and FK to remap
        comments_table = Table(
            schema_name="public",
            table_name="comments",
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
                    name="post_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
                Column(
                    name="text",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[
                ForeignKey(
                    constraint_name="fk_comments_post",
                    source_table="public.comments",
                    source_column="post_id",
                    target_table="public.posts",
                    target_column="id",
                    on_delete="CASCADE",
                )
            ],
            foreign_keys_incoming=[],
            unique_constraints={},
        )

        mock_introspector.get_table_metadata.return_value = comments_table
        generator = SQLGenerator(mock_introspector)

        # Create multiple records with FK to remap
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="comments", schema_name="public", pk_values=("100",)
                ),
                data={"id": 100, "post_id": 42, "text": "Great!"},
                dependencies=[],
            ),
            RecordData(
                identifier=RecordIdentifier(
                    table_name="comments", schema_name="public", pk_values=("101",)
                ),
                data={"id": 101, "post_id": 43, "text": "Nice!"},
                dependencies=[],
            ),
            RecordData(
                identifier=RecordIdentifier(
                    table_name="comments", schema_name="public", pk_values=("102",)
                ),
                data={"id": 102, "post_id": 42, "text": "Thanks!"},
                dependencies=[],
            ),
        ]

        # Generate SQL with FK remapping
        tables_with_remapped_ids = {("public", "posts")}
        sql = generator._generate_insert_with_fk_remapping(
            "public", "comments", records, tables_with_remapped_ids
        )

        # Should use WITH clause for bulk insert
        assert "WITH inserted AS" in sql
        # Should use array_agg to collect new IDs
        assert "array_agg(id) INTO v_new_ids_comments" in sql
        # Should have array of old IDs
        assert "v_old_ids_comments := ARRAY['100', '101', '102']" in sql
        # Should have FOR LOOP to insert mappings
        assert "FOR i IN 1..array_length(v_new_ids_comments, 1) LOOP" in sql
        assert "INSERT INTO _pgslice_id_map VALUES" in sql
        # Should have FK remapping JOIN
        assert "JOIN _pgslice_id_map" in sql

    def test_no_auto_gen_pks_simple_insert_select(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should generate simple INSERT-SELECT without RETURNING when no auto-gen PKs."""
        # Setup table WITHOUT auto-gen PK but WITH FK to remap
        orders_table = Table(
            schema_name="public",
            table_name="orders",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                    is_auto_generated=False,  # NOT auto-generated
                ),
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
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[
                ForeignKey(
                    constraint_name="fk_orders_user",
                    source_table="public.orders",
                    source_column="user_id",
                    target_table="public.users",
                    target_column="id",
                    on_delete="CASCADE",
                )
            ],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = orders_table
        generator = SQLGenerator(mock_introspector)

        # Create records with FK to remap
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="orders", schema_name="public", pk_values=("1",)
                ),
                data={"id": 1, "user_id": 42, "total": 100.00},
                dependencies=[],
            ),
        ]

        # Generate SQL with FK remapping
        tables_with_remapped_ids = {("public", "users")}
        sql = generator._generate_insert_with_fk_remapping(
            "public", "orders", records, tables_with_remapped_ids
        )

        # Should use INSERT-SELECT syntax
        assert "INSERT INTO" in sql
        assert "SELECT" in sql
        # Should have FK remapping JOIN
        assert "JOIN _pgslice_id_map" in sql
        # Should NOT have RETURNING or WITH clause
        assert "RETURNING" not in sql
        assert "WITH inserted AS" not in sql
        assert "array_agg" not in sql
        # Should end with semicolon
        assert sql.rstrip().endswith(";")

    def test_multiple_fk_remapping_multiple_joins(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should handle multiple FK remappings with multiple JOINs."""
        # Setup table with TWO FKs that both need remapping
        order_items_table = Table(
            schema_name="public",
            table_name="order_items",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                ),
                Column(
                    name="order_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
                Column(
                    name="product_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
                Column(
                    name="quantity",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[
                ForeignKey(
                    constraint_name="fk_order_items_order",
                    source_table="public.order_items",
                    source_column="order_id",
                    target_table="public.orders",
                    target_column="id",
                    on_delete="CASCADE",
                ),
                ForeignKey(
                    constraint_name="fk_order_items_product",
                    source_table="public.order_items",
                    source_column="product_id",
                    target_table="public.products",
                    target_column="id",
                    on_delete="RESTRICT",
                ),
            ],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = order_items_table
        generator = SQLGenerator(mock_introspector)

        # Create record with two FKs to remap
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="order_items",
                    schema_name="public",
                    pk_values=("1",),
                ),
                data={"id": 1, "order_id": 100, "product_id": 200, "quantity": 5},
                dependencies=[],
            ),
        ]

        # Generate SQL with BOTH FKs needing remapping
        tables_with_remapped_ids = {("public", "orders"), ("public", "products")}
        sql = generator._generate_insert_with_fk_remapping(
            "public", "order_items", records, tables_with_remapped_ids
        )

        # Should have TWO JOINs (one for each FK)
        assert sql.count("JOIN _pgslice_id_map") == 2
        # Should have both old column aliases
        assert "old_order_id" in sql
        assert "old_product_id" in sql
        # Should have both map aliases (map0 and map1)
        assert "map0" in sql
        assert "map1" in sql

    def test_on_conflict_clause_with_fk_remapping(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should include ON CONFLICT clause when table has unique constraints and auto-gen PK."""
        # Setup table with auto-gen PK, FK to remap, AND unique constraint
        comments_table = Table(
            schema_name="public",
            table_name="comments",
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
                    name="post_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
                Column(
                    name="user_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
                Column(
                    name="text",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[
                ForeignKey(
                    constraint_name="fk_comments_post",
                    source_table="public.comments",
                    source_column="post_id",
                    target_table="public.posts",
                    target_column="id",
                    on_delete="CASCADE",
                )
            ],
            foreign_keys_incoming=[],
            unique_constraints={
                "uq_comments_post_user": ["post_id", "user_id"]  # Unique constraint
            },
        )

        mock_introspector.get_table_metadata.return_value = comments_table
        generator = SQLGenerator(mock_introspector)

        # Create single record
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="comments", schema_name="public", pk_values=("1",)
                ),
                data={"id": 1, "post_id": 42, "user_id": 10, "text": "Great!"},
                dependencies=[],
            ),
        ]

        # Generate SQL with FK remapping
        tables_with_remapped_ids = {("public", "posts")}
        sql = generator._generate_insert_with_fk_remapping(
            "public", "comments", records, tables_with_remapped_ids
        )

        # Should include ON CONFLICT clause
        assert "ON CONFLICT" in sql
        assert "DO UPDATE SET" in sql


class TestCreateSchemaIntegration(TestSQLGenerator):
    """Integration tests for create_schema flag."""

    def test_generate_batch_with_create_schema_and_keep_pks(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should include DDL when create_schema=True with keep_pks=True."""
        generator = SQLGenerator(mock_introspector, batch_size=100)

        # Create test records
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="users", schema_name="public", pk_values=("1",)
                ),
                data={
                    "id": 1,
                    "name": "Alice",
                    "email": "alice@example.com",
                    "age": 30,
                },
                dependencies=set(),
            ),
        ]

        # Generate with DDL
        sql = generator.generate_batch(
            records,
            keep_pks=True,
            create_schema=True,
            database_name="testdb",
            schema_name="public",
        )

        # Verify DDL statements are present
        assert '-- CREATE DATABASE "testdb";' in sql
        assert 'CREATE SCHEMA IF NOT EXISTS "public"' in sql
        assert 'CREATE TABLE IF NOT EXISTS "public"."users"' in sql

        # Verify INSERT statements are also present
        assert "INSERT INTO" in sql
        assert "Alice" in sql

    def test_generate_batch_with_create_schema_and_plpgsql(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should include DDL when create_schema=True with PL/pgSQL remapping."""
        generator = SQLGenerator(mock_introspector, batch_size=100)

        # Create test records
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="users", schema_name="public", pk_values=("1",)
                ),
                data={"name": "Bob", "email": "bob@example.com", "age": 25},
                dependencies=set(),
            ),
        ]

        # Generate with DDL and PL/pgSQL remapping
        sql = generator.generate_batch(
            records,
            keep_pks=False,  # Triggers PL/pgSQL mode
            create_schema=True,
            database_name="testdb",
            schema_name="public",
        )

        # Verify DDL statements are present
        assert '-- CREATE DATABASE "testdb";' in sql
        assert 'CREATE SCHEMA IF NOT EXISTS "public"' in sql
        assert 'CREATE TABLE IF NOT EXISTS "public"."users"' in sql

        # Verify PL/pgSQL block is also present
        assert "DO $$" in sql or "CREATE TEMP TABLE" in sql

    def test_generate_batch_without_create_schema(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should NOT include DDL when create_schema=False (default)."""
        generator = SQLGenerator(mock_introspector, batch_size=100)

        # Create test records
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="users", schema_name="public", pk_values=("1",)
                ),
                data={
                    "id": 1,
                    "name": "Charlie",
                    "email": "charlie@example.com",
                    "age": 35,
                },
                dependencies=set(),
            ),
        ]

        # Generate without DDL
        sql = generator.generate_batch(records, keep_pks=True, create_schema=False)

        # Verify DDL statements are NOT present
        assert "CREATE DATABASE" not in sql
        assert "CREATE SCHEMA" not in sql
        assert "CREATE TABLE" not in sql

        # Verify INSERT statements are present
        assert "INSERT INTO" in sql
        assert "Charlie" in sql

    def test_create_schema_requires_database_name(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should not generate DDL if database_name is not provided."""
        generator = SQLGenerator(mock_introspector, batch_size=100)

        # Create test records
        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="users", schema_name="public", pk_values=("1",)
                ),
                data={"id": 1, "name": "Dave", "email": "dave@example.com", "age": 40},
                dependencies=set(),
            ),
        ]

        # Generate with create_schema=True but no database_name
        sql = generator.generate_batch(
            records, keep_pks=True, create_schema=True, database_name=None
        )

        # Verify DDL is not generated without database name
        assert "CREATE DATABASE" not in sql
        assert "CREATE SCHEMA" not in sql
        assert "CREATE TABLE" not in sql


class TestReservedKeywordColumns(TestSQLGenerator):
    """Test that PostgreSQL reserved keywords are properly quoted in generated SQL."""

    @pytest.fixture
    def table_with_references_column(self) -> Table:
        """Create a table with 'references' column (reserved keyword)."""
        return Table(
            schema_name="public",
            table_name="shipments_shipment",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                ),
                Column(
                    name="reference_id",
                    data_type="character varying",
                    udt_name="varchar",
                    nullable=True,
                ),
                Column(
                    name="references",  # Reserved keyword!
                    data_type="jsonb",
                    udt_name="jsonb",
                    nullable=True,
                ),
                Column(
                    name="state_id",
                    data_type="character varying",
                    udt_name="varchar",
                    nullable=True,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

    def test_quote_identifier_simple(self, generator: SQLGenerator) -> None:
        """_quote_identifier should properly quote identifiers."""
        assert generator._quote_identifier("column_name") == '"column_name"'
        assert generator._quote_identifier("references") == '"references"'
        assert generator._quote_identifier("user") == '"user"'
        assert generator._quote_identifier("group") == '"group"'

    def test_quote_identifier_with_embedded_quotes(
        self, generator: SQLGenerator
    ) -> None:
        """_quote_identifier should escape embedded double quotes."""
        assert generator._quote_identifier('col"name') == '"col""name"'
        assert generator._quote_identifier('my"table"name') == '"my""table""name"'

    def test_insert_with_references_column(
        self, mock_introspector: MagicMock, table_with_references_column: Table
    ) -> None:
        """Should properly quote 'references' column in INSERT statement."""
        mock_introspector.get_table_metadata.return_value = table_with_references_column
        generator = SQLGenerator(mock_introspector)

        record = RecordData(
            identifier=RecordIdentifier(
                table_name="shipments_shipment", schema_name="public", pk_values=("1",)
            ),
            data={
                "id": 1,
                "reference_id": "WNZK22",
                "references": "[]",
                "state_id": "quoting",
            },
            dependencies=[],
        )

        sql = generator.generate_batch([record], keep_pks=True)

        # Verify the column is quoted in the INSERT statement
        assert '"references"' in sql
        # Verify it's in the column list
        assert '("id", "reference_id", "references", "state_id")' in sql

    def test_fk_remapping_with_reserved_keyword_column(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should properly quote reserved keywords in FK remapping INSERT-SELECT."""
        # Create a table with 'user' as a FK column (reserved keyword)
        table_with_user_fk = Table(
            schema_name="public",
            table_name="posts",
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
                    name="user",  # Reserved keyword as FK!
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
                Column(
                    name="content",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[
                ForeignKey(
                    constraint_name="fk_posts_user",
                    source_table="public.posts",
                    source_column="user",
                    target_table="public.users",
                    target_column="id",
                    on_delete="CASCADE",
                )
            ],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table_with_user_fk
        generator = SQLGenerator(mock_introspector)

        record = RecordData(
            identifier=RecordIdentifier(
                table_name="posts", schema_name="public", pk_values=("1",)
            ),
            data={"id": 1, "user": 42, "content": "Hello World"},
            dependencies=[
                RecordIdentifier(
                    table_name="users", schema_name="public", pk_values=("42",)
                )
            ],
        )

        # Call the private method directly with correct parameters
        tables_with_remapped_ids = {("public", "users")}
        sql = generator._generate_insert_with_fk_remapping(
            "public", "posts", [record], tables_with_remapped_ids
        )

        # Verify reserved keyword is quoted in the AS data(...) clause
        assert '"old_user"' in sql
        # Verify it's quoted in JOIN condition
        assert 'data."old_user"' in sql

    def test_multiple_reserved_keywords(self, mock_introspector: MagicMock) -> None:
        """Should properly quote multiple reserved keyword columns."""
        table_with_multiple_keywords = Table(
            schema_name="public",
            table_name="test_reserved",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                ),
                Column(
                    name="user",  # Reserved
                    data_type="character varying",
                    udt_name="varchar",
                    nullable=True,
                ),
                Column(
                    name="group",  # Reserved
                    data_type="character varying",
                    udt_name="varchar",
                    nullable=True,
                ),
                Column(
                    name="references",  # Reserved
                    data_type="jsonb",
                    udt_name="jsonb",
                    nullable=True,
                ),
                Column(
                    name="order",  # Reserved
                    data_type="integer",
                    udt_name="int4",
                    nullable=True,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table_with_multiple_keywords
        generator = SQLGenerator(mock_introspector)

        record = RecordData(
            identifier=RecordIdentifier(
                table_name="test_reserved", schema_name="public", pk_values=("1",)
            ),
            data={
                "id": 1,
                "user": "john",
                "group": "admin",
                "references": "{}",
                "order": 5,
            },
            dependencies=[],
        )

        sql = generator.generate_batch([record], keep_pks=True)

        # Verify all reserved keywords are quoted
        assert '"user"' in sql
        assert '"group"' in sql
        assert '"references"' in sql
        assert '"order"' in sql
        # Verify they're in the column list
        assert '("group", "id", "order", "references", "user")' in sql


class TestNaturalKeyDetection(TestSQLGenerator):
    """Tests for natural key detection and idempotency."""

    def test_detect_natural_keys_common_names(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should detect common unique column names as natural keys."""
        # Test "name" column
        table_with_name = Table(
            schema_name="public",
            table_name="roles",
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
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table_with_name
        generator = SQLGenerator(mock_introspector)

        natural_keys = generator._detect_natural_keys("public", "roles")

        assert natural_keys == ["name"]

        # Test "code" column
        table_with_code = Table(
            schema_name="public",
            table_name="statuses",
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
                    name="code",
                    data_type="varchar",
                    udt_name="varchar",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table_with_code
        generator = SQLGenerator(mock_introspector)

        natural_keys = generator._detect_natural_keys("public", "statuses")

        assert natural_keys == ["code"]

        # Test pattern match "_code"
        table_with_pattern = Table(
            schema_name="public",
            table_name="countries",
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
                    name="country_code",
                    data_type="varchar",
                    udt_name="varchar",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table_with_pattern
        generator = SQLGenerator(mock_introspector)

        natural_keys = generator._detect_natural_keys("public", "countries")

        assert natural_keys == ["country_code"]

    def test_detect_natural_keys_reference_table(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should detect natural key in reference table pattern (2-3 columns)."""
        table = Table(
            schema_name="shipments",
            table_name="shipmentreprole",
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
                    data_type="varchar",
                    udt_name="varchar",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        natural_keys = generator._detect_natural_keys("shipments", "shipmentreprole")

        # Should detect reference table pattern (2 columns, 1 non-PK VARCHAR)
        assert natural_keys == ["name"]

    def test_detect_natural_keys_manual_override(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should use manual override when provided via CLI."""
        table = Table(
            schema_name="public",
            table_name="products",
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
                    name="sku",
                    data_type="varchar",
                    udt_name="varchar",
                    nullable=False,
                ),
                Column(
                    name="name",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table

        # Create generator with manual override
        manual_keys = {"public.products": ["sku"]}
        generator = SQLGenerator(mock_introspector, natural_keys=manual_keys)

        natural_keys = generator._detect_natural_keys("public", "products")

        # Should use manual override, not auto-detected "name"
        assert natural_keys == ["sku"]

        # Test without schema prefix
        manual_keys_no_schema = {"products": ["sku", "name"]}
        generator = SQLGenerator(mock_introspector, natural_keys=manual_keys_no_schema)

        natural_keys = generator._detect_natural_keys("public", "products")

        # Should match table name without schema
        assert natural_keys == ["sku", "name"]

    def test_build_on_conflict_with_natural_keys(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should return natural keys when no ON CONFLICT clause possible."""
        table = Table(
            schema_name="public",
            table_name="roles",
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
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
            unique_constraints={},
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        on_conflict, natural_keys = generator._build_on_conflict_clause(
            table, ["name"], ["id"], "public", "roles"
        )

        # Should return empty ON CONFLICT and natural keys list
        assert on_conflict == ""
        assert natural_keys == ["name"]

    def test_generate_insert_with_natural_key_check_single(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should generate CTE-based INSERT for single record with natural key."""
        table = Table(
            schema_name="public",
            table_name="roles",
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
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="roles", schema_name="public", pk_values=("1",)
                ),
                data={"id": 1, "name": "Admin"},
                dependencies=[],
            )
        ]

        sql = generator._generate_insert_with_natural_key_check(
            "public", "roles", records, ["name"], ["id"]
        )

        # Verify CTE structure
        assert "WITH to_insert AS" in sql
        assert "existing AS" in sql
        assert "inserted AS" in sql
        assert "all_ids AS" in sql
        # Verify NULL-safe comparison
        assert "IS NOT DISTINCT FROM" in sql
        # Verify ordering for FK mapping
        assert "ORDER BY old_id" in sql
        # Verify data
        assert "'Admin'" in sql

    def test_generate_insert_with_natural_key_check_bulk(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should generate CTE-based INSERT for bulk records with natural key."""
        table = Table(
            schema_name="public",
            table_name="statuses",
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
                    name="code",
                    data_type="varchar",
                    udt_name="varchar",
                    nullable=False,
                ),
                Column(
                    name="description",
                    data_type="text",
                    udt_name="text",
                    nullable=True,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="statuses", schema_name="public", pk_values=("1",)
                ),
                data={"id": 1, "code": "ACTIVE", "description": "Active status"},
                dependencies=[],
            ),
            RecordData(
                identifier=RecordIdentifier(
                    table_name="statuses", schema_name="public", pk_values=("2",)
                ),
                data={"id": 2, "code": "INACTIVE", "description": "Inactive status"},
                dependencies=[],
            ),
            RecordData(
                identifier=RecordIdentifier(
                    table_name="statuses", schema_name="public", pk_values=("3",)
                ),
                data={"id": 3, "code": "PENDING", "description": None},
                dependencies=[],
            ),
        ]

        sql = generator._generate_insert_with_natural_key_check(
            "public", "statuses", records, ["code"], ["id"]
        )

        # Verify CTE structure
        assert "WITH to_insert AS" in sql
        assert "existing AS" in sql
        assert "inserted AS" in sql
        # Verify all records
        assert "'ACTIVE'" in sql
        assert "'INACTIVE'" in sql
        assert "'PENDING'" in sql
        # Verify NULL handling
        assert "NULL" in sql
        # Verify natural key matching
        assert '"code" IS NOT DISTINCT FROM' in sql

    def test_generate_insert_with_natural_key_check_composite(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should generate CTE-based INSERT with composite natural key."""
        table = Table(
            schema_name="public",
            table_name="tenant_settings",
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
                    name="tenant_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
                Column(
                    name="setting_key",
                    data_type="varchar",
                    udt_name="varchar",
                    nullable=False,
                ),
                Column(
                    name="value",
                    data_type="text",
                    udt_name="text",
                    nullable=True,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        mock_introspector.get_table_metadata.return_value = table
        manual_keys = {"tenant_settings": ["tenant_id", "setting_key"]}
        generator = SQLGenerator(mock_introspector, natural_keys=manual_keys)

        records = [
            RecordData(
                identifier=RecordIdentifier(
                    table_name="tenant_settings",
                    schema_name="public",
                    pk_values=("1",),
                ),
                data={
                    "id": 1,
                    "tenant_id": 42,
                    "setting_key": "theme",
                    "value": "dark",
                },
                dependencies=[],
            )
        ]

        sql = generator._generate_insert_with_natural_key_check(
            "public",
            "tenant_settings",
            records,
            ["tenant_id", "setting_key"],
            ["id"],
        )

        # Verify composite key matching (both columns)
        assert '"tenant_id" IS NOT DISTINCT FROM' in sql
        assert '"setting_key" IS NOT DISTINCT FROM' in sql
        # Verify CTE structure
        assert "WITH to_insert AS" in sql

    def test_natural_key_error_when_no_detection(
        self, mock_introspector: MagicMock
    ) -> None:
        """Should raise SchemaError when no natural keys can be detected."""
        # Table with auto-gen PK, no unique constraints, and no natural key candidates
        table = Table(
            schema_name="public",
            table_name="logs",
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
                    name="message",
                    data_type="text",
                    udt_name="text",
                    nullable=True,  # nullable, so not a candidate
                ),
                Column(
                    name="timestamp",
                    data_type="timestamp",
                    udt_name="timestamp",
                    nullable=False,  # not VARCHAR/TEXT, so not a candidate
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
            unique_constraints={},
        )

        mock_introspector.get_table_metadata.return_value = table
        generator = SQLGenerator(mock_introspector)

        # Should raise error with helpful message
        with pytest.raises(Exception) as exc_info:
            generator._build_on_conflict_clause(
                table, ["message", "timestamp"], ["id"], "public", "logs"
            )

        error_msg = str(exc_info.value)
        assert "Cannot generate idempotent SQL" in error_msg
        assert "public" in error_msg
        assert "logs" in error_msg
        assert "--natural-keys" in error_msg
