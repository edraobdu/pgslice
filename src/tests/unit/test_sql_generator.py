"""Tests for SQL INSERT generation."""

import pytest
from datetime import datetime, date, time
from uuid import UUID
from unittest.mock import Mock

from snippy.dumper.sql_generator import SQLGenerator
from snippy.graph.models import RecordIdentifier, RecordData, Table, Column


class TestSQLGeneratorValueFormatting:
    """Tests for _format_value() method."""

    @pytest.fixture
    def generator(self, mock_introspector):
        """Create SQL generator instance."""
        return SQLGenerator(mock_introspector, batch_size=100)

    def test_null_value(self, generator):
        """Test NULL value formatting."""
        assert generator._format_value(None) == "NULL"

    def test_boolean_true(self, generator):
        """Test TRUE boolean formatting."""
        assert generator._format_value(True) == "TRUE"

    def test_boolean_false(self, generator):
        """Test FALSE boolean formatting."""
        assert generator._format_value(False) == "FALSE"

    def test_integer(self, generator):
        """Test integer formatting."""
        assert generator._format_value(42) == "42"
        assert generator._format_value(-100) == "-100"
        assert generator._format_value(0) == "0"

    def test_float(self, generator):
        """Test float formatting."""
        assert generator._format_value(3.14) == "3.14"
        assert generator._format_value(-2.5) == "-2.5"

    def test_float_special_values(self, generator):
        """Test special float values (NaN, Infinity)."""
        assert generator._format_value(float('nan')) == "'NaN'"
        assert generator._format_value(float('inf')) == "'Infinity'"
        assert generator._format_value(float('-inf')) == "'-Infinity'"

    def test_string_simple(self, generator):
        """Test simple string formatting."""
        assert generator._format_value("hello") == "'hello'"

    def test_string_with_single_quotes(self, generator):
        """Test string with single quotes (escaping)."""
        assert generator._format_value("O'Reilly") == "'O''Reilly'"
        assert generator._format_value("it's") == "'it''s'"

    def test_string_with_backslashes(self, generator):
        """Test string with backslashes (escaping)."""
        assert generator._format_value("C:\\path") == "'C:\\\\path'"
        assert generator._format_value("line\\nbreak") == "'line\\\\nbreak'"

    def test_string_with_both_quotes_and_backslashes(self, generator):
        """Test string with both quotes and backslashes."""
        assert generator._format_value("it's \\path") == "'it''s \\\\path'"

    def test_datetime(self, generator):
        """Test datetime formatting."""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        result = generator._format_value(dt)

        assert result == "'2024-01-15T10:30:45'"

    def test_date(self, generator):
        """Test date formatting."""
        d = date(2024, 1, 15)
        result = generator._format_value(d)

        assert result == "'2024-01-15'"

    def test_time(self, generator):
        """Test time formatting."""
        t = time(10, 30, 45)
        result = generator._format_value(t)

        assert result == "'10:30:45'"

    def test_uuid(self, generator):
        """Test UUID formatting."""
        uuid = UUID('12345678-1234-5678-1234-567812345678')
        result = generator._format_value(uuid)

        assert result == "'12345678-1234-5678-1234-567812345678'"

    def test_dict_json(self, generator):
        """Test dict (JSON) formatting."""
        data = {"key": "value", "number": 42}
        result = generator._format_value(data)

        assert "'key': 'value'" in result or '"key": "value"' in result
        # JSON should be escaped
        assert result.startswith("'")
        assert result.endswith("'")

    def test_list_json(self, generator):
        """Test list (JSON) formatting."""
        data = [1, 2, 3, "test"]
        result = generator._format_value(data)

        # JSON should be escaped and quoted
        assert result.startswith("'")
        assert result.endswith("'")

    def test_bytes_bytea(self, generator):
        """Test bytes (bytea) formatting."""
        data = b"hello"
        result = generator._format_value(data)

        assert result == "'\\x68656c6c6f'"  # hex encoding

    def test_memoryview(self, generator):
        """Test memoryview formatting."""
        data = memoryview(b"test")
        result = generator._format_value(data)

        assert result == "'\\x74657374'"

    def test_empty_string(self, generator):
        """Test empty string formatting."""
        assert generator._format_value("") == "''"

    def test_unicode_string(self, generator):
        """Test Unicode string formatting."""
        assert generator._format_value("日本語") == "'日本語'"
        assert generator._format_value("émoji🔥") == "'émoji🔥'"


