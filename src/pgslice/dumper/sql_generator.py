"""SQL INSERT statement generation with proper escaping."""

from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from ..db.schema import SchemaIntrospector
from ..graph.models import RecordData, RecordIdentifier, Table
from ..utils.exceptions import SchemaError
from ..utils.logging_config import get_logger
from .ddl_generator import DDLGenerator

logger = get_logger(__name__)


class SQLGenerator:
    """Generates INSERT statements from record data."""

    def __init__(
        self,
        schema_introspector: SchemaIntrospector,
        batch_size: int = 100,
        natural_keys: dict[str, list[str]] | None = None,
    ) -> None:
        """
        Initialize SQL generator.

        Args:
            schema_introspector: Schema introspection utility for table metadata
            batch_size: Number of rows per INSERT statement (0 or -1 = unlimited)
            natural_keys: Manual natural key overrides (format: {"schema.table": ["col1", "col2"]})
        """
        self.introspector = schema_introspector
        # 0 or -1 means unlimited batch size
        self.batch_size = batch_size if batch_size > 0 else 999999
        # Manual natural key overrides from config/CLI
        self.natural_keys = natural_keys or {}
        # Cache column type mappings per table to avoid repeated lookups
        self._column_type_cache: dict[tuple[str, str], dict[str, tuple[str, str]]] = {}
        # Cache natural key detection results per table
        self._natural_key_cache: dict[tuple[str, str], list[str]] = {}

    def generate_bulk_insert(self, records: list[RecordData]) -> str:
        """
        Generate a single bulk INSERT statement for multiple records.

        Args:
            records: List of records from the SAME table

        Returns:
            SQL INSERT statement with multiple VALUES rows
        """
        if not records:
            return ""

        # All records are from same table, use first for metadata
        first_record = records[0]
        schema = first_record.identifier.schema_name
        table = first_record.identifier.table_name

        # Get table metadata for primary keys
        table_metadata = self.introspector.get_table_metadata(schema, table)

        # Build column list (same for all rows)
        columns = sorted(first_record.data.keys())
        columns_sql = ", ".join(f'"{col}"' for col in columns)

        # Get column type mapping for array/JSON distinction
        column_type_map = self._get_column_types(schema, table)

        # Build VALUES rows
        values_rows = []
        for record in records:
            values = [
                self._format_value(record.data.get(col), column_type_map.get(col))
                for col in columns
            ]
            values_sql = ", ".join(values)
            values_rows.append(f"    ({values_sql})")

        values_clause = ",\n".join(values_rows)

        # Build ON CONFLICT clause
        if table_metadata.primary_keys:
            pk_columns = ", ".join(f'"{pk}"' for pk in table_metadata.primary_keys)
            conflict_clause = f"\nON CONFLICT ({pk_columns}) DO NOTHING"
        else:
            conflict_clause = ""

        # Add comment header with table info
        full_table_name = f'"{schema}"."{table}"'
        comment = f"-- Table: {full_table_name} ({len(records)} record{'s' if len(records) != 1 else ''})"

        # Combine into final statement
        sql = (
            f"{comment}\n"
            f"INSERT INTO {full_table_name} ({columns_sql})\n"
            f"VALUES\n{values_clause}"
            f"{conflict_clause};"
        )

        return sql

    def generate_batch(
        self,
        records: list[RecordData],
        include_transaction: bool = True,
        keep_pks: bool = False,
        create_schema: bool = False,
        database_name: str | None = None,
        schema_name: str = "public",
    ) -> str:
        """
        Generate SQL for multiple records with proper ordering and bulk INSERTs.

        Args:
            records: List of RecordData in dependency order
            include_transaction: Whether to wrap in BEGIN/COMMIT
            keep_pks: If True, keep original PK values (current behavior).
                     If False, exclude auto-generated PKs and use PL/pgSQL remapping.
            create_schema: If True, include DDL statements (CREATE DATABASE/SCHEMA/TABLE)
            database_name: Database name for CREATE DATABASE statement (required if create_schema=True)
            schema_name: Schema name for CREATE SCHEMA statement

        Returns:
            Complete SQL script
        """
        if keep_pks:
            return self._generate_batch_with_pks(
                records, include_transaction, create_schema, database_name, schema_name
            )
        else:
            return self._generate_batch_with_plpgsql_remapping(
                records, include_transaction, create_schema, database_name, schema_name
            )

    def _generate_batch_with_pks(
        self,
        records: list[RecordData],
        include_transaction: bool,
        create_schema: bool = False,
        database_name: str | None = None,
        schema_name: str = "public",
    ) -> str:
        """
        Generate SQL with original PK values (current behavior).

        Args:
            records: List of RecordData in dependency order
            include_transaction: Whether to wrap in BEGIN/COMMIT
            create_schema: If True, include DDL statements
            database_name: Database name for CREATE DATABASE (required if create_schema=True)
            schema_name: Schema name for CREATE SCHEMA

        Returns:
            Complete SQL script with all bulk INSERT statements
        """
        from collections import defaultdict

        logger.info(
            f"Generating SQL for {len(records)} records (batch_size={self.batch_size})"
        )

        sql_statements = []

        # Add DDL if requested
        if create_schema and database_name:
            ddl_generator = DDLGenerator(self.introspector)

            # Collect unique tables from records
            unique_tables = {
                (record.identifier.schema_name, record.identifier.table_name)
                for record in records
            }

            ddl = ddl_generator.generate_ddl(database_name, schema_name, unique_tables)
            sql_statements.append(ddl)
            sql_statements.append("")  # Blank line separator

        # Add header
        header = [
            "-- Generated by pgslice",
            f"-- Date: {datetime.now().isoformat()}",
            f"-- Records: {len(records)}",
            f"-- Batch size: {self.batch_size}",
            "",
        ]

        sql_statements.extend(header)

        # Add BEGIN if transaction requested
        if include_transaction:
            sql_statements.append("BEGIN;")
            sql_statements.append("")

        # BEFORE grouping by table, deduplicate based on RecordIdentifier
        seen_identifiers: set[RecordIdentifier] = set()
        unique_records: list[RecordData] = []
        duplicate_count = 0

        for record in records:
            if record.identifier not in seen_identifiers:
                seen_identifiers.add(record.identifier)
                unique_records.append(record)
            else:
                duplicate_count += 1
                logger.warning(
                    f"Duplicate #{duplicate_count} detected and skipped: {record.identifier}"
                )

        if duplicate_count > 0:
            logger.info(f"Deduplicated {duplicate_count} duplicate record(s)")

        # Group unique records by table (preserving dependency order within each table)
        records_by_table: dict[tuple[str, str], list[RecordData]] = defaultdict(list)
        for record in unique_records:
            key = (record.identifier.schema_name, record.identifier.table_name)
            records_by_table[key].append(record)

        # Generate bulk INSERTs for each table with batching
        for (_schema, _table), table_records in records_by_table.items():
            # Split into batches
            for i in range(0, len(table_records), self.batch_size):
                batch = table_records[i : i + self.batch_size]
                bulk_insert = self.generate_bulk_insert(batch)
                sql_statements.append(bulk_insert)
                sql_statements.append("")  # Blank line between batches

        # Add COMMIT if transaction requested
        if include_transaction:
            sql_statements.append("COMMIT;")

        result = "\n".join(sql_statements)
        logger.info(f"Generated SQL script ({len(result)} bytes)")
        return result

    def _get_column_types(self, schema: str, table: str) -> dict[str, tuple[str, str]]:
        """
        Get column type mapping with caching.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            Dictionary mapping column names to (data_type, udt_name) tuples
        """
        key = (schema, table)
        if key not in self._column_type_cache:
            table_metadata = self.introspector.get_table_metadata(schema, table)
            self._column_type_cache[key] = {
                c.name: (c.data_type, c.udt_name) for c in table_metadata.columns
            }
        return self._column_type_cache[key]

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
            "references" -> '"references"'
            'col"name' -> '"col""name"'  (escaped quote)
        """
        # Escape embedded double quotes by doubling them
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    def _is_array_type(self, data_type: str) -> bool:
        """
        Check if a PostgreSQL data type is an array type.

        PostgreSQL returns "ARRAY" in information_schema.columns.data_type
        for all array types (text[], integer[], etc.)

        Args:
            data_type: PostgreSQL data_type from information_schema

        Returns:
            True if the type is an array type
        """
        return data_type.upper() == "ARRAY"

    def _get_array_element_type(self, udt_name: str) -> str:
        """
        Extract the element type from PostgreSQL's udt_name.

        PostgreSQL array types have udt_name with underscore prefix:
        - "_text" → element type is "text"
        - "_int4" → element type is "integer"
        - "_varchar" → element type is "varchar"

        Args:
            udt_name: PostgreSQL udt_name from information_schema

        Returns:
            Element type name suitable for ARRAY[...]::type[] syntax

        Examples:
            "_text" → "text"
            "_int4" → "integer"
            "_varchar" → "varchar"
        """
        if udt_name.startswith("_"):
            element_udt = udt_name[1:]  # Remove underscore prefix

            # Map PostgreSQL internal names to SQL type names
            type_mapping = {
                "int4": "integer",
                "int2": "smallint",
                "int8": "bigint",
                "float4": "real",
                "float8": "double precision",
                "bool": "boolean",
                # Most others (text, varchar, uuid, etc.) use the same name
            }

            return type_mapping.get(element_udt, element_udt)

        return udt_name

    def _format_array_value(self, value: list[Any], element_type: str) -> str:
        """
        Format a Python list as a PostgreSQL array literal.

        Uses ARRAY[...] syntax with explicit type casting for clarity and safety.

        Args:
            value: Python list to format
            element_type: PostgreSQL type of array elements

        Returns:
            PostgreSQL array literal string

        Examples:
            ['foo', 'bar'], 'text' -> ARRAY['foo', 'bar']::text[]
            [1, 2, 3], 'integer' -> ARRAY[1, 2, 3]::integer[]
            [], 'text' -> ARRAY[]::text[]
        """
        # Check for nested arrays (multidimensional)
        if value and isinstance(value[0], list):
            logger.warning(
                f"Multidimensional arrays not yet supported, using JSON: {value}"
            )
            # Fall back to JSON formatting
            json_str = json.dumps(value)
            escaped = json_str.replace("'", "''")
            return f"'{escaped}'"

        if not value:
            # Empty array
            return f"ARRAY[]::{element_type}[]"

        # Determine if element type needs quoting
        text_types = {
            "text",
            "character varying",
            "varchar",
            "char",
            "character",
            "uuid",
        }
        numeric_types = {
            "integer",
            "bigint",
            "smallint",
            "int",
            "numeric",
            "decimal",
            "real",
            "double precision",
            "float",
        }
        boolean_types = {"boolean", "bool"}

        formatted_elements = []
        element_type_lower = element_type.lower()

        for item in value:
            if item is None:
                formatted_elements.append("NULL")
            elif element_type_lower in text_types or element_type in text_types:
                # Text types: escape quotes and backslashes
                escaped = str(item).replace("'", "''").replace("\\", "\\\\")
                formatted_elements.append(f"'{escaped}'")
            elif element_type_lower in numeric_types:
                # Numeric types: no quotes
                formatted_elements.append(str(item))
            elif element_type_lower in boolean_types:
                # Boolean types
                formatted_elements.append("TRUE" if item else "FALSE")
            else:
                # Fallback: treat as string
                escaped = str(item).replace("'", "''").replace("\\", "\\\\")
                formatted_elements.append(f"'{escaped}'")

        elements_str = ", ".join(formatted_elements)
        return f"ARRAY[{elements_str}]::{element_type}[]"

    def _format_value(
        self, value: Any, column_type_info: tuple[str, str] | None = None
    ) -> str:
        """
        Format a Python value as SQL literal.

        Args:
            value: Python value to format
            column_type_info: Optional (data_type, udt_name) tuple from information_schema
                            Used to distinguish between JSON and array types

        Returns:
            SQL literal string

        Handles:
        - NULL values
        - Booleans (TRUE/FALSE)
        - Numbers (int, float)
        - Strings (with proper escaping)
        - Dates, times, timestamps
        - UUIDs
        - PostgreSQL arrays (list with array column type)
        - JSON/JSONB (dict, list with json/jsonb column type, or no type info)
        - Bytea (bytes)
        """
        if value is None:
            return "NULL"

        elif isinstance(value, bool):
            # Must come before int check (bool is subclass of int)
            return "TRUE" if value else "FALSE"

        elif isinstance(value, int):
            return str(value)

        elif isinstance(value, Decimal):
            # Handle Decimal (before float, since we want numeric output)
            if value.is_nan():
                return "'NaN'"
            if value.is_infinite():
                return "'Infinity'" if value > 0 else "'-Infinity'"
            # Return as numeric literal (no quotes)
            return str(value)

        elif isinstance(value, float):
            # Handle special float values
            if value != value:  # NaN
                return "'NaN'"
            elif value == float("inf"):
                return "'Infinity'"
            elif value == float("-inf"):
                return "'-Infinity'"
            return str(value)

        elif isinstance(value, str):
            # Escape single quotes by doubling them
            escaped = value.replace("'", "''")
            # Also escape backslashes for PostgreSQL
            escaped = escaped.replace("\\", "\\\\")
            return f"'{escaped}'"

        elif isinstance(value, datetime):
            # ISO format with timezone
            return f"'{value.isoformat()}'"

        elif isinstance(value, (date, time)):
            return f"'{value.isoformat()}'"

        elif isinstance(value, UUID):
            return f"'{str(value)}'"

        elif isinstance(value, (dict, list)):
            # CRITICAL: Distinguish between PostgreSQL arrays and JSON
            if column_type_info and isinstance(value, list):
                data_type, udt_name = column_type_info
                if self._is_array_type(data_type):
                    element_type = self._get_array_element_type(udt_name)
                    return self._format_array_value(value, element_type)

            # Fall through to JSON handling for:
            # - dict values (always JSON)
            # - list values with json/jsonb column type
            # - list values with no type info (backward compatibility)
            json_str = json.dumps(value)
            escaped = json_str.replace("'", "''")
            return f"'{escaped}'"

        elif isinstance(value, bytes):
            # Bytea - use hex format
            hex_str = value.hex()
            return f"'\\x{hex_str}'"

        elif isinstance(value, memoryview):
            # Convert memoryview to bytes
            return self._format_value(bytes(value), column_type_info)

        else:
            # Fallback: convert to string and escape
            logger.warning(
                f"Unknown type {type(value)} for value {value}, converting to string"
            )
            return self._format_value(str(value))

    # ============================================================================
    # PL/pgSQL Generation with ID Remapping
    # ============================================================================

    def _generate_batch_with_plpgsql_remapping(
        self,
        records: list[RecordData],
        include_transaction: bool,
        create_schema: bool = False,
        database_name: str | None = None,
        schema_name: str = "public",
    ) -> str:
        """
        Generate PL/pgSQL script with ID remapping for auto-generated PKs.

        Algorithm:
        1. Deduplicate records
        2. Group by table
        3. Identify tables with auto-generated PKs
        4. Build temp table for ID mappings
        5. Generate PL/pgSQL DO block with:
           - INSERT ... RETURNING for tables with auto-gen PKs
           - Store old_id -> new_id in temp table
           - Replace FK values with subqueries to lookup mapped IDs
        6. Drop temp table

        Args:
            records: List of RecordData in dependency order
            include_transaction: Whether to wrap in BEGIN/COMMIT (always True for PL/pgSQL)
            create_schema: If True, include DDL statements
            database_name: Database name for CREATE DATABASE (required if create_schema=True)
            schema_name: Schema name for CREATE SCHEMA

        Returns:
            PL/pgSQL script as string
        """
        from collections import defaultdict

        logger.info(f"Generating PL/pgSQL with ID remapping for {len(records)} records")

        sql_statements = []

        # Add DDL if requested
        if create_schema and database_name:
            ddl_generator = DDLGenerator(self.introspector)

            # Collect unique tables from records
            unique_tables = {
                (record.identifier.schema_name, record.identifier.table_name)
                for record in records
            }

            ddl = ddl_generator.generate_ddl(database_name, schema_name, unique_tables)
            sql_statements.append(ddl)
            sql_statements.append("")  # Blank line separator

        # 1. Deduplicate records (same as duplicate bug fix)
        seen_identifiers: set[RecordIdentifier] = set()
        unique_records: list[RecordData] = []
        duplicate_count = 0

        for record in records:
            if record.identifier not in seen_identifiers:
                seen_identifiers.add(record.identifier)
                unique_records.append(record)
            else:
                duplicate_count += 1
                logger.warning(
                    f"Duplicate #{duplicate_count} detected and skipped: {record.identifier}"
                )

        if duplicate_count > 0:
            logger.info(f"Deduplicated {duplicate_count} duplicate record(s)")

        # 2. Group by table (preserving dependency order)
        records_by_table: dict[tuple[str, str], list[RecordData]] = defaultdict(list)
        for record in unique_records:
            key = (record.identifier.schema_name, record.identifier.table_name)
            records_by_table[key].append(record)

        # 3. Identify tables with auto-generated PKs
        tables_with_remapped_ids: set[tuple[str, str]] = set()
        for schema, table in records_by_table:
            if self._has_auto_generated_pks(schema, table):
                tables_with_remapped_ids.add((schema, table))

        # 4. Build SQL script
        sql_parts = []

        # Header
        sql_parts.extend(
            [
                "-- Generated by pgslice",
                f"-- Date: {datetime.now().isoformat()}",
                f"-- Records: {len(unique_records)}",
                "-- Mode: PL/pgSQL with ID remapping",
                "",
            ]
        )

        # Create temp table for ID mappings
        sql_parts.extend(
            [
                "-- Create temporary table for ID mapping",
                "CREATE TEMP TABLE IF NOT EXISTS _pgslice_id_map (",
                "    table_name TEXT NOT NULL,",
                "    old_id TEXT NOT NULL,",
                "    new_id TEXT NOT NULL,",
                "    PRIMARY KEY (table_name, old_id)",
                ");",
                "",
            ]
        )

        # Start PL/pgSQL block
        sql_parts.extend(
            [
                "-- Main PL/pgSQL block with ID remapping",
                "DO $$",
                "DECLARE",
            ]
        )

        # Declare variables for each table with remapping
        for schema, table in tables_with_remapped_ids:
            auto_gen_pks = self._get_auto_generated_pk_columns(schema, table)
            if auto_gen_pks:
                # Get the data type of the first PK column for variable declaration
                table_meta = self.introspector.get_table_metadata(schema, table)
                pk_col = auto_gen_pks[0]
                col_info = next(
                    (c for c in table_meta.columns if c.name == pk_col), None
                )
                if col_info:
                    pg_type = col_info.data_type
                    sql_parts.append(f"    v_new_id_{table} {pg_type};")
                    sql_parts.append(f"    v_new_ids_{table} {pg_type}[];")
                    sql_parts.append(f"    v_old_ids_{table} TEXT[];")

        sql_parts.extend(
            [
                "    i INTEGER;",
                "BEGIN",
                "",
            ]
        )

        # Add sequence synchronization to prevent conflicts
        if tables_with_remapped_ids:
            sql_parts.append("    -- Synchronize sequences to prevent ID conflicts")
            for schema, table in tables_with_remapped_ids:
                auto_gen_pks = self._get_auto_generated_pk_columns(schema, table)
                for pk_col in auto_gen_pks:
                    try:
                        seq_name = self._get_sequence_name(schema, table, pk_col)
                        full_table_name = f'"{schema}"."{table}"'
                        sql_parts.append(
                            f"    PERFORM setval('{seq_name}', "
                            f'COALESCE((SELECT MAX("{pk_col}") FROM {full_table_name}), 1));'
                        )
                    except SchemaError:
                        # Column might not have a sequence (e.g., UUID PKs)
                        logger.debug(
                            f"Skipping sequence sync for {schema}.{table}.{pk_col} (no sequence)"
                        )
            sql_parts.append("")  # Blank line after sequence sync

        # 5. Generate INSERT statements for each table
        for (schema, table), table_records in records_by_table.items():
            full_table_name = f'"{schema}"."{table}"'
            has_remapped_ids = (schema, table) in tables_with_remapped_ids

            # Add comment
            sql_parts.append(
                f"    -- Table: {full_table_name} ({len(table_records)} records)"
            )

            # Split into batches
            for i in range(0, len(table_records), self.batch_size):
                batch = table_records[i : i + self.batch_size]

                if has_remapped_ids:
                    # Check if this table ALSO has FKs to remapped tables
                    fk_to_remap = self._get_fk_columns_to_remap(
                        schema, table, tables_with_remapped_ids
                    )

                    if fk_to_remap:
                        # Has auto-gen PKs AND FKs to remap → use FK remapping method
                        # It will handle both FK remapping AND PK RETURNING
                        insert_sql = self._generate_insert_with_fk_remapping(
                            schema, table, batch, tables_with_remapped_ids
                        )
                    else:
                        # Only auto-gen PKs, no FK remapping needed
                        insert_sql = self._generate_insert_with_remapping(
                            schema, table, batch
                        )
                else:
                    # No auto-gen PKs, may have FK remapping
                    insert_sql = self._generate_insert_with_fk_remapping(
                        schema, table, batch, tables_with_remapped_ids
                    )

                sql_parts.append(insert_sql)
                sql_parts.append("")

        # End PL/pgSQL block
        sql_parts.extend(
            [
                "END $$;",
                "",
            ]
        )

        # Drop temp table
        sql_parts.extend(
            [
                "-- Cleanup",
                "DROP TABLE IF EXISTS _pgslice_id_map;",
                "",
            ]
        )

        # Combine DDL (if any) with PL/pgSQL script
        if sql_statements:
            # sql_statements contains DDL, add PL/pgSQL parts after
            sql_statements.extend(sql_parts)
            result = "\n".join(sql_statements)
        else:
            result = "\n".join(sql_parts)

        logger.info(f"Generated PL/pgSQL script ({len(result)} bytes)")
        return result

    def _get_auto_generated_pk_columns(self, schema: str, table: str) -> list[str]:
        """
        Get list of auto-generated PK columns for a table.

        Returns:
            List of column names that are both PK and auto-generated
        """
        table_meta = self.introspector.get_table_metadata(schema, table)
        auto_gen_pks = []
        for col in table_meta.columns:
            if col.is_primary_key and col.is_auto_generated:
                auto_gen_pks.append(col.name)
        return auto_gen_pks

    def _has_auto_generated_pks(self, schema: str, table: str) -> bool:
        """Check if table has any auto-generated PK columns."""
        return len(self._get_auto_generated_pk_columns(schema, table)) > 0

    def _get_sequence_name(self, schema: str, table: str, column: str) -> str:
        """
        Get the sequence name for an auto-generated column.

        Uses pg_get_serial_sequence() to find the sequence associated with a column.
        This works for SERIAL, BIGSERIAL, and columns with explicit DEFAULT nextval().

        Args:
            schema: Schema name
            table: Table name
            column: Column name

        Returns:
            Fully qualified sequence name (e.g., 'public.users_id_seq')

        Raises:
            SchemaError: If column has no associated sequence
        """
        query = "SELECT pg_get_serial_sequence(%s, %s)"
        full_table = f"{schema}.{table}"

        with self.introspector.conn.cursor() as cur:
            cur.execute(query, (full_table, column))
            result = cur.fetchone()

            if result and result[0]:
                return str(result[0])

            raise SchemaError(
                f"Column {schema}.{table}.{column} has no associated sequence"
            )

    def _parse_table_name(self, qualified_name: str) -> tuple[str, str]:
        """
        Parse a fully qualified table name into (schema, table).

        Args:
            qualified_name: Format "schema.table" or just "table"

        Returns:
            (schema, table) tuple

        Examples:
            "public.film" → ("public", "film")
            "film" → ("public", "film")  # Default to public
        """
        if "." in qualified_name:
            parts = qualified_name.split(".", 1)
            return (parts[0], parts[1])
        return ("public", qualified_name)  # Default schema

    def _get_fk_columns_to_remap(
        self, schema: str, table: str, tables_with_remapped_ids: set[tuple[str, str]]
    ) -> dict[str, tuple[str, str]]:
        """
        Get FK columns that reference tables with remapped IDs.

        Args:
            schema: Current table schema
            table: Current table name
            tables_with_remapped_ids: Set of (schema, table) tuples that have ID remapping

        Returns:
            Dict mapping FK column name -> (target_schema, target_table)
        """
        table_meta = self.introspector.get_table_metadata(schema, table)
        fk_to_remap = {}

        for fk in table_meta.foreign_keys_outgoing:
            # Parse the fully qualified target table name
            # fk.target_table is "schema.table" format from schema introspection
            target_schema, target_table = self._parse_table_name(fk.target_table)

            target_key = (target_schema, target_table)
            if target_key in tables_with_remapped_ids:
                fk_to_remap[fk.source_column] = target_key

        return fk_to_remap

    def _serialize_pk_value(self, pk_values: tuple[Any, ...]) -> str:
        """
        Serialize PK value(s) to string for storage in temp table.

        Handles:
        - Single values: convert to string
        - Composite PKs: JSON array
        - UUIDs: string representation

        Examples:
            (123,) -> "123"
            (1, 2) -> "[1, 2]"
            (UUID("..."),) -> "uuid-string"
        """
        if len(pk_values) == 1:
            val = pk_values[0]
            if isinstance(val, UUID):
                return str(val)
            return str(val)
        else:
            # Composite PK: use JSON array
            return json.dumps([str(v) for v in pk_values])

    def _build_fk_remapping_value(
        self,
        old_fk_value: Any,
        target_table_full: str,
        fk_data_type: str,
    ) -> str:
        """
        Build SQL expression to lookup remapped FK value.

        Args:
            old_fk_value: Original FK value from source DB
            target_table_full: Fully qualified target table name (schema.table)
            fk_data_type: PostgreSQL data type for casting

        Returns:
            SQL expression - either subquery for lookup or NULL

        Examples:
            NULL -> NULL
            3 -> (SELECT new_id::INTEGER FROM _pgslice_id_map WHERE table_name='users' AND old_id='3')
        """
        if old_fk_value is None:
            return "NULL"

        old_id_str = str(old_fk_value)

        return (
            f"(SELECT new_id::{fk_data_type} FROM _pgslice_id_map "
            f"WHERE table_name='{target_table_full}' AND old_id='{old_id_str}')"
        )

    def _build_natural_key_join_condition(
        self, natural_keys: list[str], left_alias: str, right_alias: str
    ) -> str:
        """
        Build JOIN condition for natural key matching that handles NULLs correctly.

        Uses IS NOT DISTINCT FROM to treat NULL as a distinct value that can match.

        Args:
            natural_keys: List of column names forming the natural key
            left_alias: Alias for left table in JOIN
            right_alias: Alias for right table in JOIN

        Returns:
            SQL JOIN condition string

        Example:
            _build_natural_key_join_condition(["name"], "t", "ti")
            → 't."name" IS NOT DISTINCT FROM ti."name"'

            _build_natural_key_join_condition(["tenant_id", "code"], "t", "ti")
            → 't."tenant_id" IS NOT DISTINCT FROM ti."tenant_id" AND t."code" IS NOT DISTINCT FROM ti."code"'
        """
        conditions = [
            f'{left_alias}."{nk}" IS NOT DISTINCT FROM {right_alias}."{nk}"'
            for nk in natural_keys
        ]
        return " AND ".join(conditions)

    def _detect_natural_keys(
        self,
        schema: str,
        table: str,
    ) -> list[str]:
        """
        Detect columns that likely represent natural keys for idempotency.

        Natural keys are columns that logically should be unique even without
        explicit unique constraints. Used for generating idempotent INSERTs
        when ON CONFLICT cannot be used.

        Priority order:
        1. Manual overrides from --natural-keys CLI option (self.natural_keys)
        2. Common unique column names (name, code, slug, email, etc.)
        3. Reference table pattern (2-3 columns with single non-PK VARCHAR)
        4. Composite patterns (tenant_id + code, etc.)

        Args:
            schema: Schema name
            table: Table name

        Returns:
            List of column names that form natural key, or empty list if none detected
        """
        # Check cache first
        cache_key = (schema, table)
        if cache_key in self._natural_key_cache:
            return self._natural_key_cache[cache_key]

        # PRIORITY 1: Manual overrides from CLI (self.natural_keys)
        if self.natural_keys:
            full_table_name = f"{schema}.{table}"
            if full_table_name in self.natural_keys:
                natural_keys = self.natural_keys[full_table_name]
                self._natural_key_cache[cache_key] = natural_keys
                logger.debug(
                    f"Using manual natural keys for {schema}.{table}: {natural_keys}"
                )
                return natural_keys

            # Also try without schema prefix (for convenience)
            if table in self.natural_keys:
                natural_keys = self.natural_keys[table]
                self._natural_key_cache[cache_key] = natural_keys
                logger.debug(
                    f"Using manual natural keys for {schema}.{table}: {natural_keys}"
                )
                return natural_keys

        # Get table metadata
        table_meta = self.introspector.get_table_metadata(schema, table)

        # Filter to non-PK, non-nullable columns
        candidate_columns = [
            col
            for col in table_meta.columns
            if not col.is_primary_key
            and not col.nullable
            and col.data_type in ("character varying", "text", "varchar")
        ]

        if not candidate_columns:
            self._natural_key_cache[cache_key] = []
            return []

        # PRIORITY 2: Common unique column names (single column)
        common_unique_names = {
            "name",
            "code",
            "slug",
            "email",
            "username",
            "key",
            "identifier",
            "handle",
        }
        common_unique_patterns = ["_code", "_key", "_identifier", "_slug"]

        for col in candidate_columns:
            col_lower = col.name.lower()
            # Exact match
            if col_lower in common_unique_names:
                natural_keys = [col.name]
                self._natural_key_cache[cache_key] = natural_keys
                logger.info(
                    f"Auto-detected natural key for {schema}.{table}: "
                    f"{natural_keys} (common name pattern)"
                )
                return natural_keys

            # Pattern match
            for pattern in common_unique_patterns:
                if col_lower.endswith(pattern):
                    natural_keys = [col.name]
                    self._natural_key_cache[cache_key] = natural_keys
                    logger.info(
                        f"Auto-detected natural key for {schema}.{table}: "
                        f"{natural_keys} (pattern: *{pattern})"
                    )
                    return natural_keys

        # PRIORITY 3: Reference table pattern
        # Table has 2-3 total columns with exactly ONE non-PK non-nullable VARCHAR
        total_columns = len(table_meta.columns)
        if 2 <= total_columns <= 3 and len(candidate_columns) == 1:
            natural_keys = [candidate_columns[0].name]
            self._natural_key_cache[cache_key] = natural_keys
            logger.info(
                f"Auto-detected natural key for {schema}.{table}: "
                f"{natural_keys} (reference table pattern)"
            )
            return natural_keys

        # PRIORITY 4: No natural keys detected
        self._natural_key_cache[cache_key] = []
        return []

    def _build_on_conflict_clause(
        self,
        table_meta: Table,
        insert_columns: list[str],
        auto_gen_pks: list[str],
        schema: str,
        table: str,
    ) -> tuple[str, list[str] | None]:
        """
        Build ON CONFLICT clause OR detect natural keys for idempotency.

        Uses DO UPDATE with a no-op update to always get RETURNING values.
        This makes the SQL idempotent - reusing existing records instead of failing.

        Priority order:
        1. Non-auto-generated primary keys (string PKs, UUIDs, manual IDs) → ON CONFLICT
        2. Unique constraints → ON CONFLICT
        3. Natural keys (auto-detected or manual from self.natural_keys) → CTE pattern
        4. No idempotency available → ERROR

        Args:
            table_meta: Table metadata with primary keys and unique constraints
            insert_columns: Columns being inserted
            auto_gen_pks: Auto-generated PK columns (excluded from ON CONFLICT)
            schema: Schema name (for natural key detection)
            table: Table name (for natural key detection)

        Returns:
            Tuple of (on_conflict_sql, natural_keys):
            - If on_conflict_sql != "": use traditional ON CONFLICT, natural_keys is None
            - If natural_keys is not None: use CTE pattern, on_conflict_sql is ""
            - Both empty: error case (should never happen, raises exception)
        """
        # PRIORITY 1: Check for non-auto-generated primary keys
        # These are string PKs, UUIDs, or manually-set integer PKs
        if table_meta.primary_keys:
            # Get PKs that are NOT auto-generated
            non_auto_gen_pks = [
                pk for pk in table_meta.primary_keys if pk not in auto_gen_pks
            ]

            # Verify all PK columns are being inserted
            if non_auto_gen_pks and all(
                pk in insert_columns for pk in non_auto_gen_pks
            ):
                conflict_cols = ", ".join(f'"{pk}"' for pk in non_auto_gen_pks)
                # Use first PK for no-op update
                update_col = non_auto_gen_pks[0]
                on_conflict = (
                    f"ON CONFLICT ({conflict_cols}) "
                    f'DO UPDATE SET "{update_col}" = EXCLUDED."{update_col}"'
                )
                return (on_conflict, None)

        # PRIORITY 2: Check for unique constraints (existing logic)
        unique_constraints = table_meta.unique_constraints

        # Filter out unique constraints that only contain auto-generated PKs
        # (those are already handled by the PK constraint)
        non_pk_unique = {
            name: cols
            for name, cols in unique_constraints.items()
            if not all(c in auto_gen_pks for c in cols)
        }

        if non_pk_unique:
            # Use the first unique constraint for ON CONFLICT
            # (could be improved to choose best constraint, but any will work)
            constraint_name, constraint_cols = next(iter(non_pk_unique.items()))

            # Check if all constraint columns are in insert_columns
            if all(col in insert_columns for col in constraint_cols):
                conflict_cols = ", ".join(f'"{col}"' for col in constraint_cols)

                # Generate no-op UPDATE clause
                # Pick the first column in the constraint for the update
                update_col = constraint_cols[0]
                on_conflict = (
                    f"ON CONFLICT ({conflict_cols}) "
                    f'DO UPDATE SET "{update_col}" = EXCLUDED."{update_col}"'
                )
                return (on_conflict, None)

        # PRIORITY 3: Natural key detection
        natural_keys = self._detect_natural_keys(schema, table)
        if natural_keys and all(nk in insert_columns for nk in natural_keys):
            return ("", natural_keys)

        # PRIORITY 4: No idempotency available - ERROR
        raise SchemaError(
            f'Cannot generate idempotent SQL for table "{schema}"."{table}". '
            f"Table has auto-generated primary keys with no unique constraints. "
            f'Please specify natural keys using: --natural-keys "{schema}.{table}=col1,col2"'
        )

    def _generate_insert_with_remapping(
        self, schema: str, table: str, records: list[RecordData]
    ) -> str:
        """Generate INSERT with RETURNING and store ID mappings, with ON CONFLICT support."""
        # Get auto-generated PK columns
        auto_gen_pks = self._get_auto_generated_pk_columns(schema, table)
        table_meta = self.introspector.get_table_metadata(schema, table)

        # Get all columns EXCEPT auto-generated PKs
        first_record = records[0]
        all_columns = sorted(first_record.data.keys())
        insert_columns = [col for col in all_columns if col not in auto_gen_pks]

        # Build column list
        columns_sql = ", ".join(f'"{col}"' for col in insert_columns)

        # Get column type mapping for array/JSON distinction
        column_type_map = self._get_column_types(schema, table)

        # Build VALUES rows
        values_rows = []
        old_pk_values = []
        for record in records:
            values = [
                self._format_value(record.data.get(col), column_type_map.get(col))
                for col in insert_columns
            ]
            values_sql = ", ".join(values)
            values_rows.append(f"        ({values_sql})")

            # Store old PK value for mapping
            # Get the PK values from the record identifier
            old_pks = record.identifier.pk_values
            old_pk_values.append(self._serialize_pk_value(old_pks))

        values_clause = ",\n".join(values_rows)
        full_table_name = f'"{schema}"."{table}"'

        # Build ON CONFLICT clause for unique constraints (or detect natural keys)
        on_conflict, natural_keys = self._build_on_conflict_clause(
            table_meta, insert_columns, auto_gen_pks, schema, table
        )

        # Route to natural key CTE pattern if natural keys detected
        if natural_keys:
            logger.debug(
                f"Using natural key CTE pattern for {schema}.{table} "
                f"with keys: {natural_keys}"
            )
            return self._generate_insert_with_natural_key_check(
                schema, table, records, natural_keys, auto_gen_pks
            )

        # Use traditional ON CONFLICT approach
        if len(records) == 1:
            # Single insert: use RETURNING INTO scalar variable
            sql_lines = [
                f"    INSERT INTO {full_table_name} ({columns_sql})",
                "    VALUES",
                f"{values_clause}",
            ]
            if on_conflict:
                sql_lines.append(f"    {on_conflict}")
            sql_lines.extend(
                [
                    f"    RETURNING {auto_gen_pks[0]} INTO v_new_id_{table};",
                    f"    INSERT INTO _pgslice_id_map VALUES ('{full_table_name}', '{old_pk_values[0]}', v_new_id_{table}::TEXT);",
                ]
            )
        else:
            # Bulk insert: use WITH + array aggregation + loop
            old_ids_array = ", ".join(f"'{val}'" for val in old_pk_values)
            sql_lines = [
                f"    v_old_ids_{table} := ARRAY[{old_ids_array}];",
                "    WITH inserted AS (",
                f"        INSERT INTO {full_table_name} ({columns_sql})",
                "        VALUES",
                f"{values_clause}",
            ]
            if on_conflict:
                sql_lines.append(f"        {on_conflict}")
            sql_lines.extend(
                [
                    f"        RETURNING {auto_gen_pks[0]}",
                    "    )",
                    f"    SELECT array_agg({auto_gen_pks[0]}) INTO v_new_ids_{table} FROM inserted;",
                    "    ",
                    f"    FOR i IN 1..array_length(v_new_ids_{table}, 1) LOOP",
                    f"        INSERT INTO _pgslice_id_map VALUES ('{full_table_name}', v_old_ids_{table}[i], v_new_ids_{table}[i]::TEXT);",
                    "    END LOOP;",
                ]
            )

        return "\n".join(sql_lines)

    def _generate_insert_with_natural_key_check(
        self,
        schema: str,
        table: str,
        records: list[RecordData],
        natural_keys: list[str],
        auto_gen_pks: list[str],
    ) -> str:
        """
        Generate INSERT with natural key checking using CTE pattern.

        Uses WHERE NOT EXISTS pattern to check for existing records by natural key.
        This enables idempotent INSERTs when ON CONFLICT cannot be used
        (no unique constraints on natural key columns).

        Algorithm:
        1. Create to_insert CTE with old_ids and data
        2. Find existing records by natural key match (existing CTE)
        3. INSERT only records not in existing (inserted CTE)
        4. Join inserted records back to old_ids via natural key (inserted_with_old_ids CTE)
        5. Combine existing and inserted IDs (all_ids CTE)
        6. Aggregate in old_id order to maintain FK mapping alignment

        Args:
            schema: Schema name
            table: Table name
            records: List of records to insert
            natural_keys: List of column names forming natural key
            auto_gen_pks: List of auto-generated PK column names

        Returns:
            PL/pgSQL code for CTE-based INSERT with natural key checking
        """
        if not natural_keys:
            raise ValueError("natural_keys must be non-empty")

        if not auto_gen_pks:
            raise ValueError("auto_gen_pks must be non-empty for this method")

        # Get all columns EXCEPT auto-generated PKs
        first_record = records[0]
        all_columns = sorted(first_record.data.keys())
        insert_columns = [col for col in all_columns if col not in auto_gen_pks]

        # Verify natural keys are in insert columns
        missing_nk = [nk for nk in natural_keys if nk not in insert_columns]
        if missing_nk:
            raise SchemaError(
                f"Natural key columns {missing_nk} not found in "
                f"insert columns for {schema}.{table}"
            )

        # Build column list
        columns_sql = ", ".join(f'"{col}"' for col in insert_columns)
        natural_keys_sql = ", ".join(f'"{nk}"' for nk in natural_keys)

        # Get column type mapping
        column_type_map = self._get_column_types(schema, table)

        # Build VALUES rows and collect old PK values
        values_rows = []
        old_pk_values = []
        for record in records:
            values = [
                self._format_value(record.data.get(col), column_type_map.get(col))
                for col in insert_columns
            ]
            values_sql = ", ".join(values)
            values_rows.append(f"        ({values_sql})")

            old_pks = record.identifier.pk_values
            old_pk_values.append(self._serialize_pk_value(old_pks))

        values_clause = ",\n".join(values_rows)
        full_table_name = f'"{schema}"."{table}"'
        pk_col = auto_gen_pks[0]  # Use first PK column

        # Build natural key JOIN conditions
        nk_join_existing = self._build_natural_key_join_condition(
            natural_keys, "t", "ti"
        )
        nk_join_inserted = self._build_natural_key_join_condition(
            natural_keys, "ins", "ti"
        )

        old_ids_array = ", ".join(f"'{val}'" for val in old_pk_values)

        # Generate CTE-based INSERT
        sql_lines = [
            f"    v_old_ids_{table} := ARRAY[{old_ids_array}];",
            "    WITH to_insert AS (",
            "        SELECT",
            f"            unnest(v_old_ids_{table}) AS old_id,",
            "            *",
            "        FROM (VALUES",
            f"{values_clause}",
            f"        ) AS data({columns_sql})",
            "    ),",
            "    existing AS (",
            f"        SELECT t.{pk_col} AS new_id, ti.old_id",
            f"        FROM {full_table_name} t",
            "        INNER JOIN to_insert ti",
            f"            ON {nk_join_existing}",
            "    ),",
            "    inserted AS (",
            f"        INSERT INTO {full_table_name} ({columns_sql})",
            f"        SELECT {columns_sql}",
            "        FROM to_insert",
            "        WHERE old_id NOT IN (SELECT old_id FROM existing)",
            f"        RETURNING {pk_col}, {natural_keys_sql}",
            "    ),",
            "    inserted_with_old_ids AS (",
            f"        SELECT ins.{pk_col} AS new_id, ti.old_id",
            "        FROM inserted ins",
            "        INNER JOIN to_insert ti",
            f"            ON {nk_join_inserted}",
            "    ),",
            "    all_ids AS (",
            "        SELECT old_id, new_id FROM existing",
            "        UNION ALL",
            "        SELECT old_id, new_id FROM inserted_with_old_ids",
            "    )",
            f"    SELECT array_agg(new_id ORDER BY old_id) INTO v_new_ids_{table}",
            "    FROM all_ids;",
            "    ",
            f"    FOR i IN 1..array_length(v_new_ids_{table}, 1) LOOP",
            f"        INSERT INTO _pgslice_id_map VALUES ('{full_table_name}', v_old_ids_{table}[i], v_new_ids_{table}[i]::TEXT);",
            "    END LOOP;",
        ]

        return "\n".join(sql_lines)

    def _generate_insert_with_fk_remapping(
        self,
        schema: str,
        table: str,
        records: list[RecordData],
        tables_with_remapped_ids: set[tuple[str, str]],
    ) -> str:
        """
        Generate INSERT with FK remapping using JOIN-based approach.

        Instead of subqueries per value, use a single INSERT-SELECT with JOINs.
        Much more efficient for large datasets.

        Example output:
            INSERT INTO film_actor (actor_id, film_id, last_update)
            SELECT
                map0.new_id::integer,
                map1.new_id::integer,
                data."last_update"
            FROM (VALUES
                ('20', '1', '2006-02-15T10:05:03'),
                ...
            ) AS data("old_actor_id", "old_film_id", "last_update")
            JOIN _pgslice_id_map map0 ...
            JOIN _pgslice_id_map map1 ...
        """
        # Check if table has auto-generated PKs
        auto_gen_pks = self._get_auto_generated_pk_columns(schema, table)
        has_auto_gen_pks = len(auto_gen_pks) > 0

        # Get FK columns that need remapping
        fk_to_remap = self._get_fk_columns_to_remap(
            schema, table, tables_with_remapped_ids
        )

        # Build column list
        first_record = records[0]
        all_columns = sorted(first_record.data.keys())

        # Exclude auto-gen PKs if present (they will be generated by the database)
        if has_auto_gen_pks:
            columns = [col for col in all_columns if col not in auto_gen_pks]
        else:
            columns = all_columns

        # Get column type mapping for array/JSON distinction
        column_type_map = self._get_column_types(schema, table)

        full_table_name = f'"{schema}"."{table}"'

        # If no FKs to remap, use simple INSERT VALUES
        if not fk_to_remap:
            columns_sql = ", ".join(f'"{col}"' for col in columns)
            values_rows = []
            for record in records:
                values = []
                for col in columns:
                    values.append(
                        self._format_value(
                            record.data.get(col), column_type_map.get(col)
                        )
                    )
                values_sql = ", ".join(values)
                values_rows.append(f"        ({values_sql})")
            values_clause = ",\n".join(values_rows)

            # Build ON CONFLICT clause for idempotency (or detect natural keys)
            table_meta = self.introspector.get_table_metadata(schema, table)
            on_conflict, natural_keys = self._build_on_conflict_clause(
                table_meta, columns, auto_gen_pks, schema, table
            )

            # Note: Natural key CTE pattern not implemented for FK remapping case yet
            # Fall back to ON CONFLICT (which will error if natural_keys and no unique constraint)
            if natural_keys:
                logger.warning(
                    f"Natural keys detected for {schema}.{table} but FK remapping is needed. "
                    f"Natural key + FK remapping not yet supported. "
                    f"Attempting ON CONFLICT fallback (may fail)."
                )

            sql_parts = [
                f"    INSERT INTO {full_table_name} ({columns_sql})",
                "    VALUES",
                f"{values_clause}",
            ]
            if on_conflict:
                sql_parts.append(f"    {on_conflict}")
            sql_parts.append(";")

            return "\n".join(sql_parts)

        # Build VALUES clause with old FK values as strings
        values_rows = []
        old_pk_values = []  # Track old PK values for mapping (if has_auto_gen_pks)

        for record in records:
            values = []
            for col in columns:
                value = record.data.get(col)
                if col in fk_to_remap:
                    # For FK columns, use old ID as string
                    if value is None:
                        values.append("NULL")
                    else:
                        # Escape single quotes in the value
                        escaped_value = str(value).replace("'", "''")
                        values.append(f"'{escaped_value}'")
                else:
                    # For regular columns, format normally
                    values.append(self._format_value(value, column_type_map.get(col)))
            values_sql = ", ".join(values)
            values_rows.append(f"        ({values_sql})")

            # Track old PK values for mapping (if has auto-gen PKs)
            if has_auto_gen_pks:
                old_pks = record.identifier.pk_values
                old_pk_values.append(self._serialize_pk_value(old_pks))

        values_clause = ",\n".join(values_rows)

        # Create column aliases for the VALUES clause
        # Example: data("old_actor_id", "old_film_id", "description", "last_update")
        data_column_aliases = []
        for col in columns:
            if col in fk_to_remap:
                # Quote the prefixed alias for remapped FK columns
                data_column_aliases.append(self._quote_identifier(f"old_{col}"))
            else:
                # Quote regular column names to handle reserved keywords
                data_column_aliases.append(self._quote_identifier(col))

        # Get table metadata for column types
        table_meta = self.introspector.get_table_metadata(schema, table)

        # Build SELECT clause and JOIN clauses
        select_parts = []
        join_clauses = []
        join_index = 0

        for col in columns:
            if col in fk_to_remap:
                # FK column: select from mapping table
                target_schema, target_table = fk_to_remap[col]
                target_full = f'"{target_schema}"."{target_table}"'
                alias = f"map{join_index}"

                # Get column data type for casting
                col_meta = next((c for c in table_meta.columns if c.name == col), None)
                if col_meta:
                    col_type = col_meta.data_type
                    # For user-defined types, use udt_name
                    if col_type.upper() == "USER-DEFINED":
                        col_type = col_meta.udt_name
                else:
                    col_type = "INTEGER"

                select_parts.append(f"{alias}.new_id::{col_type}")

                # Add JOIN clause
                join_clauses.append(
                    f"    JOIN _pgslice_id_map {alias}\n"
                    f"        ON {alias}.table_name = '{target_full}'\n"
                    f"        AND {alias}.old_id = data.{self._quote_identifier(f'old_{col}')}"
                )
                join_index += 1
            else:
                # Regular column: select from data with proper type casting
                col_meta = next((c for c in table_meta.columns if c.name == col), None)
                if col_meta:
                    # Get the PostgreSQL type for casting
                    # Map from information_schema data_type to PostgreSQL cast type
                    pg_type = col_meta.data_type

                    # For user-defined types (ENUMs, custom types), use udt_name
                    if pg_type.upper() == "USER-DEFINED":
                        pg_type = col_meta.udt_name
                    # For arrays, use udt_name which includes the [] suffix properly
                    elif pg_type.upper() == "ARRAY":
                        # For arrays, we need to use the udt_name and convert to proper array type
                        element_type = self._get_array_element_type(col_meta.udt_name)
                        pg_type = f"{element_type}[]"

                    select_parts.append(
                        f"data.{self._quote_identifier(col)}::{pg_type}"
                    )
                else:
                    # Fallback if column metadata not found
                    select_parts.append(f"data.{self._quote_identifier(col)}")

        select_clause = ",\n        ".join(select_parts)
        join_clause = "\n".join(join_clauses)

        # Build final INSERT-SELECT statement
        columns_sql = ", ".join(f'"{col}"' for col in columns)
        data_aliases_sql = ", ".join(data_column_aliases)

        # Base INSERT-SELECT statement
        base_sql_lines = [
            f"    INSERT INTO {full_table_name} ({columns_sql})",
            "    SELECT",
            f"        {select_clause}",
            "    FROM (VALUES",
            f"{values_clause}",
            f"    ) AS data({data_aliases_sql})",
            f"{join_clause}",
        ]

        # If table has auto-generated PKs, add RETURNING and mapping storage
        if has_auto_gen_pks:
            table_meta = self.introspector.get_table_metadata(schema, table)

            # Build ON CONFLICT clause for idempotency (or detect natural keys)
            on_conflict, natural_keys = self._build_on_conflict_clause(
                table_meta, columns, auto_gen_pks, schema, table
            )

            # Note: Natural key CTE pattern not implemented for FK remapping case yet
            if natural_keys:
                logger.warning(
                    f"Natural keys detected for {schema}.{table} but FK remapping is needed. "
                    f"Natural key + FK remapping not yet supported. "
                    f"Attempting ON CONFLICT fallback (may fail)."
                )

            if len(records) == 1:
                # Single insert: use RETURNING INTO scalar variable
                sql_lines = base_sql_lines.copy()
                # Remove the semicolon from the last line (join_clause)
                sql_lines[-1] = sql_lines[-1].rstrip(";")
                if on_conflict:
                    sql_lines.append(f"    {on_conflict}")
                sql_lines.extend(
                    [
                        f"    RETURNING {auto_gen_pks[0]} INTO v_new_id_{table};",
                        f"    INSERT INTO _pgslice_id_map VALUES ('{full_table_name}', '{old_pk_values[0]}', v_new_id_{table}::TEXT);",
                    ]
                )
                return "\n".join(sql_lines)
            else:
                # Bulk insert: wrap in WITH clause + array aggregation
                old_ids_array = ", ".join(f"'{val}'" for val in old_pk_values)
                sql_lines = [
                    f"    v_old_ids_{table} := ARRAY[{old_ids_array}];",
                    "    WITH inserted AS (",
                ]
                # Indent base SQL by 4 more spaces
                for line in base_sql_lines:
                    # Remove the semicolon from join_clause line
                    line = line.rstrip(";")
                    sql_lines.append(f"    {line}")
                if on_conflict:
                    sql_lines.append(f"        {on_conflict}")
                sql_lines.extend(
                    [
                        f"        RETURNING {auto_gen_pks[0]}",
                        "    )",
                        f"    SELECT array_agg({auto_gen_pks[0]}) INTO v_new_ids_{table} FROM inserted;",
                        "    ",
                        f"    FOR i IN 1..array_length(v_new_ids_{table}, 1) LOOP",
                        f"        INSERT INTO _pgslice_id_map VALUES ('{full_table_name}', v_old_ids_{table}[i], v_new_ids_{table}[i]::TEXT);",
                        "    END LOOP;",
                    ]
                )
                return "\n".join(sql_lines)
        else:
            # No auto-gen PKs: return simple INSERT-SELECT with ON CONFLICT
            table_meta = self.introspector.get_table_metadata(schema, table)

            # Build ON CONFLICT clause for idempotency (or detect natural keys)
            on_conflict, natural_keys = self._build_on_conflict_clause(
                table_meta, columns, auto_gen_pks, schema, table
            )

            # Note: Natural key CTE pattern not implemented for FK remapping case yet
            if natural_keys:
                logger.warning(
                    f"Natural keys detected for {schema}.{table} but FK remapping is needed. "
                    f"Natural key + FK remapping not yet supported. "
                    f"Attempting ON CONFLICT fallback (may fail)."
                )

            sql_lines = base_sql_lines.copy()
            # Remove trailing semicolon if present
            sql_lines[-1] = sql_lines[-1].rstrip(";")
            if on_conflict:
                sql_lines.append(f"    {on_conflict}")
            # Add semicolon at the end
            sql_lines.append(";")
            return "\n".join(sql_lines)
