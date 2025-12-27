"""Tests for DDL generation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pgslice.dumper.ddl_generator import DDLGenerator
from pgslice.graph.models import Column, ForeignKey, Table


class TestDDLGenerator:
    """Tests for DDLGenerator class."""

    @pytest.fixture
    def mock_introspector(self) -> MagicMock:
        """Provide a mocked schema introspector."""
        return MagicMock()

    @pytest.fixture
    def generator(self, mock_introspector: MagicMock) -> DDLGenerator:
        """Provide a DDLGenerator instance."""
        return DDLGenerator(mock_introspector)


class TestGenerateDDL(TestDDLGenerator):
    """Tests for generate_ddl method."""

    def test_empty_tables_set(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should return empty string for empty table set."""
        result = generator.generate_ddl("testdb", "public", set())
        assert result == ""

    def test_generate_database_statement(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should generate CREATE DATABASE IF NOT EXISTS statement."""
        # Mock table metadata
        mock_introspector.get_table_metadata.return_value = Table(
            schema_name="public",
            table_name="users",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_auto_generated=True,
                    is_primary_key=True,
                )
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        result = generator.generate_ddl("mydb", "public", {("public", "users")})
        assert 'CREATE DATABASE IF NOT EXISTS "mydb";' in result

    def test_generate_schema_statement(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should generate CREATE SCHEMA IF NOT EXISTS statement."""
        mock_introspector.get_table_metadata.return_value = Table(
            schema_name="public",
            table_name="users",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_auto_generated=True,
                    is_primary_key=True,
                )
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        result = generator.generate_ddl("mydb", "public", {("public", "users")})
        assert 'CREATE SCHEMA IF NOT EXISTS "public";' in result

    def test_multiple_schemas(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should generate CREATE SCHEMA for all unique schemas."""

        def get_table_meta(schema: str, table: str) -> Table:
            return Table(
                schema_name=schema,
                table_name=table,
                columns=[
                    Column(
                        name="id",
                        data_type="integer",
                        udt_name="int4",
                        nullable=False,
                        is_auto_generated=True,
                        is_primary_key=True,
                    )
                ],
                primary_keys=["id"],
                foreign_keys_outgoing=[],
                foreign_keys_incoming=[],
            )

        mock_introspector.get_table_metadata.side_effect = get_table_meta

        result = generator.generate_ddl(
            "mydb", "public", {("public", "users"), ("custom", "orders")}
        )
        assert 'CREATE SCHEMA IF NOT EXISTS "public";' in result
        assert 'CREATE SCHEMA IF NOT EXISTS "custom";' in result


class TestGenerateCreateTable(TestDDLGenerator):
    """Tests for _generate_create_table method."""

    def test_basic_table(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should generate basic CREATE TABLE statement."""
        mock_introspector.get_table_metadata.return_value = Table(
            schema_name="public",
            table_name="users",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_auto_generated=True,
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
        )

        result = generator._generate_create_table("public", "users")
        assert 'CREATE TABLE IF NOT EXISTS "public"."users"' in result
        assert '"id" INTEGER' in result
        assert '"email" TEXT NOT NULL' in result

    def test_serial_column(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should handle SERIAL columns correctly."""
        mock_introspector.get_table_metadata.return_value = Table(
            schema_name="public",
            table_name="users",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_auto_generated=True,
                    is_primary_key=True,
                    default="nextval('users_id_seq'::regclass)",
                )
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        result = generator._generate_create_table("public", "users")
        # SERIAL columns should not include PRIMARY KEY inline or DEFAULT nextval
        assert '"id" INTEGER NOT NULL' in result

    def test_composite_primary_key(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should handle composite primary keys."""
        mock_introspector.get_table_metadata.return_value = Table(
            schema_name="public",
            table_name="user_roles",
            columns=[
                Column(
                    name="user_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                ),
                Column(
                    name="role_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_primary_key=True,
                ),
            ],
            primary_keys=["user_id", "role_id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        result = generator._generate_create_table("public", "user_roles")
        assert 'PRIMARY KEY ("user_id", "role_id")' in result

    def test_unique_constraints(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should include unique constraints."""
        mock_introspector.get_table_metadata.return_value = Table(
            schema_name="public",
            table_name="users",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_auto_generated=True,
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
            unique_constraints={"users_email_key": ["email"]},
        )

        result = generator._generate_create_table("public", "users")
        assert 'CONSTRAINT "users_email_key" UNIQUE ("email")' in result

    def test_default_values(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should include DEFAULT values."""
        mock_introspector.get_table_metadata.return_value = Table(
            schema_name="public",
            table_name="posts",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_auto_generated=True,
                    is_primary_key=True,
                ),
                Column(
                    name="status",
                    data_type="text",
                    udt_name="text",
                    nullable=False,
                    default="'draft'::text",
                ),
                Column(
                    name="created_at",
                    data_type="timestamp",
                    udt_name="timestamp",
                    nullable=False,
                    default="now()",
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        result = generator._generate_create_table("public", "posts")
        assert "DEFAULT 'draft'::text" in result
        assert "DEFAULT now()" in result


class TestColumnFormatting(TestDDLGenerator):
    """Tests for _format_column_definition method."""

    def test_array_types(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should format array types correctly."""
        col = Column(
            name="tags",
            data_type="ARRAY",
            udt_name="_text",
            nullable=True,
        )

        result = generator._format_column_definition(col)
        assert '"tags" TEXT[]' in result

    def test_integer_array(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should format integer array types."""
        col = Column(
            name="scores",
            data_type="ARRAY",
            udt_name="_int4",
            nullable=True,
        )

        result = generator._format_column_definition(col)
        assert '"scores" INTEGER[]' in result

    def test_json_types(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should handle JSON and JSONB types."""
        col_json = Column(
            name="metadata",
            data_type="json",
            udt_name="json",
            nullable=True,
        )
        col_jsonb = Column(
            name="data",
            data_type="jsonb",
            udt_name="jsonb",
            nullable=True,
        )

        result_json = generator._format_column_definition(col_json)
        result_jsonb = generator._format_column_definition(col_jsonb)

        assert '"metadata" JSON' in result_json
        assert '"data" JSONB' in result_jsonb

    def test_numeric_types(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should handle various numeric types."""
        cols = [
            Column(
                name="small_num", data_type="smallint", udt_name="int2", nullable=True
            ),
            Column(name="big_num", data_type="bigint", udt_name="int8", nullable=True),
            Column(
                name="decimal_num",
                data_type="numeric",
                udt_name="numeric",
                nullable=True,
            ),
            Column(name="real_num", data_type="real", udt_name="float4", nullable=True),
            Column(
                name="double_num",
                data_type="double precision",
                udt_name="float8",
                nullable=True,
            ),
        ]

        for col in cols:
            result = generator._format_column_definition(col)
            assert col.name in result


class TestForeignKeys(TestDDLGenerator):
    """Tests for foreign key generation."""

    def test_generate_foreign_keys(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should generate ALTER TABLE statements for foreign keys."""
        mock_introspector.get_table_metadata.return_value = Table(
            schema_name="public",
            table_name="orders",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_auto_generated=True,
                    is_primary_key=True,
                ),
                Column(
                    name="user_id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                ),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[
                ForeignKey(
                    constraint_name="orders_user_id_fkey",
                    source_table="orders",
                    source_column="user_id",
                    target_table="users",
                    target_column="id",
                    on_delete="CASCADE",
                )
            ],
            foreign_keys_incoming=[],
        )

        result = generator._generate_foreign_key_statements("public", "orders")
        assert 'ALTER TABLE "public"."orders"' in result
        assert 'ADD CONSTRAINT "orders_user_id_fkey"' in result
        assert 'FOREIGN KEY ("user_id")' in result
        assert 'REFERENCES "public"."users"("id")' in result
        assert "ON DELETE CASCADE" in result

    def test_no_foreign_keys(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should return empty string when no foreign keys."""
        mock_introspector.get_table_metadata.return_value = Table(
            schema_name="public",
            table_name="users",
            columns=[
                Column(
                    name="id",
                    data_type="integer",
                    udt_name="int4",
                    nullable=False,
                    is_auto_generated=True,
                    is_primary_key=True,
                )
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[],
            foreign_keys_incoming=[],
        )

        result = generator._generate_foreign_key_statements("public", "users")
        assert result == ""


class TestTableDependencySorting(TestDDLGenerator):
    """Tests for _sort_tables_by_dependencies method."""

    def test_sort_simple_dependency(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should sort tables by dependencies - users before orders."""

        def get_table_meta(schema: str, table: str) -> Table:
            if table == "users":
                return Table(
                    schema_name=schema,
                    table_name=table,
                    columns=[],
                    primary_keys=["id"],
                    foreign_keys_outgoing=[],
                    foreign_keys_incoming=[],
                )
            else:  # orders
                return Table(
                    schema_name=schema,
                    table_name=table,
                    columns=[],
                    primary_keys=["id"],
                    foreign_keys_outgoing=[
                        ForeignKey(
                            constraint_name="orders_user_id_fkey",
                            source_table="orders",
                            source_column="user_id",
                            target_table="users",
                            target_column="id",
                        )
                    ],
                    foreign_keys_incoming=[],
                )

        mock_introspector.get_table_metadata.side_effect = get_table_meta

        result = generator._sort_tables_by_dependencies(
            {("public", "orders"), ("public", "users")}
        )

        # Users should come before orders
        users_idx = result.index(("public", "users"))
        orders_idx = result.index(("public", "orders"))
        assert users_idx < orders_idx

    def test_circular_dependencies(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should handle circular dependencies gracefully."""

        def get_table_meta(schema: str, table: str) -> Table:
            if table == "authors":
                return Table(
                    schema_name=schema,
                    table_name=table,
                    columns=[],
                    primary_keys=["id"],
                    foreign_keys_outgoing=[
                        ForeignKey(
                            constraint_name="authors_favorite_book_id_fkey",
                            source_table="authors",
                            source_column="favorite_book_id",
                            target_table="books",
                            target_column="id",
                        )
                    ],
                    foreign_keys_incoming=[],
                )
            else:  # books
                return Table(
                    schema_name=schema,
                    table_name=table,
                    columns=[],
                    primary_keys=["id"],
                    foreign_keys_outgoing=[
                        ForeignKey(
                            constraint_name="books_author_id_fkey",
                            source_table="books",
                            source_column="author_id",
                            target_table="authors",
                            target_column="id",
                        )
                    ],
                    foreign_keys_incoming=[],
                )

        mock_introspector.get_table_metadata.side_effect = get_table_meta

        # Should not raise an error
        result = generator._sort_tables_by_dependencies(
            {("public", "authors"), ("public", "books")}
        )

        # Should return all tables (order may vary)
        assert len(result) == 2
        assert set(result) == {("public", "authors"), ("public", "books")}


class TestIdentifierQuoting(TestDDLGenerator):
    """Tests for _quote_identifier method."""

    def test_simple_identifier(self, generator: DDLGenerator) -> None:
        """Should quote simple identifiers."""
        assert generator._quote_identifier("users") == '"users"'

    def test_identifier_with_special_chars(self, generator: DDLGenerator) -> None:
        """Should handle identifiers with special characters."""
        assert generator._quote_identifier("my-table") == '"my-table"'
        assert generator._quote_identifier("table.name") == '"table.name"'

    def test_identifier_with_embedded_quotes(self, generator: DDLGenerator) -> None:
        """Should escape embedded double quotes."""
        assert generator._quote_identifier('table"name') == '"table""name"'

    def test_reserved_words(self, generator: DDLGenerator) -> None:
        """Should quote reserved words."""
        assert generator._quote_identifier("order") == '"order"'
        assert generator._quote_identifier("select") == '"select"'


class TestTypeMapping(TestDDLGenerator):
    """Tests for _map_postgresql_type method."""

    def test_user_defined_types(self, generator: DDLGenerator) -> None:
        """Should handle user-defined types (ENUMs)."""
        result = generator._map_postgresql_type("USER-DEFINED", "status_enum")
        assert result == "status_enum"

    def test_varchar_to_text(self, generator: DDLGenerator) -> None:
        """Should map VARCHAR to TEXT."""
        result = generator._map_postgresql_type("character varying", "varchar")
        assert result == "TEXT"

    def test_timestamp_types(self, generator: DDLGenerator) -> None:
        """Should handle various timestamp types."""
        assert (
            generator._map_postgresql_type("timestamp without time zone", "timestamp")
            == "TIMESTAMP"
        )
        assert (
            generator._map_postgresql_type("timestamp with time zone", "timestamptz")
            == "TIMESTAMPTZ"
        )

    def test_array_type_mapping(self, generator: DDLGenerator) -> None:
        """Should map array types to type[]."""
        result = generator._map_postgresql_type("ARRAY", "_text")
        assert result == "TEXT[]"

        result = generator._map_postgresql_type("ARRAY", "_int4")
        assert result == "INTEGER[]"


class TestIntegration(TestDDLGenerator):
    """Integration tests for complete DDL generation."""

    def test_full_ddl_generation(
        self, generator: DDLGenerator, mock_introspector: MagicMock
    ) -> None:
        """Should generate complete DDL with database, schema, and tables."""

        def get_table_meta(schema: str, table: str) -> Table:
            if table == "users":
                return Table(
                    schema_name=schema,
                    table_name=table,
                    columns=[
                        Column(
                            name="id",
                            data_type="integer",
                            udt_name="int4",
                            nullable=False,
                            is_auto_generated=True,
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
                )
            else:  # orders
                return Table(
                    schema_name=schema,
                    table_name=table,
                    columns=[
                        Column(
                            name="id",
                            data_type="integer",
                            udt_name="int4",
                            nullable=False,
                            is_auto_generated=True,
                            is_primary_key=True,
                        ),
                        Column(
                            name="user_id",
                            data_type="integer",
                            udt_name="int4",
                            nullable=False,
                        ),
                    ],
                    primary_keys=["id"],
                    foreign_keys_outgoing=[
                        ForeignKey(
                            constraint_name="orders_user_id_fkey",
                            source_table="orders",
                            source_column="user_id",
                            target_table="users",
                            target_column="id",
                        )
                    ],
                    foreign_keys_incoming=[],
                )

        mock_introspector.get_table_metadata.side_effect = get_table_meta

        result = generator.generate_ddl(
            "testdb", "public", {("public", "users"), ("public", "orders")}
        )

        # Should contain all parts
        assert 'CREATE DATABASE IF NOT EXISTS "testdb"' in result
        assert 'CREATE SCHEMA IF NOT EXISTS "public"' in result
        assert 'CREATE TABLE IF NOT EXISTS "public"."users"' in result
        assert 'CREATE TABLE IF NOT EXISTS "public"."orders"' in result
        assert 'ALTER TABLE "public"."orders"' in result
        assert "FOREIGN KEY" in result
