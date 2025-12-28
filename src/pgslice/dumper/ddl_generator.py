"""DDL (Data Definition Language) generation for schema creation."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING

from ..graph.models import Column, Table
from ..utils.logging_config import get_logger

if TYPE_CHECKING:
    from ..db.schema import SchemaIntrospector

logger = get_logger(__name__)


class DDLGenerator:
    """Generates CREATE DATABASE, CREATE SCHEMA, and CREATE TABLE statements."""

    def __init__(self, schema_introspector: SchemaIntrospector) -> None:
        """
        Initialize DDL generator.

        Args:
            schema_introspector: Schema introspection utility for table metadata
        """
        self.introspector = schema_introspector

    def generate_ddl(
        self,
        database_name: str,
        schema_name: str,
        tables: set[tuple[str, str]],
    ) -> str:
        """
        Generate complete DDL for database, schema, and tables.

        Args:
            database_name: Name of the database to create
            schema_name: Name of the schema to create
            tables: Set of (schema, table) tuples to generate CREATE TABLE for

        Returns:
            Complete DDL script with CREATE statements

        Example:
            >>> generator = DDLGenerator(introspector)
            >>> ddl = generator.generate_ddl("mydb", "public", {("public", "users")})
            >>> print(ddl)
            -- CREATE DATABASE "mydb";
            \\c "mydb"
            CREATE SCHEMA IF NOT EXISTS "public";
            ...
        """
        if not tables:
            return ""

        logger.info(
            f"Generating DDL for database '{database_name}', "
            f"schema '{schema_name}', {len(tables)} table(s)"
        )

        statements = []

        # 1. CREATE DATABASE
        quoted_db = self._quote_identifier(database_name)
        statements.append(
            f"-- NOTE: PostgreSQL does not support 'CREATE DATABASE IF NOT EXISTS'.\n"
            f"-- If the database already exists, comment out the line below or it will fail.\n"
            f"-- For a new database: Uncomment the following line\n"
            f"-- CREATE DATABASE {quoted_db};"
        )
        statements.append("")  # Blank line

        # 2. CONNECT TO DATABASE
        # Add connection command (psql-specific)
        statements.append(
            f"-- Connect to the database before creating schemas/tables.\n"
            f"-- For psql: Use the \\c command below\n"
            f"-- For other clients: Disconnect and reconnect to the database manually\n"
            f"\\c {quoted_db}"
        )
        statements.append("")  # Blank line

        # 3. CREATE SCHEMA(S)
        # Collect unique schemas from tables
        unique_schemas = {schema for schema, _ in tables}
        for schema in sorted(unique_schemas):
            quoted_schema = self._quote_identifier(schema)
            statements.append(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema};")
        statements.append("")  # Blank line

        # 4. CREATE TABLES (sorted by dependencies)
        sorted_tables = self._sort_tables_by_dependencies(tables)

        table_statements = []
        foreign_key_statements = []

        for schema, table in sorted_tables:
            # Generate CREATE TABLE
            create_table_sql = self._generate_create_table(schema, table)
            table_statements.append(create_table_sql)

            # Generate ALTER TABLE statements for foreign keys
            fk_sql = self._generate_foreign_key_statements(schema, table)
            if fk_sql:
                foreign_key_statements.append(fk_sql)

        # Add all table creation statements
        statements.extend(table_statements)

        # Add blank line before foreign keys
        if foreign_key_statements:
            statements.append("")
            statements.append("-- Add foreign key constraints")
            statements.extend(foreign_key_statements)

        ddl = "\n".join(statements)
        logger.debug(f"Generated DDL: {len(statements)} statements")
        return ddl

    def _generate_create_table(self, schema: str, table: str) -> str:
        """
        Generate CREATE TABLE statement for a single table.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            CREATE TABLE IF NOT EXISTS statement with all columns and constraints

        Example:
            CREATE TABLE IF NOT EXISTS "public"."users" (
                "id" SERIAL PRIMARY KEY,
                "email" TEXT NOT NULL,
                "created_at" TIMESTAMP DEFAULT NOW()
            );
        """
        # Get table metadata
        table_metadata = self.introspector.get_table_metadata(schema, table)

        quoted_schema = self._quote_identifier(schema)
        quoted_table = self._quote_identifier(table)
        full_table_name = f"{quoted_schema}.{quoted_table}"

        # Build column definitions
        column_defs = []
        for col in table_metadata.columns:
            col_def = self._format_column_definition(col)
            column_defs.append(f"    {col_def}")

        # Add table-level constraints
        constraints = []

        # Primary key constraint (if not already in column definition)
        if table_metadata.primary_keys:
            # Check if PK is already defined inline (single PK column)
            has_inline_pk = len(table_metadata.primary_keys) == 1 and any(
                col.is_primary_key and not col.is_auto_generated
                for col in table_metadata.columns
                if col.name == table_metadata.primary_keys[0]
            )

            if not has_inline_pk:
                pk_constraint = self._format_primary_key_constraint(table_metadata)
                if pk_constraint:
                    constraints.append(f"    {pk_constraint}")

        # Unique constraints
        for constraint_name, columns in table_metadata.unique_constraints.items():
            unique_constraint = self._format_unique_constraint(constraint_name, columns)
            constraints.append(f"    {unique_constraint}")

        # Combine columns and constraints
        all_definitions = column_defs + constraints
        definitions_sql = ",\n".join(all_definitions)

        # Build final CREATE TABLE statement
        create_table = (
            f"CREATE TABLE IF NOT EXISTS {full_table_name} (\n{definitions_sql}\n);"
        )

        return create_table

    def _format_column_definition(self, col: Column) -> str:
        """
        Format a single column definition.

        Args:
            col: Column metadata

        Returns:
            Column definition string

        Example:
            "id" SERIAL PRIMARY KEY
            "email" TEXT NOT NULL
            "count" INTEGER DEFAULT 0
            "tags" TEXT[]
        """
        quoted_name = self._quote_identifier(col.name)

        # Map data type
        col_type = self._map_postgresql_type(col.data_type, col.udt_name)

        # Build definition parts
        parts = [quoted_name, col_type]

        # Add NOT NULL if applicable
        if not col.nullable:
            parts.append("NOT NULL")

        # Add DEFAULT if specified
        if col.default is not None:
            # Clean up default value (remove PostgreSQL type casts if present)
            default_value = col.default
            # Handle nextval() for SERIAL columns - skip it as SERIAL includes it
            if "nextval(" not in default_value.lower():
                parts.append(f"DEFAULT {default_value}")

        # Add PRIMARY KEY if single PK and not auto-generated
        # (AUTO-generated columns like SERIAL handle PK differently)
        if col.is_primary_key and not col.is_auto_generated:
            parts.append("PRIMARY KEY")

        return " ".join(parts)

    def _format_primary_key_constraint(self, table: Table) -> str:
        """
        Format PRIMARY KEY constraint.

        Args:
            table: Table metadata

        Returns:
            PRIMARY KEY constraint string or empty string

        Example:
            PRIMARY KEY ("id")
            PRIMARY KEY ("tenant_id", "user_id")
        """
        if not table.primary_keys:
            return ""

        # For SERIAL/auto-generated single PK, skip (already in column def)
        if len(table.primary_keys) == 1:
            pk_col_name = table.primary_keys[0]
            pk_col = next(
                (col for col in table.columns if col.name == pk_col_name), None
            )
            if pk_col and pk_col.is_auto_generated:
                return ""  # SERIAL already includes PRIMARY KEY

        # Format composite or explicit PK
        pk_columns = ", ".join(self._quote_identifier(pk) for pk in table.primary_keys)
        return f"PRIMARY KEY ({pk_columns})"

    def _format_unique_constraint(self, name: str, columns: list[str]) -> str:
        """
        Format UNIQUE constraint.

        Args:
            name: Constraint name
            columns: List of column names

        Returns:
            UNIQUE constraint string

        Example:
            CONSTRAINT "users_email_key" UNIQUE ("email")
        """
        quoted_name = self._quote_identifier(name)
        quoted_columns = ", ".join(self._quote_identifier(col) for col in columns)
        return f"CONSTRAINT {quoted_name} UNIQUE ({quoted_columns})"

    def _generate_foreign_key_statements(self, schema: str, table: str) -> str:
        """
        Generate ALTER TABLE statements for foreign keys.

        Foreign keys are added via ALTER TABLE to handle circular dependencies.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            ALTER TABLE statements for all foreign keys, or empty string

        Example:
            ALTER TABLE "public"."orders"
                ADD CONSTRAINT "orders_user_id_fkey"
                FOREIGN KEY ("user_id")
                REFERENCES "public"."users"("id");
        """
        # Get table metadata
        table_metadata = self.introspector.get_table_metadata(schema, table)

        if not table_metadata.foreign_keys_outgoing:
            return ""

        quoted_schema = self._quote_identifier(schema)
        quoted_table = self._quote_identifier(table)
        full_table_name = f"{quoted_schema}.{quoted_table}"

        fk_statements = []

        for fk in table_metadata.foreign_keys_outgoing:
            # Quote identifiers
            constraint_name = self._quote_identifier(fk.constraint_name)
            source_col = self._quote_identifier(fk.source_column)

            # Determine target schema (assume same schema if not specified)
            # Foreign key target tables might be in different schemas
            target_schema = schema  # Default to same schema
            target_table_quoted = self._quote_identifier(fk.target_table)
            target_col_quoted = self._quote_identifier(fk.target_column)

            # Build ALTER TABLE statement
            alter_stmt = (
                f"ALTER TABLE {full_table_name}\n"
                f"    ADD CONSTRAINT {constraint_name}\n"
                f"    FOREIGN KEY ({source_col})\n"
                f'    REFERENCES "{target_schema}".{target_table_quoted}({target_col_quoted})'
            )

            # Add ON DELETE clause if not default
            if fk.on_delete and fk.on_delete != "NO ACTION":
                alter_stmt += f"\n    ON DELETE {fk.on_delete}"

            alter_stmt += ";"
            fk_statements.append(alter_stmt)

        return "\n\n".join(fk_statements)

    def _map_postgresql_type(self, data_type: str, udt_name: str) -> str:
        """
        Map PostgreSQL information_schema data type to CREATE TABLE syntax.

        Args:
            data_type: Data type from information_schema.columns.data_type
            udt_name: UDT name from information_schema.columns.udt_name

        Returns:
            PostgreSQL type for CREATE TABLE statement

        Example:
            ("ARRAY", "_text") -> "TEXT[]"
            ("integer", "int4") -> "INTEGER"
            ("character varying", "varchar") -> "TEXT"
            ("USER-DEFINED", "my_enum") -> "my_enum"
        """
        data_type_upper = data_type.upper()

        # Handle arrays
        if data_type_upper == "ARRAY":
            element_type = self._get_array_element_type(udt_name)
            return f"{element_type}[]"

        # Handle user-defined types (ENUMs, domains, etc.)
        if data_type_upper == "USER-DEFINED":
            return udt_name

        # Map standard types
        type_mapping = {
            "INTEGER": "INTEGER",
            "BIGINT": "BIGINT",
            "SMALLINT": "SMALLINT",
            "TEXT": "TEXT",
            "CHARACTER VARYING": "TEXT",  # Prefer TEXT over VARCHAR
            "VARCHAR": "TEXT",
            "CHARACTER": "CHAR",
            "CHAR": "CHAR",
            "BOOLEAN": "BOOLEAN",
            "TIMESTAMP WITHOUT TIME ZONE": "TIMESTAMP",
            "TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ",
            "TIMESTAMP": "TIMESTAMP",
            "TIMESTAMPTZ": "TIMESTAMPTZ",
            "DATE": "DATE",
            "TIME WITHOUT TIME ZONE": "TIME",
            "TIME WITH TIME ZONE": "TIMETZ",
            "TIME": "TIME",
            "UUID": "UUID",
            "JSON": "JSON",
            "JSONB": "JSONB",
            "NUMERIC": "NUMERIC",
            "DECIMAL": "NUMERIC",
            "REAL": "REAL",
            "DOUBLE PRECISION": "DOUBLE PRECISION",
            "BYTEA": "BYTEA",
            "SERIAL": "SERIAL",
            "BIGSERIAL": "BIGSERIAL",
            "SMALLSERIAL": "SMALLSERIAL",
        }

        mapped_type = type_mapping.get(data_type_upper)
        if mapped_type:
            return mapped_type

        # Fallback: use data_type as-is
        logger.warning(
            f"Unknown data type '{data_type}' (udt: '{udt_name}'), using as-is"
        )
        return data_type.upper()

    def _get_array_element_type(self, udt_name: str) -> str:
        """
        Extract element type from array udt_name.

        Args:
            udt_name: PostgreSQL UDT name (e.g., "_text", "_int4")

        Returns:
            Element type name

        Example:
            "_text" -> "TEXT"
            "_int4" -> "INTEGER"
            "_varchar" -> "TEXT"
        """
        # Remove leading underscore from array type names
        element_udt = udt_name[1:] if udt_name.startswith("_") else udt_name

        # Map common UDT names to SQL types
        udt_mapping = {
            "text": "TEXT",
            "varchar": "TEXT",
            "char": "CHAR",
            "int4": "INTEGER",
            "int8": "BIGINT",
            "int2": "SMALLINT",
            "float4": "REAL",
            "float8": "DOUBLE PRECISION",
            "bool": "BOOLEAN",
            "timestamp": "TIMESTAMP",
            "timestamptz": "TIMESTAMPTZ",
            "date": "DATE",
            "time": "TIME",
            "timetz": "TIMETZ",
            "uuid": "UUID",
            "json": "JSON",
            "jsonb": "JSONB",
            "numeric": "NUMERIC",
            "bytea": "BYTEA",
        }

        return udt_mapping.get(element_udt, element_udt.upper())

    def _sort_tables_by_dependencies(
        self, tables: set[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        """
        Sort tables by FK dependencies using topological sort (Kahn's algorithm).

        Tables with no dependencies come first, followed by tables that depend on them.
        This ensures CREATE TABLE statements are in valid dependency order.

        Args:
            tables: Set of (schema, table) tuples

        Returns:
            List of (schema, table) tuples in dependency order

        Example:
            Input: {("public", "orders"), ("public", "users")}
            Output: [("public", "users"), ("public", "orders")]
            (users has no deps, orders depends on users)
        """
        if not tables:
            return []

        # Build dependency graph
        # in_degree: how many tables this table depends on
        in_degree: dict[tuple[str, str], int] = dict.fromkeys(tables, 0)
        # adjacency list: tables that depend on this table
        dependents: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)

        for schema, table in tables:
            table_metadata = self.introspector.get_table_metadata(schema, table)

            # Count dependencies (outgoing FKs to other tables in the set)
            for fk in table_metadata.foreign_keys_outgoing:
                # Assume target is in same schema if not specified
                target_table_tuple = (schema, fk.target_table)

                # Only count if target is in our table set
                if target_table_tuple in tables:
                    in_degree[(schema, table)] += 1
                    dependents[target_table_tuple].append((schema, table))

        # Kahn's algorithm: Process tables with no dependencies first
        queue: deque[tuple[str, str]] = deque()
        for table_tuple in tables:
            if in_degree[table_tuple] == 0:
                queue.append(table_tuple)

        sorted_tables = []

        while queue:
            current = queue.popleft()
            sorted_tables.append(current)

            # Reduce in-degree for dependents
            for dependent in dependents[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # If we couldn't sort all tables, there's a circular dependency
        # In this case, just append remaining tables (FK will be added via ALTER)
        if len(sorted_tables) < len(tables):
            remaining = tables - set(sorted_tables)
            sorted_tables.extend(sorted(remaining))  # Sort for consistency
            logger.warning(
                f"Circular dependencies detected among tables: {remaining}. "
                f"Foreign keys will be added via ALTER TABLE."
            )

        return sorted_tables

    def _quote_identifier(self, identifier: str) -> str:
        """
        Quote a SQL identifier safely.

        Always uses double quotes to handle reserved words and special characters.
        Escapes embedded double quotes.

        Args:
            identifier: SQL identifier (table, column, schema name)

        Returns:
            Quoted identifier

        Example:
            "users" -> '"users"'
            "my-table" -> '"my-table"'
            'table"name' -> '"table""name"'  (escaped quote)
        """
        # Escape embedded double quotes by doubling them
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'