class TestSQLGeneratorBulkInsert:
    """Tests for generate_bulk_insert() method."""

    @pytest.fixture
    def mock_table_metadata(self):
        """Create mock table metadata."""
        return Table(
            schema_name="public",
            table_name="users",
            columns=[],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

    @pytest.fixture
    def generator(self, mock_introspector, mock_table_metadata):
        """Create SQL generator with mocked introspector."""
        mock_introspector.get_table_metadata.return_value = mock_table_metadata
        return SQLGenerator(mock_introspector, batch_size=100)

    def test_empty_records(self, generator):
        """Test generating bulk INSERT with empty record list."""
        result = generator.generate_bulk_insert([])

        assert result == ""

    def test_single_record(self, generator):
        """Test generating bulk INSERT with single record."""
        record = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 1}),
            data={"id": 1, "username": "alice"},
            dependencies=[],
        )

        result = generator.generate_bulk_insert([record])

        assert "INSERT INTO" in result
        assert "public.users" in result
        assert "id" in result
        assert "username" in result
        assert "VALUES" in result
        assert "(1, 'alice')" in result
        assert "ON CONFLICT" in result

    def test_multiple_records(self, generator):
        """Test generating bulk INSERT with multiple records."""
        records = [
            RecordData(
                identifier=RecordIdentifier("public", "users", {"id": i}),
                data={"id": i, "username": f"user{i}"},
                dependencies=[],
            )
            for i in range(1, 4)
        ]

        result = generator.generate_bulk_insert(records)

        assert result.count("INSERT INTO") == 1  # Single INSERT statement
        assert result.count("VALUES") == 1
        assert "(1, 'user1')" in result
        assert "(2, 'user2')" in result
        assert "(3, 'user3')" in result

    def test_on_conflict_clause(self, generator):
        """Test ON CONFLICT clause is generated correctly."""
        record = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 1}),
            data={"id": 1},
            dependencies=[],
        )

        result = generator.generate_bulk_insert([record])

        assert "ON CONFLICT (\"id\") DO NOTHING" in result

    def test_table_without_primary_key(self, generator, mock_introspector):
        """Test table without primary key has no ON CONFLICT clause."""
        # Create metadata with no primary keys
        metadata = Table(
            schema_name="public",
            table_name="logs",
            columns=[],
            primary_keys=[],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )
        mock_introspector.get_table_metadata.return_value = metadata

        record = RecordData(
            identifier=RecordIdentifier("public", "logs", {"id": 1}),
            data={"id": 1, "message": "test"},
            dependencies=[],
        )

        result = generator.generate_bulk_insert([record])

        assert "ON CONFLICT" not in result

    def test_columns_are_sorted(self, generator):
        """Test columns in INSERT are sorted alphabetically."""
        record = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 1}),
            data={"username": "alice", "email": "alice@example.com", "id": 1},
            dependencies=[],
        )

        result = generator.generate_bulk_insert([record])

        # Extract columns from INSERT statement
        # Should be: ("email", "id", "username") - alphabetically sorted
        assert result.index('"email"') < result.index('"id"')
        assert result.index('"id"') < result.index('"username"')


class TestSQLGeneratorBatch:
    """Tests for generate_batch() method."""

    @pytest.fixture
    def mock_table_metadata(self):
        """Create mock table metadata."""
        return Table(
            schema_name="public",
            table_name="users",
            columns=[],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

    @pytest.fixture
    def generator(self, mock_introspector, mock_table_metadata):
        """Create SQL generator."""
        mock_introspector.get_table_metadata.return_value = mock_table_metadata
        return SQLGenerator(mock_introspector, batch_size=2)

    def test_empty_records(self, generator):
        """Test generating batch with no records."""
        result = generator.generate_batch([])

        assert "BEGIN;" in result
        assert "COMMIT;" in result
        assert "-- Records: 0" in result

    def test_batch_includes_transaction(self, generator):
        """Test batch includes BEGIN/COMMIT by default."""
        record = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 1}),
            data={"id": 1},
            dependencies=[],
        )

        result = generator.generate_batch([record])

        assert "BEGIN;" in result
        assert "COMMIT;" in result

    def test_batch_without_transaction(self, generator):
        """Test batch without transaction wrapping."""
        record = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 1}),
            data={"id": 1},
            dependencies=[],
        )

        result = generator.generate_batch([record], include_transaction=False)

        assert "BEGIN;" not in result
        assert "COMMIT;" not in result

    def test_batch_size_enforcement(self, generator):
        """Test records are split into batches."""
        # Generator has batch_size=2, create 5 records
        records = [
            RecordData(
                identifier=RecordIdentifier("public", "users", {"id": i}),
                data={"id": i},
                dependencies=[],
            )
            for i in range(1, 6)
        ]

        result = generator.generate_batch(records)

        # Should have 3 INSERT statements (2, 2, 1)
        assert result.count("INSERT INTO") == 3

    def test_header_comment(self, generator):
        """Test batch includes header comments."""
        record = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 1}),
            data={"id": 1},
            dependencies=[],
        )

        result = generator.generate_batch([record])

        assert "-- Generated by snippy" in result
        assert "-- Date:" in result
        assert "-- Records: 1" in result
        assert "-- Batch size:" in result

    def test_generate_batch_deduplicates_records(self, generator):
        """Test SQL generator handles duplicate RecordData in input list."""
        # Create duplicate RecordData (same identifier, same data)
        record1 = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 3}),
            data={"id": 3, "username": "alice", "email": "alice@example.com"},
            dependencies=[],
        )
        # Create another record with the same identifier (duplicate)
        record2 = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 3}),
            data={"id": 3, "username": "alice", "email": "alice@example.com"},
            dependencies=[],
        )
        # Create a different record
        record3 = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 5}),
            data={"id": 5, "username": "bob", "email": "bob@example.com"},
            dependencies=[],
        )

        # Pass list with duplicate record
        records = [record1, record2, record3]
        result = generator.generate_batch(records)

        # Count occurrences of the duplicate record's data in the result
        # Should appear only once, not twice
        assert result.count("'alice@example.com'") == 1
        assert result.count("'alice'") == 1

        # The other record should still be there
        assert result.count("'bob@example.com'") == 1
        assert result.count("'bob'") == 1

        # Should only have 2 value rows (one for alice, one for bob)
        # Count the pattern of closing parenthesis followed by comma or ON CONFLICT
        # This is a simple heuristic - the VALUES clause should have 2 rows
        lines = result.split('\n')
        values_section_started = False
        value_row_count = 0

        for line in lines:
            if 'VALUES' in line:
                values_section_started = True
                continue
            if values_section_started and line.strip().startswith('('):
                value_row_count += 1
            if 'ON CONFLICT' in line:
                break

        assert value_row_count == 2
