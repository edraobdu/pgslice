"""Schema introspection operations shared by CLI and REPL."""

from __future__ import annotations

from printy import printy
from tabulate import tabulate

from pgslice.db.connection import ConnectionManager
from pgslice.db.schema import SchemaIntrospector


def list_tables(conn_manager: ConnectionManager, schema: str) -> list[str]:
    """
    List all tables in a schema.

    Args:
        conn_manager: Database connection manager
        schema: Schema name

    Returns:
        List of table names
    """
    conn = conn_manager.get_connection()
    introspector = SchemaIntrospector(conn)
    return introspector.get_all_tables(schema)


def print_tables(tables: list[str], schema: str) -> None:
    """
    Print table list with formatting.

    Args:
        tables: List of table names
        schema: Schema name (for display)
    """
    printy(f"\n[c]Tables in schema '{schema}':@\n")
    for table in tables:
        printy(f"  {table}")
    printy(f"\n[g]Total: {len(tables)} tables@\n")


def describe_table(
    conn_manager: ConnectionManager, schema: str, table_name: str
) -> None:
    """
    Describe table structure and relationships.

    Args:
        conn_manager: Database connection manager
        schema: Schema name
        table_name: Table to describe
    """
    conn = conn_manager.get_connection()
    introspector = SchemaIntrospector(conn)
    table = introspector.get_table_metadata(schema, table_name)

    printy(f"\n[c]Table: {table.full_name}@\n")

    # Columns
    printy("\n[cB]Columns@")
    col_data = []
    for col in table.columns:
        pk_indicator = "✓" if col.is_primary_key else ""
        col_data.append(
            [
                col.name,
                col.data_type,
                "YES" if col.nullable else "NO",
                col.default or "",
                pk_indicator,
            ]
        )
    table_str = tabulate(
        col_data,
        headers=["Name", "Type", "Nullable", "Default", "PK"],
        tablefmt="simple",
    )
    printy(table_str)

    # Primary keys
    if table.primary_keys:
        printy(f"\n[g]Primary Keys:@ {', '.join(table.primary_keys)}")

    # Foreign keys outgoing
    if table.foreign_keys_outgoing:
        printy("\n[y]Foreign Keys (Outgoing):@")
        for fk in table.foreign_keys_outgoing:
            printy(f"  {fk.source_column} → {fk.target_table}.{fk.target_column}")

    # Foreign keys incoming
    if table.foreign_keys_incoming:
        printy("\n[b]Referenced By (Incoming):@")
        for fk in table.foreign_keys_incoming:
            printy(f"  {fk.source_table}.{fk.source_column} → {fk.target_column}")

    printy()
