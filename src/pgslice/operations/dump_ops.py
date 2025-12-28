"""Dump operations shared by CLI and REPL."""

from __future__ import annotations

from dataclasses import dataclass, field

from pgslice.config import AppConfig
from pgslice.db.connection import ConnectionManager
from pgslice.dumper.dump_service import DumpResult, DumpService
from pgslice.graph.models import TimeframeFilter


@dataclass
class DumpOptions:
    """Options for dump operation."""

    table: str
    pk_values: list[str]
    schema: str
    wide_mode: bool = False
    keep_pks: bool = False
    create_schema: bool = False
    timeframe_filters: list[TimeframeFilter] = field(default_factory=list)
    show_progress: bool = False


def execute_dump(
    conn_manager: ConnectionManager,
    config: AppConfig,
    options: DumpOptions,
) -> DumpResult:
    """
    Execute dump operation.

    Args:
        conn_manager: Database connection manager
        config: Application configuration
        options: Dump options

    Returns:
        DumpResult with SQL content and metadata
    """
    service = DumpService(conn_manager, config, show_progress=options.show_progress)
    return service.dump(
        table=options.table,
        pk_values=options.pk_values,
        schema=options.schema,
        wide_mode=options.wide_mode,
        keep_pks=options.keep_pks,
        create_schema=options.create_schema,
        timeframe_filters=options.timeframe_filters,
    )
