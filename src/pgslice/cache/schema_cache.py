"""SQLite-based cache for database schema metadata."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from ..graph.models import Column, ForeignKey, Table
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class SchemaCache:
    """SQLite-based cache for database schema metadata with TTL."""

    def __init__(self, cache_path: Path, ttl_hours: int = 24) -> None:
        """
        Initialize schema cache.

        Args:
            cache_path: Path to SQLite cache database
            ttl_hours: Time-to-live for cached data in hours
        """
        self.cache_path = cache_path
        self.ttl = timedelta(hours=ttl_hours)
        self._init_cache_db()

    def _init_cache_db(self) -> None:
        """Initialize SQLite cache schema."""
        logger.debug(f"Initializing cache database at {self.cache_path}")

        # Ensure directory exists
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.cache_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    db_host TEXT NOT NULL,
                    db_name TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (db_host, db_name)
                );

                CREATE TABLE IF NOT EXISTS tables (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    db_host TEXT NOT NULL,
                    db_name TEXT NOT NULL,
                    schema_name TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    primary_keys TEXT NOT NULL,
                    UNIQUE (db_host, db_name, schema_name, table_name)
                );

                CREATE TABLE IF NOT EXISTS columns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_id INTEGER NOT NULL,
                    column_name TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    udt_name TEXT NOT NULL,
                    nullable INTEGER NOT NULL,
                    default_value TEXT,
                    is_primary_key INTEGER NOT NULL,
                    FOREIGN KEY (table_id) REFERENCES tables(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS foreign_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    constraint_name TEXT NOT NULL,
                    source_table_id INTEGER NOT NULL,
                    source_column TEXT NOT NULL,
                    target_table_id INTEGER NOT NULL,
                    target_column TEXT NOT NULL,
                    on_delete TEXT NOT NULL,
                    FOREIGN KEY (source_table_id) REFERENCES tables(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_table_id) REFERENCES tables(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS unique_constraints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_id INTEGER NOT NULL,
                    constraint_name TEXT NOT NULL,
                    columns TEXT NOT NULL,
                    FOREIGN KEY (table_id) REFERENCES tables(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_tables_lookup
                ON tables(db_host, db_name, schema_name, table_name);

                CREATE INDEX IF NOT EXISTS idx_fk_source
                ON foreign_keys(source_table_id);

                CREATE INDEX IF NOT EXISTS idx_fk_target
                ON foreign_keys(target_table_id);

                CREATE INDEX IF NOT EXISTS idx_unique_constraints
                ON unique_constraints(table_id);
            """)

        logger.debug("Cache database initialized")

    def is_cache_valid(self, db_host: str, db_name: str) -> bool:
        """
        Check if cache exists and is not expired.

        Args:
            db_host: Database host
            db_name: Database name

        Returns:
            True if cache is valid
        """
        with sqlite3.connect(self.cache_path) as conn:
            cur = conn.execute(
                """
                SELECT cached_at FROM cache_metadata
                WHERE db_host = ? AND db_name = ?
                """,
                (db_host, db_name),
            )
            row = cur.fetchone()

        if row is None:
            logger.debug(f"No cache found for {db_host}/{db_name}")
            return False

        cached_at = datetime.fromisoformat(row[0])
        age = datetime.now() - cached_at
        is_valid = age < self.ttl

        logger.debug(
            f"Cache for {db_host}/{db_name}: age={age}, ttl={self.ttl}, valid={is_valid}"
        )
        return is_valid

    def get_table(
        self, db_host: str, db_name: str, schema: str, table: str
    ) -> Table | None:
        """
        Retrieve table metadata from cache.

        Args:
            db_host: Database host
            db_name: Database name
            schema: Schema name
            table: Table name

        Returns:
            Table object or None if not cached
        """
        with sqlite3.connect(self.cache_path) as conn:
            # Get table record
            cur = conn.execute(
                """
                SELECT id, primary_keys
                FROM tables
                WHERE db_host = ? AND db_name = ? AND schema_name = ? AND table_name = ?
                """,
                (db_host, db_name, schema, table),
            )
            table_row = cur.fetchone()

            if table_row is None:
                return None

            table_id, primary_keys_json = table_row
            primary_keys = json.loads(primary_keys_json)

            # Get columns
            cur = conn.execute(
                """
                SELECT column_name, data_type, udt_name, nullable, default_value, is_primary_key
                FROM columns
                WHERE table_id = ?
                ORDER BY id
                """,
                (table_id,),
            )
            columns = [
                Column(
                    name=row[0],
                    data_type=row[1],
                    udt_name=row[2],
                    nullable=bool(row[3]),
                    default=row[4],
                    is_primary_key=bool(row[5]),
                )
                for row in cur.fetchall()
            ]

            # Get outgoing foreign keys
            cur = conn.execute(
                """
                SELECT
                    fk.constraint_name,
                    st.schema_name || '.' || st.table_name AS source_table,
                    fk.source_column,
                    tt.schema_name || '.' || tt.table_name AS target_table,
                    fk.target_column,
                    fk.on_delete
                FROM foreign_keys fk
                JOIN tables st ON st.id = fk.source_table_id
                JOIN tables tt ON tt.id = fk.target_table_id
                WHERE fk.source_table_id = ?
                """,
                (table_id,),
            )
            fk_outgoing = [
                ForeignKey(
                    constraint_name=row[0],
                    source_table=row[1],
                    source_column=row[2],
                    target_table=row[3],
                    target_column=row[4],
                    on_delete=row[5],
                )
                for row in cur.fetchall()
            ]

            # Get incoming foreign keys
            cur = conn.execute(
                """
                SELECT
                    fk.constraint_name,
                    st.schema_name || '.' || st.table_name AS source_table,
                    fk.source_column,
                    tt.schema_name || '.' || tt.table_name AS target_table,
                    fk.target_column,
                    fk.on_delete
                FROM foreign_keys fk
                JOIN tables st ON st.id = fk.source_table_id
                JOIN tables tt ON tt.id = fk.target_table_id
                WHERE fk.target_table_id = ?
                """,
                (table_id,),
            )
            fk_incoming = [
                ForeignKey(
                    constraint_name=row[0],
                    source_table=row[1],
                    source_column=row[2],
                    target_table=row[3],
                    target_column=row[4],
                    on_delete=row[5],
                )
                for row in cur.fetchall()
            ]

            # Get unique constraints
            cur = conn.execute(
                """
                SELECT constraint_name, columns
                FROM unique_constraints
                WHERE table_id = ?
                """,
                (table_id,),
            )
            unique_constraints = {row[0]: json.loads(row[1]) for row in cur.fetchall()}

        logger.debug(f"Retrieved {schema}.{table} from cache")
        return Table(
            schema_name=schema,
            table_name=table,
            columns=columns,
            primary_keys=primary_keys,
            foreign_keys_outgoing=fk_outgoing,
            foreign_keys_incoming=fk_incoming,
            unique_constraints=unique_constraints,
        )

    def cache_table(self, db_host: str, db_name: str, table: Table) -> None:
        """
        Store table metadata in cache.

        Args:
            db_host: Database host
            db_name: Database name
            table: Table metadata to cache
        """
        with sqlite3.connect(self.cache_path) as conn:
            # Update cache metadata
            conn.execute(
                """
                INSERT OR REPLACE INTO cache_metadata (db_host, db_name, cached_at)
                VALUES (?, ?, ?)
                """,
                (db_host, db_name, datetime.now().isoformat()),
            )

            # Insert or get table
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO tables (db_host, db_name, schema_name, table_name, primary_keys)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    db_host,
                    db_name,
                    table.schema_name,
                    table.table_name,
                    json.dumps(table.primary_keys),
                ),
            )

            # Get table ID
            cur = conn.execute(
                """
                SELECT id FROM tables
                WHERE db_host = ? AND db_name = ? AND schema_name = ? AND table_name = ?
                """,
                (db_host, db_name, table.schema_name, table.table_name),
            )
            table_id = cur.fetchone()[0]

            # Delete existing columns, FKs, and unique constraints
            conn.execute("DELETE FROM columns WHERE table_id = ?", (table_id,))
            conn.execute(
                "DELETE FROM foreign_keys WHERE source_table_id = ? OR target_table_id = ?",
                (table_id, table_id),
            )
            conn.execute(
                "DELETE FROM unique_constraints WHERE table_id = ?", (table_id,)
            )

            # Insert columns
            for col in table.columns:
                conn.execute(
                    """
                    INSERT INTO columns (table_id, column_name, data_type, udt_name, nullable, default_value, is_primary_key)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        table_id,
                        col.name,
                        col.data_type,
                        col.udt_name,
                        int(col.nullable),
                        col.default,
                        int(col.is_primary_key),
                    ),
                )

            # Insert foreign keys (both outgoing and incoming)
            for fk in table.foreign_keys_outgoing + table.foreign_keys_incoming:
                # Get source and target table IDs
                source_schema, source_table = self._parse_table_name(fk.source_table)
                target_schema, target_table = self._parse_table_name(fk.target_table)

                # Ensure source and target tables exist
                for schema, tbl in [
                    (source_schema, source_table),
                    (target_schema, target_table),
                ]:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO tables (db_host, db_name, schema_name, table_name, primary_keys)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (db_host, db_name, schema, tbl, "[]"),
                    )

                # Get IDs
                cur = conn.execute(
                    """
                    SELECT id FROM tables
                    WHERE db_host = ? AND db_name = ? AND schema_name = ? AND table_name = ?
                    """,
                    (db_host, db_name, source_schema, source_table),
                )
                source_table_id = cur.fetchone()[0]

                cur = conn.execute(
                    """
                    SELECT id FROM tables
                    WHERE db_host = ? AND db_name = ? AND schema_name = ? AND table_name = ?
                    """,
                    (db_host, db_name, target_schema, target_table),
                )
                target_table_id = cur.fetchone()[0]

                # Insert FK
                conn.execute(
                    """
                    INSERT OR IGNORE INTO foreign_keys
                    (constraint_name, source_table_id, source_column, target_table_id, target_column, on_delete)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fk.constraint_name,
                        source_table_id,
                        fk.source_column,
                        target_table_id,
                        fk.target_column,
                        fk.on_delete,
                    ),
                )

            # Insert unique constraints
            for constraint_name, columns in table.unique_constraints.items():
                conn.execute(
                    """
                    INSERT INTO unique_constraints (table_id, constraint_name, columns)
                    VALUES (?, ?, ?)
                    """,
                    (table_id, constraint_name, json.dumps(columns)),
                )

            conn.commit()

        logger.debug(f"Cached {table.schema_name}.{table.table_name}")

    def invalidate_cache(self, db_host: str, db_name: str) -> None:
        """
        Delete cached schema for a database.

        Args:
            db_host: Database host
            db_name: Database name
        """
        with sqlite3.connect(self.cache_path) as conn:
            conn.execute(
                "DELETE FROM cache_metadata WHERE db_host = ? AND db_name = ?",
                (db_host, db_name),
            )
            # Tables will cascade delete columns and FKs
            conn.execute(
                "DELETE FROM tables WHERE db_host = ? AND db_name = ?",
                (db_host, db_name),
            )
            conn.commit()

        logger.info(f"Invalidated cache for {db_host}/{db_name}")

    @staticmethod
    def _parse_table_name(full_name: str) -> tuple[str, str]:
        """
        Parse 'schema.table' or just 'table' format.

        Args:
            full_name: Fully qualified or simple table name

        Returns:
            Tuple of (schema, table)
        """
        if "." in full_name:
            parts = full_name.split(".", 1)
            return parts[0], parts[1]
        return "public", full_name

    def __enter__(self) -> SchemaCache:
        """Enter context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Exit context manager."""
        pass
