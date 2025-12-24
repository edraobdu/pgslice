"""PostgreSQL schema introspection using system catalogs."""

from __future__ import annotations

from typing import Any

import psycopg

from ..graph.models import Column, ForeignKey, Table
from ..utils.exceptions import SchemaError
from ..utils.logging_config import get_logger
from ..utils.security import SQLSanitizer

logger = get_logger(__name__)


class SchemaIntrospector:
    """Introspects PostgreSQL database schema using system catalogs."""

    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        """
        Initialize schema introspector.

        Args:
            connection: Active PostgreSQL connection
        """
        self.conn = connection

    def get_table_metadata(self, schema: str, table: str) -> Table:
        """
        Get complete metadata for a single table.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            Complete Table object with all metadata

        Raises:
            SchemaError: If table doesn't exist or metadata cannot be retrieved
        """
        # Validate identifiers
        SQLSanitizer.validate_schema_table(schema, table)

        logger.debug(f"Fetching metadata for {schema}.{table}")

        try:
            columns = self._get_columns(schema, table)
            primary_keys = self._get_primary_keys(schema, table)
            fk_outgoing = self._get_foreign_keys_outgoing(schema, table)
            fk_incoming = self._get_foreign_keys_incoming(schema, table)
            unique_constraints = self._get_unique_constraints(schema, table)

            # Mark PK columns and detect auto-generated columns
            pk_set = set(primary_keys)
            columns = [
                Column(
                    name=col.name,
                    data_type=col.data_type,
                    udt_name=col.udt_name,
                    nullable=col.nullable,
                    default=col.default,
                    is_primary_key=col.name in pk_set,
                    is_auto_generated=(
                        col.name in pk_set
                        and self._is_auto_generated_column(schema, table, col.name)
                    ),
                )
                for col in columns
            ]

            return Table(
                schema_name=schema,
                table_name=table,
                columns=columns,
                primary_keys=primary_keys,
                foreign_keys_outgoing=fk_outgoing,
                foreign_keys_incoming=fk_incoming,
                unique_constraints=unique_constraints,
            )

        except psycopg.Error as e:
            raise SchemaError(f"Failed to introspect {schema}.{table}: {e}") from e

    def _get_columns(self, schema: str, table: str) -> list[Column]:
        """
        Query information_schema.columns for table columns.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            List of Column objects
        """
        query = """
            SELECT
                column_name,
                data_type,
                udt_name,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """

        with self.conn.cursor() as cur:
            cur.execute(query, (schema, table))
            rows = cur.fetchall()

        if not rows:
            raise SchemaError(f"Table {schema}.{table} not found or has no columns")

        columns = []
        for row in rows:
            column_name, data_type, udt_name, is_nullable, column_default = row
            columns.append(
                Column(
                    name=column_name,
                    data_type=data_type,
                    udt_name=udt_name,
                    nullable=is_nullable == "YES",
                    default=column_default,
                    is_primary_key=False,  # Will be set later
                )
            )

        logger.debug(f"Found {len(columns)} columns in {schema}.{table}")
        return columns

    def _get_primary_keys(self, schema: str, table: str) -> list[str]:
        """
        Query pg_constraint for primary key columns.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            List of primary key column names in order
        """
        query = """
            SELECT a.attname AS column_name
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid
                AND a.attnum = ANY(i.indkey)
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE i.indisprimary
                AND n.nspname = %s
                AND c.relname = %s
            ORDER BY array_position(i.indkey, a.attnum)
        """

        with self.conn.cursor() as cur:
            cur.execute(query, (schema, table))
            rows = cur.fetchall()

        primary_keys = [row[0] for row in rows]

        if not primary_keys:
            logger.warning(f"No primary key found for {schema}.{table}")

        logger.debug(f"Primary keys for {schema}.{table}: {primary_keys}")
        return primary_keys

    def _is_auto_generated_column(self, schema: str, table: str, column: str) -> bool:
        """
        Detect if a column is auto-generated (SERIAL, BIGSERIAL, IDENTITY).

        Checks:
        1. Column has associated sequence (pg_get_serial_sequence)
        2. Column is IDENTITY column (attidentity)
        3. Column default contains 'nextval('

        Args:
            schema: Schema name
            table: Table name
            column: Column name

        Returns:
            True if column is auto-generated
        """
        query = """
            SELECT
                pg_get_serial_sequence(%s || '.' || %s, %s) IS NOT NULL as has_sequence,
                a.attidentity IN ('a', 'd') as is_identity,
                col.column_default
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            LEFT JOIN information_schema.columns col
                ON col.table_schema = n.nspname
                AND col.table_name = c.relname
                AND col.column_name = a.attname
            WHERE n.nspname = %s
                AND c.relname = %s
                AND a.attname = %s
                AND a.attnum > 0
                AND NOT a.attisdropped
        """

        try:
            with self.conn.cursor() as cur:
                cur.execute(query, (schema, table, column, schema, table, column))
                row = cur.fetchone()

            if not row:
                return False

            has_sequence, is_identity, column_default = row

            # Check if it's a SERIAL/BIGSERIAL (has sequence)
            if has_sequence:
                return True

            # Check if it's an IDENTITY column
            if is_identity:
                return True

            # Check if default contains nextval (fallback for edge cases)
            return bool(column_default and "nextval(" in column_default.lower())

        except Exception as e:
            logger.warning(
                f"Could not check if {schema}.{table}.{column} is auto-generated: {e}"
            )
            return False

    def _get_foreign_keys_outgoing(self, schema: str, table: str) -> list[ForeignKey]:
        """
        Query pg_constraint for foreign keys FROM this table to other tables.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            List of ForeignKey objects
        """
        query = """
            SELECT DISTINCT ON (c.conname)
                c.conname AS constraint_name,
                ns.nspname || '.' || cls.relname AS source_table,
                a.attname AS source_column,
                nf.nspname || '.' || clf.relname AS target_table,
                af.attname AS target_column,
                CASE c.confdeltype
                    WHEN 'a' THEN 'NO ACTION'
                    WHEN 'r' THEN 'RESTRICT'
                    WHEN 'c' THEN 'CASCADE'
                    WHEN 'n' THEN 'SET NULL'
                    WHEN 'd' THEN 'SET DEFAULT'
                    ELSE 'NO ACTION'
                END AS on_delete
            FROM pg_constraint c
            JOIN pg_class cls ON cls.oid = c.conrelid
            JOIN pg_namespace ns ON ns.oid = cls.relnamespace
            JOIN pg_class clf ON clf.oid = c.confrelid
            JOIN pg_namespace nf ON nf.oid = clf.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.conrelid
                AND a.attnum = ANY(c.conkey)
            JOIN pg_attribute af ON af.attrelid = c.confrelid
                AND af.attnum = ANY(c.confkey)
            WHERE c.contype = 'f'
                AND ns.nspname = %s
                AND cls.relname = %s
            ORDER BY c.conname, a.attnum
        """

        with self.conn.cursor() as cur:
            cur.execute(query, (schema, table))
            rows = cur.fetchall()

        foreign_keys = []
        for row in rows:
            (
                constraint_name,
                source_table,
                source_column,
                target_table,
                target_column,
                on_delete,
            ) = row
            foreign_keys.append(
                ForeignKey(
                    constraint_name=constraint_name,
                    source_table=source_table,
                    source_column=source_column,
                    target_table=target_table,
                    target_column=target_column,
                    on_delete=on_delete,
                )
            )

        logger.debug(f"Found {len(foreign_keys)} outgoing FKs from {schema}.{table}")
        return foreign_keys

    def _get_foreign_keys_incoming(self, schema: str, table: str) -> list[ForeignKey]:
        """
        Query pg_constraint for foreign keys FROM other tables TO this table.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            List of ForeignKey objects
        """
        query = """
            SELECT DISTINCT ON (c.conname)
                c.conname AS constraint_name,
                ns.nspname || '.' || cls.relname AS source_table,
                a.attname AS source_column,
                nf.nspname || '.' || clf.relname AS target_table,
                af.attname AS target_column,
                CASE c.confdeltype
                    WHEN 'a' THEN 'NO ACTION'
                    WHEN 'r' THEN 'RESTRICT'
                    WHEN 'c' THEN 'CASCADE'
                    WHEN 'n' THEN 'SET NULL'
                    WHEN 'd' THEN 'SET DEFAULT'
                    ELSE 'NO ACTION'
                END AS on_delete
            FROM pg_constraint c
            JOIN pg_class cls ON cls.oid = c.conrelid
            JOIN pg_namespace ns ON ns.oid = cls.relnamespace
            JOIN pg_class clf ON clf.oid = c.confrelid
            JOIN pg_namespace nf ON nf.oid = clf.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.conrelid
                AND a.attnum = ANY(c.conkey)
            JOIN pg_attribute af ON af.attrelid = c.confrelid
                AND af.attnum = ANY(c.confkey)
            WHERE c.contype = 'f'
                AND nf.nspname = %s
                AND clf.relname = %s
            ORDER BY c.conname, a.attnum
        """

        with self.conn.cursor() as cur:
            cur.execute(query, (schema, table))
            rows = cur.fetchall()

        foreign_keys = []
        for row in rows:
            (
                constraint_name,
                source_table,
                source_column,
                target_table,
                target_column,
                on_delete,
            ) = row
            foreign_keys.append(
                ForeignKey(
                    constraint_name=constraint_name,
                    source_table=source_table,
                    source_column=source_column,
                    target_table=target_table,
                    target_column=target_column,
                    on_delete=on_delete,
                )
            )

        logger.debug(f"Found {len(foreign_keys)} incoming FKs to {schema}.{table}")
        return foreign_keys

    def _get_unique_constraints(self, schema: str, table: str) -> dict[str, list[str]]:
        """
        Get unique constraints for a table.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            Dict mapping constraint name to list of column names

        Example:
            {
                "country_country_key": ["country"],
                "language_name_key": ["name"]
            }
        """
        query = """
            SELECT
                c.conname AS constraint_name,
                array_agg(a.attname ORDER BY array_position(c.conkey, a.attnum)) AS columns
            FROM pg_constraint c
            JOIN pg_class cls ON cls.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = cls.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.conrelid
                AND a.attnum = ANY(c.conkey)
            WHERE c.contype = 'u'
                AND n.nspname = %s
                AND cls.relname = %s
            GROUP BY c.conname
        """

        with self.conn.cursor() as cur:
            cur.execute(query, (schema, table))
            rows = cur.fetchall()

        constraints = {row[0]: row[1] for row in rows}
        logger.debug(
            f"Found {len(constraints)} unique constraint(s) in {schema}.{table}"
        )
        return constraints

    def get_all_tables(self, schema: str = "public") -> list[str]:
        """
        Get all table names in a schema.

        Args:
            schema: Schema name (default: public)

        Returns:
            List of table names
        """
        SQLSanitizer.validate_identifier(schema)

        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
                AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """

        with self.conn.cursor() as cur:
            cur.execute(query, (schema,))
            rows = cur.fetchall()

        tables = [row[0] for row in rows]
        logger.debug(f"Found {len(tables)} tables in schema '{schema}'")
        return tables
