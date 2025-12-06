"""Integration tests for schema introspection (requires test database)."""

import pytest

from snippy.db.schema import SchemaIntrospector
from snippy.utils.exceptions import SchemaError


@pytest.mark.integration
class TestSchemaIntrospectorWithDatabase:
    """Integration tests for SchemaIntrospector with real database."""

    def test_get_table_metadata_users(self, test_db_connection):
        """Test getting metadata for users table."""
        introspector = SchemaIntrospector(test_db_connection)

        table = introspector.get_table_metadata("public", "users")

        assert table.schema_name == "public"
        assert table.table_name == "users"
        assert "id" in table.primary_keys
        assert len(table.columns) > 0

    def test_get_table_metadata_columns(self, test_db_connection):
        """Test table metadata includes correct columns."""
        introspector = SchemaIntrospector(test_db_connection)

        table = introspector.get_table_metadata("public", "users")

        column_names = [col.name for col in table.columns]
        assert "id" in column_names
        assert "username" in column_names
        assert "email" in column_names
        assert "role_id" in column_names
        assert "manager_id" in column_names

    def test_get_table_metadata_primary_keys(self, test_db_connection):
        """Test primary key detection."""
        introspector = SchemaIntrospector(test_db_connection)

        table = introspector.get_table_metadata("public", "users")

        assert table.primary_keys == ["id"]
        # Check column is marked as PK
        id_col = next(col for col in table.columns if col.name == "id")
        assert id_col.is_primary_key is True

    def test_get_table_metadata_foreign_keys_outgoing(self, test_db_connection):
        """Test outgoing foreign key detection."""
        introspector = SchemaIntrospector(test_db_connection)

        table = introspector.get_table_metadata("public", "users")

        # Users table has FK to roles (role_id)
        fk_targets = [
            (fk.source_column, fk.target_table)
            for fk in table.foreign_keys_outgoing
        ]
        assert ("role_id", "roles") in fk_targets

    def test_get_table_metadata_foreign_keys_incoming(self, test_db_connection):
        """Test incoming foreign key detection."""
        introspector = SchemaIntrospector(test_db_connection)

        table = introspector.get_table_metadata("public", "users")

        # Other tables reference users (e.g., bank_accounts.user_id -> users.id)
        fk_sources = [
            (fk.source_table, fk.source_column)
            for fk in table.foreign_keys_incoming
        ]
        # Should include bank_accounts referencing users
        assert any(fk[0] == "bank_accounts" for fk in fk_sources)

    def test_get_table_metadata_self_referencing_fk(self, test_db_connection):
        """Test self-referencing foreign key (users.manager_id -> users.id)."""
        introspector = SchemaIntrospector(test_db_connection)

        table = introspector.get_table_metadata("public", "users")

        # Check outgoing self-reference
        self_refs_out = [
            fk for fk in table.foreign_keys_outgoing
            if fk.target_table == "users"
        ]
        assert len(self_refs_out) > 0
        assert any(fk.source_column == "manager_id" for fk in self_refs_out)

        # Check incoming self-reference
        self_refs_in = [
            fk for fk in table.foreign_keys_incoming
            if fk.source_table == "users"
        ]
        assert len(self_refs_in) > 0

    def test_get_table_metadata_composite_pk(self, test_db_connection):
        """Test composite primary key detection (user_groups table)."""
        introspector = SchemaIntrospector(test_db_connection)

        table = introspector.get_table_metadata("public", "user_groups")

        assert len(table.primary_keys) == 2
        assert "user_id" in table.primary_keys
        assert "group_id" in table.primary_keys

    def test_get_table_metadata_no_primary_key(self, test_db_connection):
        """Test table without primary key (if such table exists)."""
        introspector = SchemaIntrospector(test_db_connection)

        # Most tables should have PKs, but test handles case gracefully
        table = introspector.get_table_metadata("public", "roles")

        # Even if no PK, should return valid metadata
        assert table.schema_name == "public"
        assert table.table_name == "roles"

    def test_table_not_found_error(self, test_db_connection):
        """Test error when table doesn't exist."""
        introspector = SchemaIntrospector(test_db_connection)

        with pytest.raises(SchemaError) as exc_info:
            introspector.get_table_metadata("public", "nonexistent_table")

        assert "nonexistent_table" in str(exc_info.value)

    def test_invalid_schema_error(self, test_db_connection):
        """Test error when schema doesn't exist."""
        introspector = SchemaIntrospector(test_db_connection)

        with pytest.raises(SchemaError):
            introspector.get_table_metadata("invalid_schema", "users")

    def test_get_all_tables(self, test_db_connection):
        """Test getting all tables in schema."""
        introspector = SchemaIntrospector(test_db_connection)

        tables = introspector.get_all_tables("public")

        assert len(tables) > 0
        assert "users" in tables
        assert "roles" in tables
        assert "bank_accounts" in tables

    def test_get_all_tables_returns_sorted(self, test_db_connection):
        """Test get_all_tables returns sorted list."""
        introspector = SchemaIntrospector(test_db_connection)

        tables = introspector.get_all_tables("public")

        assert tables == sorted(tables)

    def test_column_nullable_detection(self, test_db_connection):
        """Test nullable column detection."""
        introspector = SchemaIntrospector(test_db_connection)

        table = introspector.get_table_metadata("public", "users")

        # id should not be nullable
        id_col = next(col for col in table.columns if col.name == "id")
        assert id_col.nullable is False

        # manager_id should be nullable
        manager_col = next(col for col in table.columns if col.name == "manager_id")
        assert manager_col.nullable is True

    def test_column_data_types(self, test_db_connection):
        """Test data type detection."""
        introspector = SchemaIntrospector(test_db_connection)

        table = introspector.get_table_metadata("public", "users")

        # Check some data types
        id_col = next(col for col in table.columns if col.name == "id")
        assert "int" in id_col.data_type.lower()

        username_col = next(col for col in table.columns if col.name == "username")
        assert "char" in username_col.data_type.lower() or "text" in username_col.data_type.lower()

    def test_many_to_many_table(self, test_db_connection):
        """Test many-to-many junction table (user_groups)."""
        introspector = SchemaIntrospector(test_db_connection)

        table = introspector.get_table_metadata("public", "user_groups")

        # Should have FKs to both users and groups
        fk_targets = [fk.target_table for fk in table.foreign_keys_outgoing]
        assert "users" in fk_targets
        assert "groups" in fk_targets

    def test_caching_same_table_twice(self, test_db_connection):
        """Test getting same table metadata twice (internal caching if any)."""
        introspector = SchemaIntrospector(test_db_connection)

        table1 = introspector.get_table_metadata("public", "users")
        table2 = introspector.get_table_metadata("public", "users")

        # Should return consistent results
        assert table1.table_name == table2.table_name
        assert table1.primary_keys == table2.primary_keys
        assert len(table1.columns) == len(table2.columns)
