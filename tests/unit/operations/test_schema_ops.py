"""Tests for shared schema operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pgslice.operations.schema_ops import describe_table, list_tables, print_tables


class TestListTables:
    """Tests for list_tables function."""

    def test_returns_table_list(self) -> None:
        """Should return list of tables from introspector."""
        mock_conn_manager = MagicMock()
        mock_conn = MagicMock()
        mock_conn_manager.get_connection.return_value = mock_conn

        with patch("pgslice.operations.schema_ops.SchemaIntrospector") as mock_intro:
            mock_introspector = MagicMock()
            mock_introspector.get_all_tables.return_value = ["users", "orders"]
            mock_intro.return_value = mock_introspector

            result = list_tables(mock_conn_manager, "public")

            assert result == ["users", "orders"]
            mock_introspector.get_all_tables.assert_called_once_with("public")

    def test_uses_provided_schema(self) -> None:
        """Should use the provided schema."""
        mock_conn_manager = MagicMock()
        mock_conn = MagicMock()
        mock_conn_manager.get_connection.return_value = mock_conn

        with patch("pgslice.operations.schema_ops.SchemaIntrospector") as mock_intro:
            mock_introspector = MagicMock()
            mock_introspector.get_all_tables.return_value = []
            mock_intro.return_value = mock_introspector

            list_tables(mock_conn_manager, "custom_schema")

            mock_introspector.get_all_tables.assert_called_once_with("custom_schema")


class TestPrintTables:
    """Tests for print_tables function."""

    def test_prints_formatted_output(self) -> None:
        """Should print tables with formatting."""
        with patch("pgslice.operations.schema_ops.printy") as mock_printy:
            print_tables(["users", "orders"], "public")

            # Check header was printed
            calls = [str(call) for call in mock_printy.call_args_list]
            assert any("Tables in schema 'public'" in call for call in calls)
            assert any("Total: 2 tables" in call for call in calls)

    def test_handles_empty_list(self) -> None:
        """Should handle empty table list."""
        with patch("pgslice.operations.schema_ops.printy") as mock_printy:
            print_tables([], "public")

            calls = [str(call) for call in mock_printy.call_args_list]
            assert any("Total: 0 tables" in call for call in calls)


class TestDescribeTable:
    """Tests for describe_table function."""

    @pytest.fixture
    def mock_table(self) -> MagicMock:
        """Create mock table metadata."""
        table = MagicMock()
        table.full_name = "public.users"
        table.primary_keys = ["id"]

        # Mock column
        col = MagicMock()
        col.name = "id"
        col.data_type = "integer"
        col.nullable = False
        col.default = "nextval('users_id_seq')"
        col.is_primary_key = True
        table.columns = [col]

        # Mock FKs
        table.foreign_keys_outgoing = []
        table.foreign_keys_incoming = []

        return table

    def test_displays_table_structure(self, mock_table: MagicMock) -> None:
        """Should display table structure."""
        mock_conn_manager = MagicMock()
        mock_conn = MagicMock()
        mock_conn_manager.get_connection.return_value = mock_conn

        with (
            patch("pgslice.operations.schema_ops.SchemaIntrospector") as mock_intro,
            patch("pgslice.operations.schema_ops.printy") as mock_printy,
        ):
            mock_introspector = MagicMock()
            mock_introspector.get_table_metadata.return_value = mock_table
            mock_intro.return_value = mock_introspector

            describe_table(mock_conn_manager, "public", "users")

            # Check table name was printed
            calls = [str(call) for call in mock_printy.call_args_list]
            assert any("public.users" in call for call in calls)
            assert any("Columns" in call for call in calls)

    def test_displays_foreign_keys(self, mock_table: MagicMock) -> None:
        """Should display foreign key relationships."""
        # Add outgoing FK
        fk_out = MagicMock()
        fk_out.source_column = "role_id"
        fk_out.target_table = "roles"
        fk_out.target_column = "id"
        mock_table.foreign_keys_outgoing = [fk_out]

        # Add incoming FK
        fk_in = MagicMock()
        fk_in.source_table = "orders"
        fk_in.source_column = "user_id"
        fk_in.target_column = "id"
        mock_table.foreign_keys_incoming = [fk_in]

        mock_conn_manager = MagicMock()
        mock_conn = MagicMock()
        mock_conn_manager.get_connection.return_value = mock_conn

        with (
            patch("pgslice.operations.schema_ops.SchemaIntrospector") as mock_intro,
            patch("pgslice.operations.schema_ops.printy") as mock_printy,
        ):
            mock_introspector = MagicMock()
            mock_introspector.get_table_metadata.return_value = mock_table
            mock_intro.return_value = mock_introspector

            describe_table(mock_conn_manager, "public", "users")

            calls = [str(call) for call in mock_printy.call_args_list]
            assert any("Foreign Keys (Outgoing)" in call for call in calls)
            assert any("Referenced By (Incoming)" in call for call in calls)
