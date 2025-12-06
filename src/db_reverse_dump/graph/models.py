"""Data models for database schema and record representation."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ColumnType(Enum):
    """PostgreSQL column types."""

    INTEGER = "integer"
    BIGINT = "bigint"
    SMALLINT = "smallint"
    TEXT = "text"
    VARCHAR = "varchar"
    CHAR = "char"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"
    TIMESTAMPTZ = "timestamptz"
    DATE = "date"
    TIME = "time"
    UUID = "uuid"
    JSON = "json"
    JSONB = "jsonb"
    NUMERIC = "numeric"
    REAL = "real"
    DOUBLE = "double precision"
    BYTEA = "bytea"
    ARRAY = "array"
    OTHER = "other"


@dataclass(frozen=True)
class Column:
    """Represents a database column."""

    name: str
    data_type: str  # Store as string, convert to ColumnType as needed
    nullable: bool
    default: str | None = None
    is_primary_key: bool = False


@dataclass(frozen=True)
class ForeignKey:
    """Represents a foreign key relationship."""

    constraint_name: str
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    on_delete: str = "NO ACTION"  # CASCADE, SET NULL, RESTRICT, NO ACTION

    def __hash__(self) -> int:
        """Make hashable for use in sets."""
        return hash(
            (
                self.source_table,
                self.source_column,
                self.target_table,
                self.target_column,
            )
        )


@dataclass
class Table:
    """Represents a database table with complete metadata."""

    schema_name: str
    table_name: str
    columns: list[Column]
    primary_keys: list[str]
    foreign_keys_outgoing: list[ForeignKey]  # FKs from this table to others
    foreign_keys_incoming: list[ForeignKey]  # FKs from other tables to this one

    @property
    def full_name(self) -> str:
        """Get fully qualified table name."""
        return f"{self.schema_name}.{self.table_name}"


@dataclass(frozen=True)
class RecordIdentifier:
    """Uniquely identifies a database record by table and primary key(s)."""

    table_name: str
    schema_name: str
    pk_values: tuple[Any, ...]  # Support composite primary keys

    def __hash__(self) -> int:
        """Make hashable for use in sets (visited tracking)."""
        return hash((self.schema_name, self.table_name, self.pk_values))

    def __eq__(self, other: object) -> bool:
        """Equality comparison for visited tracking."""
        if not isinstance(other, RecordIdentifier):
            return NotImplemented
        return (
            self.schema_name == other.schema_name
            and self.table_name == other.table_name
            and self.pk_values == other.pk_values
        )

    def __repr__(self) -> str:
        """String representation."""
        pk_str = ", ".join(str(v) for v in self.pk_values)
        return f"{self.schema_name}.{self.table_name}({pk_str})"


@dataclass
class RecordData:
    """Contains actual record data with dependency information."""

    identifier: RecordIdentifier
    data: dict[str, Any]
    dependencies: set[RecordIdentifier] = field(default_factory=set)

    def __hash__(self) -> int:
        """Make hashable based on identifier."""
        return hash(self.identifier)

    def __eq__(self, other: object) -> bool:
        """Equality based on identifier."""
        if not isinstance(other, RecordData):
            return NotImplemented
        return self.identifier == other.identifier


@dataclass
class TimeframeFilter:
    """Filter records by timestamp range for specific tables."""

    table_name: str
    column_name: str  # Timestamp column (e.g., 'created_at')
    start_date: datetime
    end_date: datetime

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"{self.table_name}.{self.column_name}: "
            f"{self.start_date.date()} to {self.end_date.date()}"
        )
