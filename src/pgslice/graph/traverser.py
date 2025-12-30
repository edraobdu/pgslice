"""Bidirectional relationship traversal via foreign keys."""

from __future__ import annotations

from collections import deque
from typing import Any

import psycopg

from ..db.schema import SchemaIntrospector
from ..graph.models import RecordData, RecordIdentifier, Table, TimeframeFilter
from ..graph.visited_tracker import VisitedTracker
from ..utils.exceptions import RecordNotFoundError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class RelationshipTraverser:
    """
    Traverses database relationships bidirectionally using BFS.

    Follows both forward FK references (this record -> other records)
    and reverse FK references (other records -> this record).
    """

    def __init__(
        self,
        connection: psycopg.Connection[Any],
        schema_introspector: SchemaIntrospector,
        visited_tracker: VisitedTracker,
        timeframe_filters: list[TimeframeFilter] | None = None,
        wide_mode: bool = False,
        fetch_batch_size: int = 500,
    ) -> None:
        """
        Initialize relationship traverser.

        Args:
            connection: Active database connection
            schema_introspector: Schema introspection utility
            visited_tracker: Visited record tracker
            timeframe_filters: Optional timeframe filters for specific tables
            wide_mode: If True, follow incoming FKs from all records (wide/exploratory).
                      If False (default), only follow incoming FKs from starting records
                      and records reached via incoming FKs (strict mode, prevents fan-out).
            fetch_batch_size: Number of records to fetch in a single batch query (default: 500).
                            Higher values reduce database round-trips but increase memory usage.
        """
        self.conn = connection
        self.introspector = schema_introspector
        self.visited = visited_tracker
        self.table_cache: dict[str, Table] = {}
        self.timeframe_filters = {f.table_name: f for f in (timeframe_filters or [])}
        self.wide_mode = wide_mode
        self.fetch_batch_size = fetch_batch_size

    def traverse(
        self,
        table_name: str,
        pk_value: Any,
        schema: str = "public",
        max_depth: int | None = None,
    ) -> set[RecordData]:
        """
        Traverse relationships from a starting record using batch fetching.

        Algorithm:
        1. Start with initial record (table + PK)
        2. Use BFS with queue of (RecordIdentifier, depth, follow_incoming_fks)
        3. Collect records at same depth into batches (up to fetch_batch_size)
        4. For each batch:
           - Batch fetch all records
           - Process outgoing FKs for all records in batch
           - Batch process incoming FKs
        5. Continue until queue empty

        Args:
            table_name: Starting table name
            pk_value: Primary key value
            schema: Schema name (default: public)
            max_depth: Optional maximum traversal depth

        Returns:
            Set of all discovered RecordData objects

        Raises:
            RecordNotFoundError: If starting record doesn't exist
        """
        start_id = self._create_record_identifier(schema, table_name, (pk_value,))
        queue: deque[tuple[RecordIdentifier, int, bool]] = deque([(start_id, 0, True)])
        results: set[RecordData] = set()

        logger.info(f"Starting traversal from {start_id}")

        while queue:
            # Collect batch: all records at current depth (up to batch_size)
            current_depth = queue[0][1] if queue else 0
            batch: list[tuple[RecordIdentifier, bool]] = []

            while queue and len(batch) < self.fetch_batch_size:
                record_id, depth, follow_incoming_fks = queue.popleft()

                # If depth changed, put it back and process current batch
                if depth != current_depth:
                    queue.appendleft((record_id, depth, follow_incoming_fks))
                    break

                # Check depth limit
                if max_depth is not None and depth > max_depth:
                    logger.debug(
                        f"Skipping {record_id}: depth {depth} > max {max_depth}"
                    )
                    continue

                # Skip if already visited
                if self.visited.is_visited(record_id):
                    logger.debug(f"Skipping {record_id}: already visited")
                    continue

                # Mark as visited BEFORE fetching
                self.visited.mark_visited(record_id)
                batch.append((record_id, follow_incoming_fks))

            # Process batch
            if not batch:
                continue

            # Batch fetch all records
            record_ids = [rid for rid, _ in batch]
            try:
                fetched_records = self._fetch_records_batch(record_ids)
            except Exception as e:
                logger.error(f"Error batch fetching records: {e}")
                # Fall back to individual fetches
                fetched_records = {}
                for record_id in record_ids:
                    try:
                        fetched_records[record_id] = self._fetch_record(record_id)
                    except RecordNotFoundError:
                        logger.warning(f"Record not found: {record_id}")

            # Process each fetched record
            for record_id, _ in batch:
                if record_id not in fetched_records:
                    continue

                record_data = fetched_records[record_id]
                results.add(record_data)
                logger.debug(
                    f"Fetched {record_id} at depth {current_depth} ({len(results)} total)"
                )

                # Get table metadata
                table = self._get_table_metadata(
                    record_id.schema_name, record_id.table_name
                )

                # Traverse outgoing FKs (forward relationships)
                for fk in table.foreign_keys_outgoing:
                    target_id = self._resolve_foreign_key_target(record_data, fk)
                    if target_id:
                        # ALWAYS add dependency
                        record_data.dependencies.add(target_id)
                        logger.debug(
                            f"  -> Dependency: {record_data.identifier} depends on {target_id}"
                        )

                        # Only traverse if not visited
                        if not self.visited.is_visited(target_id):
                            follow_incoming = self.wide_mode
                            queue.append(
                                (target_id, current_depth + 1, follow_incoming)
                            )
                            logger.debug(f"  -> Following outgoing FK to {target_id}")

            # Process incoming FKs for batch (using batch lookup)
            # Group by FK to minimize queries
            incoming_fk_lookups: dict[Any, list[tuple[RecordIdentifier, bool]]] = {}
            for record_id, follow_incoming_fks in batch:
                if record_id not in fetched_records or not follow_incoming_fks:
                    continue

                table = self._get_table_metadata(
                    record_id.schema_name, record_id.table_name
                )

                for fk in table.foreign_keys_incoming:
                    # Skip self-referencing FKs in strict mode
                    if not self.wide_mode:
                        source_schema, source_table = self._parse_table_name(
                            fk.source_table
                        )
                        if (
                            source_schema == record_id.schema_name
                            and source_table == record_id.table_name
                        ):
                            logger.debug(
                                "  <- Skipping self-referencing FK (strict mode)"
                            )
                            continue

                    # Group records by FK for batch lookup
                    fk_key = (fk.source_table, fk.source_column)
                    if fk_key not in incoming_fk_lookups:
                        incoming_fk_lookups[fk_key] = []
                    incoming_fk_lookups[fk_key].append((record_id, follow_incoming_fks))

            # Batch process incoming FKs
            for (source_table, source_column), targets in incoming_fk_lookups.items():
                # Reconstruct FK object for batch lookup
                fk_obj = type(
                    "FK",
                    (),
                    {"source_table": source_table, "source_column": source_column},
                )()
                target_ids = [tid for tid, _ in targets]

                try:
                    referencing_map = self._find_referencing_records_batch(
                        target_ids, fk_obj
                    )

                    for target_id in target_ids:
                        source_records = referencing_map.get(target_id, [])
                        for source_id in source_records:
                            if not self.visited.is_visited(source_id):
                                queue.append((source_id, current_depth + 1, True))
                                logger.debug(
                                    f"  <- Following incoming FK from {source_id}"
                                )
                except Exception as e:
                    logger.error(f"Error in batch FK lookup: {e}")

        logger.info(f"Traversal complete: {len(results)} records found")
        return results

    def traverse_multiple(
        self,
        table_name: str,
        pk_values: list[Any],
        schema: str = "public",
        max_depth: int | None = None,
    ) -> set[RecordData]:
        """
        Traverse from multiple starting records using unified BFS.

        Optimizes multi-record traversal by batch-fetching all starting
        records and running a single BFS from all starting points.

        Args:
            table_name: Starting table name
            pk_values: List of primary key values
            schema: Schema name (default: public)
            max_depth: Optional maximum traversal depth

        Returns:
            Set of all discovered RecordData objects
        """
        # Edge case: empty pk_values
        if not pk_values:
            logger.info("No primary keys provided for traversal")
            return set()

        # Single PK: delegate to traverse() for simplicity
        if len(pk_values) == 1:
            return self.traverse(table_name, pk_values[0], schema, max_depth)

        logger.info(
            f"Starting batch traversal from {schema}.{table_name} "
            f"with {len(pk_values)} starting records"
        )

        results: set[RecordData] = set()

        # Step 1: Create RecordIdentifiers for all starting records
        start_ids: list[RecordIdentifier] = [
            self._create_record_identifier(schema, table_name, (pk,))
            for pk in pk_values
        ]

        # Step 2: Filter out already-visited starting records
        unvisited_start_ids: list[RecordIdentifier] = [
            rid for rid in start_ids if not self.visited.is_visited(rid)
        ]

        if not unvisited_start_ids:
            logger.info("All starting records already visited")
            return results

        # Step 3: Mark all starting records as visited BEFORE fetching
        for rid in unvisited_start_ids:
            self.visited.mark_visited(rid)

        # Step 4: Batch-fetch ALL starting records in one query
        try:
            fetched_starts = self._fetch_records_batch(unvisited_start_ids)
        except Exception as e:
            logger.error(f"Error batch-fetching starting records: {e}")
            # Fallback to individual fetches
            fetched_starts = {}
            for rid in unvisited_start_ids:
                try:
                    fetched_starts[rid] = self._fetch_record(rid)
                except RecordNotFoundError:
                    logger.warning(f"Starting record not found: {rid}")

        if not fetched_starts:
            logger.warning("No starting records found")
            return results

        logger.debug(
            f"Fetched {len(fetched_starts)}/{len(unvisited_start_ids)} starting records"
        )

        # Step 5: Initialize unified BFS queue with all starting records at depth 0
        queue: deque[tuple[RecordIdentifier, int, bool]] = deque()

        for record_id, record_data in fetched_starts.items():
            results.add(record_data)

            # Get table metadata and process outgoing FKs
            table = self._get_table_metadata(
                record_id.schema_name, record_id.table_name
            )

            for fk in table.foreign_keys_outgoing:
                target_id = self._resolve_foreign_key_target(record_data, fk)
                if target_id:
                    record_data.dependencies.add(target_id)
                    if not self.visited.is_visited(target_id):
                        follow_incoming = self.wide_mode
                        queue.append((target_id, 1, follow_incoming))

        # Step 6: Batch-process incoming FKs for all starting records
        self._batch_process_incoming_fks_for_records(
            fetched_starts, queue, current_depth=0
        )

        # Step 7: Run unified BFS (reuse logic from traverse())
        while queue:
            current_depth = queue[0][1] if queue else 0
            batch: list[tuple[RecordIdentifier, bool]] = []

            # Collect batch at current depth
            while queue and len(batch) < self.fetch_batch_size:
                record_id, depth, follow_incoming_fks = queue.popleft()

                if depth != current_depth:
                    queue.appendleft((record_id, depth, follow_incoming_fks))
                    break

                if max_depth is not None and depth > max_depth:
                    logger.debug(
                        f"Skipping {record_id}: depth {depth} > max {max_depth}"
                    )
                    continue

                if self.visited.is_visited(record_id):
                    logger.debug(f"Skipping {record_id}: already visited")
                    continue

                self.visited.mark_visited(record_id)
                batch.append((record_id, follow_incoming_fks))

            if not batch:
                continue

            # Batch fetch records
            record_ids = [rid for rid, _ in batch]
            try:
                fetched_records = self._fetch_records_batch(record_ids)
            except Exception as e:
                logger.error(f"Error batch fetching records: {e}")
                fetched_records = {}
                for record_id in record_ids:
                    try:
                        fetched_records[record_id] = self._fetch_record(record_id)
                    except RecordNotFoundError:
                        logger.warning(f"Record not found: {record_id}")

            # Process fetched records
            for record_id, _ in batch:
                if record_id not in fetched_records:
                    continue

                record_data = fetched_records[record_id]
                results.add(record_data)

                table = self._get_table_metadata(
                    record_id.schema_name, record_id.table_name
                )

                for fk in table.foreign_keys_outgoing:
                    target_id = self._resolve_foreign_key_target(record_data, fk)
                    if target_id:
                        record_data.dependencies.add(target_id)
                        if not self.visited.is_visited(target_id):
                            follow_incoming = self.wide_mode
                            queue.append(
                                (target_id, current_depth + 1, follow_incoming)
                            )

            # Process incoming FKs for batch
            batch_records = {
                rid: fetched_records[rid]
                for rid, follow in batch
                if rid in fetched_records and follow
            }
            self._batch_process_incoming_fks_for_records(
                batch_records, queue, current_depth
            )

        logger.info(
            f"Batch traversal complete: {len(results)} unique records found "
            f"from {len(pk_values)} starting points"
        )
        return results

    def _batch_process_incoming_fks_for_records(
        self,
        records: dict[RecordIdentifier, RecordData],
        queue: deque[tuple[RecordIdentifier, int, bool]],
        current_depth: int,
    ) -> None:
        """
        Process incoming FKs for multiple records in batch.

        Groups records by FK relationship for efficient batch lookups.

        Args:
            records: Map of record IDs to their data
            queue: BFS queue to append discovered records
            current_depth: Current traversal depth
        """
        if not records:
            return

        # Group by incoming FK for batch processing
        incoming_fk_lookups: dict[tuple[str, str], list[RecordIdentifier]] = {}

        for record_id in records:
            table = self._get_table_metadata(
                record_id.schema_name, record_id.table_name
            )

            for fk in table.foreign_keys_incoming:
                # Skip self-referencing FKs in strict mode
                if not self.wide_mode:
                    source_schema, source_table = self._parse_table_name(
                        fk.source_table
                    )
                    if (
                        source_schema == record_id.schema_name
                        and source_table == record_id.table_name
                    ):
                        continue

                fk_key = (fk.source_table, fk.source_column)
                if fk_key not in incoming_fk_lookups:
                    incoming_fk_lookups[fk_key] = []
                incoming_fk_lookups[fk_key].append(record_id)

        # Execute batch lookups
        for (source_table, source_column), target_ids in incoming_fk_lookups.items():
            fk_obj = type(
                "FK",
                (),
                {"source_table": source_table, "source_column": source_column},
            )()

            try:
                referencing_map = self._find_referencing_records_batch(
                    target_ids, fk_obj
                )

                for target_id in target_ids:
                    source_records = referencing_map.get(target_id, [])
                    for source_id in source_records:
                        if not self.visited.is_visited(source_id):
                            queue.append((source_id, current_depth + 1, True))
            except Exception as e:
                logger.error(f"Error in batch FK lookup for {source_table}: {e}")

    def _fetch_record(self, record_id: RecordIdentifier) -> RecordData:
        """
        Fetch a single record by primary key.

        Args:
            record_id: Record identifier

        Returns:
            RecordData with fetched data

        Raises:
            RecordNotFoundError: If record doesn't exist
        """
        table = self._get_table_metadata(record_id.schema_name, record_id.table_name)

        # Build WHERE clause for primary keys
        if not table.primary_keys:
            raise RecordNotFoundError(
                f"Table {record_id.schema_name}.{record_id.table_name} has no primary key"
            )

        where_parts = []
        params = []
        for pk_col, pk_val in zip(
            table.primary_keys, record_id.pk_values, strict=False
        ):
            where_parts.append(f'"{pk_col}" = %s')
            params.append(pk_val)

        # Apply timeframe filter if applicable
        timeframe_clause = ""
        if record_id.table_name in self.timeframe_filters:
            filter_config = self.timeframe_filters[record_id.table_name]
            timeframe_clause = f' AND "{filter_config.column_name}" BETWEEN %s AND %s'
            params.extend([filter_config.start_date, filter_config.end_date])

        query = f"""
            SELECT * FROM "{record_id.schema_name}"."{record_id.table_name}"
            WHERE {" AND ".join(where_parts)}{timeframe_clause}
        """

        with self.conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()

            if row is None:
                raise RecordNotFoundError(f"Record not found: {record_id}")

            # Convert row to dict
            columns = [desc[0] for desc in (cur.description or [])]
            data = dict(zip(columns, row, strict=False))

        return RecordData(identifier=record_id, data=data)

    def _fetch_records_batch(
        self, record_ids: list[RecordIdentifier]
    ) -> dict[RecordIdentifier, RecordData]:
        """
        Fetch multiple records in a single query using IN clause.
        Groups records by table for efficient batching.

        Args:
            record_ids: List of record identifiers to fetch

        Returns:
            Dictionary mapping RecordIdentifier to RecordData
        """
        if not record_ids:
            return {}

        results: dict[RecordIdentifier, RecordData] = {}

        # Group by (schema, table)
        by_table: dict[tuple[str, str], list[RecordIdentifier]] = {}
        for record_id in record_ids:
            key = (record_id.schema_name, record_id.table_name)
            by_table.setdefault(key, []).append(record_id)

        # Fetch each table's records in batch
        for (schema, table), table_record_ids in by_table.items():
            table_metadata = self._get_table_metadata(schema, table)

            if not table_metadata.primary_keys:
                logger.warning(f"Table {schema}.{table} has no primary key, skipping")
                continue

            # Build WHERE clause: WHERE id IN (1, 2, 3)
            pk_col = table_metadata.primary_keys[0]
            pk_values = [rid.pk_values[0] for rid in table_record_ids]
            placeholders = ", ".join(["%s"] * len(pk_values))

            # Apply timeframe filter if applicable
            timeframe_clause = ""
            params: list[Any] = pk_values.copy()

            if table in self.timeframe_filters:
                filter_config = self.timeframe_filters[table]
                timeframe_clause = (
                    f' AND "{filter_config.column_name}" BETWEEN %s AND %s'
                )
                params.extend([filter_config.start_date, filter_config.end_date])

            query = f"""
                SELECT * FROM "{schema}"."{table}"
                WHERE "{pk_col}" IN ({placeholders}){timeframe_clause}
            """

            with self.conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                columns = [desc[0] for desc in (cur.description or [])]

                for row in rows:
                    data = dict(zip(columns, row, strict=False))
                    pk_value = data[pk_col]
                    record_id = self._create_record_identifier(
                        schema, table, (pk_value,)
                    )
                    results[record_id] = RecordData(identifier=record_id, data=data)

        return results

    def _resolve_foreign_key_target(
        self, record: RecordData, fk: Any
    ) -> RecordIdentifier | None:
        """
        Extract FK value from record and create target RecordIdentifier.

        Args:
            record: Source record
            fk: ForeignKey object

        Returns:
            Target RecordIdentifier or None if FK is NULL
        """
        fk_value = record.data.get(fk.source_column)

        if fk_value is None:
            logger.debug(f"NULL FK: {record.identifier} -> {fk.target_table}")
            return None

        # Parse target table (may be schema.table format)
        schema, table = self._parse_table_name(fk.target_table)

        return self._create_record_identifier(schema, table, (fk_value,))

    def _find_referencing_records(
        self, target_id: RecordIdentifier, fk: Any
    ) -> list[RecordIdentifier]:
        """
        Find all records in source table that reference the target record.

        Args:
            target_id: Target record being referenced
            fk: ForeignKey object

        Returns:
            List of RecordIdentifiers for all referencing records
        """
        # Parse source table
        schema, table = self._parse_table_name(fk.source_table)

        # Get primary keys for source table
        source_table = self._get_table_metadata(schema, table)
        if not source_table.primary_keys:
            logger.warning(f"Table {schema}.{table} has no primary key, skipping")
            return []

        # Get the target PK value to match against
        self._get_table_metadata(target_id.schema_name, target_id.table_name)
        # Assuming single-column FK for now (multi-column FK support would need enhancement)
        if len(target_id.pk_values) != 1:
            logger.warning(
                f"Composite PK not fully supported for reverse FK: {target_id}"
            )
            target_pk_value = target_id.pk_values[0]
        else:
            target_pk_value = target_id.pk_values[0]

        # Build query
        pk_columns = ", ".join(f'"{pk}"' for pk in source_table.primary_keys)

        # Apply timeframe filter if applicable
        timeframe_clause = ""
        params: list[Any] = [target_pk_value]

        if table in self.timeframe_filters:
            filter_config = self.timeframe_filters[table]
            timeframe_clause = f' AND "{filter_config.column_name}" BETWEEN %s AND %s'
            params.extend([filter_config.start_date, filter_config.end_date])

        query = f"""
            SELECT {pk_columns}
            FROM "{schema}"."{table}"
            WHERE "{fk.source_column}" = %s{timeframe_clause}
        """

        # Debug logging for over-extraction investigation
        logger.debug(
            f"Finding records in {schema}.{table} where {fk.source_column} = {target_pk_value}"
        )

        results = []
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            for row in cur.fetchall():
                # row contains PK values (may be tuple for composite PKs)
                pk_values = row if isinstance(row, tuple) else (row,)
                record_id = self._create_record_identifier(schema, table, pk_values)
                results.append(record_id)

        if results:
            logger.debug(
                f"Found {len(results)} records in {schema}.{table} "
                f"referencing {target_id}: {[r.pk_values for r in results]}"
            )

        return results

    def _find_referencing_records_batch(
        self, target_ids: list[RecordIdentifier], fk: Any
    ) -> dict[RecordIdentifier, list[RecordIdentifier]]:
        """
        Find all records referencing multiple targets via single FK using IN clause.

        Args:
            target_ids: List of target record identifiers being referenced
            fk: ForeignKey object

        Returns:
            Dictionary mapping each target_id to list of RecordIdentifiers referencing it
        """
        if not target_ids:
            return {}

        # Parse source table
        schema, table = self._parse_table_name(fk.source_table)

        # Get primary keys for source table
        source_table = self._get_table_metadata(schema, table)
        if not source_table.primary_keys:
            logger.warning(f"Table {schema}.{table} has no primary key, skipping")
            return {}

        # Get target PK values
        target_pk_values = [tid.pk_values[0] for tid in target_ids]

        # Build query with IN clause
        pk_columns = ", ".join(f'"{pk}"' for pk in source_table.primary_keys)
        placeholders = ", ".join(["%s"] * len(target_pk_values))

        # Apply timeframe filter if applicable
        timeframe_clause = ""
        params: list[Any] = target_pk_values.copy()

        if table in self.timeframe_filters:
            filter_config = self.timeframe_filters[table]
            timeframe_clause = f' AND "{filter_config.column_name}" BETWEEN %s AND %s'
            params.extend([filter_config.start_date, filter_config.end_date])

        # Include FK column to map back to targets
        query = f"""
            SELECT {pk_columns}, "{fk.source_column}"
            FROM "{schema}"."{table}"
            WHERE "{fk.source_column}" IN ({placeholders}){timeframe_clause}
        """

        # Initialize results dict with empty lists for all targets
        results: dict[RecordIdentifier, list[RecordIdentifier]] = {
            tid: [] for tid in target_ids
        }

        with self.conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

            for row in rows:
                fk_value = row[-1]  # Last column is FK value
                pk_values = row[:-1]  # Rest are PK values

                source_id = self._create_record_identifier(
                    schema,
                    table,
                    (pk_values[0],) if len(pk_values) == 1 else tuple(pk_values),
                )

                # Map to correct target
                for target_id in target_ids:
                    if str(target_id.pk_values[0]) == str(fk_value):
                        results[target_id].append(source_id)
                        break

        return results

    def _get_table_metadata(self, schema: str, table: str) -> Table:
        """
        Get table metadata with caching.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            Table metadata
        """
        key = f"{schema}.{table}"
        if key not in self.table_cache:
            self.table_cache[key] = self.introspector.get_table_metadata(schema, table)
        return self.table_cache[key]

    def _create_record_identifier(
        self, schema: str, table: str, pk_values: tuple[Any, ...]
    ) -> RecordIdentifier:
        """
        Create RecordIdentifier with proper types.

        Args:
            schema: Schema name
            table: Table name
            pk_values: Tuple of primary key values

        Returns:
            RecordIdentifier
        """
        return RecordIdentifier(
            schema_name=schema, table_name=table, pk_values=pk_values
        )

    def _parse_table_name(self, full_name: str) -> tuple[str, str]:
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
