"""Faker-based factories for generating test data."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from faker import Faker

from pgslice.graph.models import (
    Column,
    ForeignKey,
    RecordData,
    RecordIdentifier,
    Table,
    TimeframeFilter,
)

fake = Faker()


class ColumnFactory:
    """Factory for generating Column models."""

    @staticmethod
    def create(
        name: str | None = None,
        data_type: str = "integer",
        udt_name: str = "int4",
        nullable: bool = True,
        default: str | None = None,
        is_primary_key: bool = False,
        is_auto_generated: bool = False,
    ) -> Column:
        """Create a Column with configurable attributes."""
        return Column(
            name=name or fake.word(),
            data_type=data_type,
            udt_name=udt_name,
            nullable=nullable,
            default=default,
            is_primary_key=is_primary_key,
            is_auto_generated=is_auto_generated,
        )

    @staticmethod
    def create_primary_key(name: str = "id", auto_generated: bool = True) -> Column:
        """Create a primary key column."""
        return Column(
            name=name,
            data_type="integer",
            udt_name="int4",
            nullable=False,
            is_primary_key=True,
            is_auto_generated=auto_generated,
        )

    @staticmethod
    def create_text(name: str | None = None, nullable: bool = True) -> Column:
        """Create a text column."""
        return Column(
            name=name or fake.word(),
            data_type="text",
            udt_name="text",
            nullable=nullable,
        )

    @staticmethod
    def create_timestamp(name: str = "created_at") -> Column:
        """Create a timestamp column."""
        return Column(
            name=name,
            data_type="timestamp",
            udt_name="timestamp",
            nullable=True,
            default="now()",
        )

    @staticmethod
    def create_foreign_key_column(name: str, nullable: bool = False) -> Column:
        """Create a foreign key column (integer reference)."""
        return Column(
            name=name,
            data_type="integer",
            udt_name="int4",
            nullable=nullable,
        )


class ForeignKeyFactory:
    """Factory for generating ForeignKey models."""

    @staticmethod
    def create(
        source_table: str | None = None,
        source_column: str | None = None,
        target_table: str | None = None,
        target_column: str = "id",
        constraint_name: str | None = None,
        on_delete: str = "NO ACTION",
    ) -> ForeignKey:
        """Create a ForeignKey with configurable attributes."""
        src_table = source_table or fake.word()
        tgt_table = target_table or fake.word()
        src_col = source_column or f"{tgt_table}_id"

        return ForeignKey(
            constraint_name=constraint_name or f"fk_{src_table}_{src_col}",
            source_table=src_table,
            source_column=src_col,
            target_table=tgt_table,
            target_column=target_column,
            on_delete=on_delete,
        )

    @staticmethod
    def create_self_referencing(
        table_name: str,
        column_name: str = "parent_id",
        on_delete: str = "SET NULL",
    ) -> ForeignKey:
        """Create a self-referencing foreign key."""
        return ForeignKey(
            constraint_name=f"fk_{table_name}_{column_name}",
            source_table=table_name,
            source_column=column_name,
            target_table=table_name,
            target_column="id",
            on_delete=on_delete,
        )


class TableFactory:
    """Factory for generating Table models."""

    @staticmethod
    def create(
        schema_name: str = "public",
        table_name: str | None = None,
        columns: list[Column] | None = None,
        primary_keys: list[str] | None = None,
        foreign_keys_outgoing: list[ForeignKey] | None = None,
        foreign_keys_incoming: list[ForeignKey] | None = None,
        unique_constraints: dict[str, list[str]] | None = None,
    ) -> Table:
        """Create a Table with configurable attributes."""
        name = table_name or fake.word()

        if columns is None:
            columns = [
                ColumnFactory.create_primary_key(),
                ColumnFactory.create_text("name"),
            ]

        if primary_keys is None:
            primary_keys = ["id"]

        return Table(
            schema_name=schema_name,
            table_name=name,
            columns=columns,
            primary_keys=primary_keys,
            foreign_keys_outgoing=foreign_keys_outgoing or [],
            foreign_keys_incoming=foreign_keys_incoming or [],
            unique_constraints=unique_constraints or {},
        )

    @staticmethod
    def create_with_fk(
        table_name: str,
        fk_column: str,
        target_table: str,
        schema_name: str = "public",
    ) -> Table:
        """Create a table with a foreign key to another table."""
        fk = ForeignKeyFactory.create(
            source_table=table_name,
            source_column=fk_column,
            target_table=target_table,
        )

        return Table(
            schema_name=schema_name,
            table_name=table_name,
            columns=[
                ColumnFactory.create_primary_key(),
                ColumnFactory.create_foreign_key_column(fk_column),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[fk],
            foreign_keys_incoming=[],
        )

    @staticmethod
    def create_self_referencing(
        table_name: str = "employees",
        parent_column: str = "manager_id",
        schema_name: str = "public",
    ) -> Table:
        """Create a table with self-referencing foreign key."""
        fk = ForeignKeyFactory.create_self_referencing(table_name, parent_column)

        return Table(
            schema_name=schema_name,
            table_name=table_name,
            columns=[
                ColumnFactory.create_primary_key(),
                ColumnFactory.create_text("name"),
                ColumnFactory.create_foreign_key_column(parent_column, nullable=True),
            ],
            primary_keys=["id"],
            foreign_keys_outgoing=[fk],
            foreign_keys_incoming=[fk],  # Self-referencing appears in both
        )


class RecordIdentifierFactory:
    """Factory for generating RecordIdentifier models."""

    @staticmethod
    def create(
        table_name: str | None = None,
        schema_name: str = "public",
        pk_values: tuple[Any, ...] | None = None,
    ) -> RecordIdentifier:
        """Create a RecordIdentifier with configurable attributes."""
        return RecordIdentifier(
            table_name=table_name or fake.word(),
            schema_name=schema_name,
            pk_values=pk_values or (fake.random_int(min=1, max=10000),),
        )


class RecordDataFactory:
    """Factory for generating RecordData models."""

    @staticmethod
    def create(
        identifier: RecordIdentifier | None = None,
        data: dict[str, Any] | None = None,
        dependencies: set[RecordIdentifier] | None = None,
    ) -> RecordData:
        """Create a RecordData with configurable attributes."""
        if identifier is None:
            identifier = RecordIdentifierFactory.create()

        if data is None:
            data = {
                "id": identifier.pk_values[0],
                "name": fake.name(),
                "email": fake.email(),
            }

        return RecordData(
            identifier=identifier,
            data=data,
            dependencies=dependencies or set(),
        )

    @staticmethod
    def create_with_dependencies(
        table_name: str,
        pk_value: int,
        dep_identifiers: list[RecordIdentifier],
        data: dict[str, Any] | None = None,
    ) -> RecordData:
        """Create a RecordData with specific dependencies."""
        identifier = RecordIdentifier(
            table_name=table_name,
            schema_name="public",
            pk_values=(pk_value,),
        )

        return RecordData(
            identifier=identifier,
            data=data or {"id": pk_value},
            dependencies=set(dep_identifiers),
        )


class TimeframeFilterFactory:
    """Factory for generating TimeframeFilter models."""

    @staticmethod
    def create(
        table_name: str | None = None,
        column_name: str = "created_at",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> TimeframeFilter:
        """Create a TimeframeFilter with configurable attributes."""
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now()

        return TimeframeFilter(
            table_name=table_name or fake.word(),
            column_name=column_name,
            start_date=start_date,
            end_date=end_date,
        )

    @staticmethod
    def create_year(
        table_name: str,
        year: int = 2024,
        column_name: str = "created_at",
    ) -> TimeframeFilter:
        """Create a TimeframeFilter for a specific year."""
        return TimeframeFilter(
            table_name=table_name,
            column_name=column_name,
            start_date=datetime(year, 1, 1),
            end_date=datetime(year, 12, 31, 23, 59, 59),
        )
