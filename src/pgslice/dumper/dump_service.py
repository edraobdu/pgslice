"""Service for executing database dump operations."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from tqdm import tqdm

from ..config import AppConfig
from ..db.connection import ConnectionManager
from ..db.schema import SchemaIntrospector
from ..graph.models import TimeframeFilter
from ..graph.traverser import RelationshipTraverser
from ..graph.visited_tracker import VisitedTracker
from ..utils.logging_config import get_logger
from ..utils.spinner import SpinnerAnimator, animated_spinner
from .dependency_sorter import DependencySorter
from .sql_generator import SQLGenerator

logger = get_logger(__name__)


@dataclass
class DumpResult:
    """Result of a dump operation."""

    sql_content: str
    record_count: int
    tables_involved: set[str] = field(default_factory=set)


class DumpService:
    """Service for executing database dump operations."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        config: AppConfig,
        show_progress: bool = False,
    ) -> None:
        """
        Initialize dump service.

        Args:
            connection_manager: Database connection manager
            config: Application configuration
            show_progress: Whether to show progress bar (writes to stderr)
        """
        self.conn_manager = connection_manager
        self.config = config
        self.show_progress = show_progress

    def dump(
        self,
        table: str,
        pk_values: list[str],
        schema: str = "public",
        wide_mode: bool = False,
        keep_pks: bool = False,
        create_schema: bool = False,
        timeframe_filters: list[TimeframeFilter] | None = None,
        show_graph: bool = False,
    ) -> DumpResult:
        """
        Execute dump operation and return result.

        Args:
            table: Table name to dump
            pk_values: List of primary key values
            schema: Database schema name
            wide_mode: Whether to follow all relationships including self-referencing FKs
            keep_pks: Whether to keep original primary key values
            create_schema: Whether to include DDL statements
            timeframe_filters: Optional timeframe filters
            show_graph: Whether to display relationship graph after dump

        Returns:
            DumpResult with SQL content and metadata
        """
        timeframe_filters = timeframe_filters or []

        # Progress bar with 4 steps, writes to stderr
        with tqdm(
            total=4,
            desc="Dumping",
            disable=not self.show_progress,
            file=sys.stderr,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}",
        ) as pbar:
            # Create spinner animator (updates every 100ms for smooth animation)
            spinner = SpinnerAnimator(update_interval=0.1)

            # Step 1: Setup and traverse relationships (using animated spinner)
            with animated_spinner(
                spinner, pbar.set_description, "Traversing relationships"
            ):
                conn = self.conn_manager.get_connection()
                introspector = SchemaIntrospector(conn)
                visited = VisitedTracker()
                traverser = RelationshipTraverser(
                    conn,
                    introspector,
                    visited,
                    timeframe_filters,
                    wide_mode=wide_mode,
                    fetch_batch_size=self.config.sql_batch_size,
                )

                if len(pk_values) == 1:
                    records = traverser.traverse(
                        table, pk_values[0], schema, self.config.max_depth
                    )
                else:
                    records = traverser.traverse_multiple(
                        table, pk_values, schema, self.config.max_depth
                    )
            pbar.update(1)

            # Step 2: Sort by dependencies (using animated spinner)
            with animated_spinner(
                spinner, pbar.set_description, "Sorting dependencies"
            ):
                sorter = DependencySorter()
                sorted_records = sorter.sort(records)
            pbar.update(1)

            # Step 3: Generate SQL (using animated spinner)
            with animated_spinner(spinner, pbar.set_description, "Generating SQL"):
                generator = SQLGenerator(
                    introspector, batch_size=self.config.sql_batch_size
                )
                sql = generator.generate_batch(
                    sorted_records,
                    keep_pks=keep_pks,
                    create_schema=create_schema,
                    database_name=self.config.db.database,
                    schema_name=schema,
                )
            pbar.update(1)

            # Step 4: Complete
            pbar.set_description("Complete ✓")
            pbar.update(1)

        # Display graph AFTER progress bar completes
        if show_graph and self.show_progress:
            from ..utils.graph_visualizer import GraphBuilder, GraphRenderer

            builder = GraphBuilder()
            graph = builder.build(records, table, schema)

            renderer = GraphRenderer()
            graph_output = renderer.render(graph)

            # Print to stderr with header
            sys.stderr.write("\n")
            sys.stderr.write("=== Relationship Graph ===\n")
            sys.stderr.write(graph_output)
            sys.stderr.write("\n\n")
            sys.stderr.flush()

        # Collect tables involved
        tables_involved = {record.identifier.table_name for record in sorted_records}

        return DumpResult(
            sql_content=sql,
            record_count=len(sorted_records),
            tables_involved=tables_involved,
        )
