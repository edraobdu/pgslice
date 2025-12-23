"""Topological sorting of records based on foreign key dependencies."""

from __future__ import annotations

from collections import defaultdict, deque

from ..graph.models import RecordData, RecordIdentifier
from ..utils.exceptions import CircularDependencyError
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class DependencySorter:
    """
    Topologically sorts records so dependencies come before dependents.

    Uses Kahn's algorithm for topological sorting to ensure that
    INSERT statements are generated in an order that respects
    foreign key constraints.
    """

    def sort(self, records: set[RecordData]) -> list[RecordData]:
        """
        Sort records in dependency order using Kahn's algorithm.

        Algorithm:
        1. Build adjacency graph from dependencies
        2. Calculate in-degree for each node
        3. Start with nodes having in-degree 0
        4. Process nodes in order, reducing in-degree of neighbors
        5. Detect cycles if not all nodes processed

        Args:
            records: Set of RecordData to sort

        Returns:
            List of RecordData in dependency order (dependencies first)

        Raises:
            CircularDependencyError: If circular dependencies detected
        """
        if not records:
            return []

        logger.info(f"Sorting {len(records)} records by dependencies")

        # Build graph structures
        graph: dict[RecordIdentifier, set[RecordIdentifier]] = defaultdict(set)
        in_degree: dict[RecordIdentifier, int] = defaultdict(int)
        record_map: dict[RecordIdentifier, RecordData] = {}

        # Initialize - all records start with in-degree 0
        for record in records:
            record_map[record.identifier] = record
            if record.identifier not in in_degree:
                in_degree[record.identifier] = 0

        # Build edges: dependency -> dependent
        # If A depends on B, then B -> A (B must come before A)
        for record in records:
            for dep in record.dependencies:
                # Only consider dependencies that are in our record set
                if dep in record_map:
                    graph[dep].add(record.identifier)
                    in_degree[record.identifier] += 1

        logger.debug(f"Built dependency graph with {len(graph)} nodes")

        # Kahn's algorithm: Start with nodes having no dependencies
        queue: deque[RecordIdentifier] = deque(
            [node for node in record_map if in_degree[node] == 0]
        )

        sorted_records: list[RecordData] = []
        processed_count = 0

        while queue:
            # Get a node with no incoming edges
            current = queue.popleft()
            sorted_records.append(record_map[current])
            processed_count += 1

            # For each neighbor, reduce in-degree
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check for cycles
        if processed_count != len(records):
            # Find nodes that weren't processed (part of cycle)
            unprocessed = set(record_map.keys()) - {
                r.identifier for r in sorted_records
            }
            logger.error(
                f"Circular dependency detected involving {len(unprocessed)} records"
            )

            # Log some examples of unprocessed records
            examples = list(unprocessed)[:5]
            logger.error(f"Examples: {examples}")

            raise CircularDependencyError(
                f"Circular dependency detected involving {len(unprocessed)} records. "
                f"Examples: {examples}"
            )

        logger.info(f"Successfully sorted {len(sorted_records)} records")
        return sorted_records

    def analyze_dependencies(self, records: set[RecordData]) -> dict[str, int | float]:
        """
        Analyze dependency statistics.

        Args:
            records: Set of RecordData

        Returns:
            Dictionary with statistics:
            - total_records: Total number of records
            - records_with_deps: Records that have dependencies
            - max_dependencies: Maximum dependencies for any record
            - avg_dependencies: Average dependencies per record
        """
        if not records:
            return {
                "total_records": 0,
                "records_with_deps": 0,
                "max_dependencies": 0,
                "avg_dependencies": 0.0,
            }

        total_deps = 0
        max_deps = 0
        records_with_deps = 0

        for record in records:
            dep_count = len(record.dependencies)
            if dep_count > 0:
                records_with_deps += 1
            total_deps += dep_count
            max_deps = max(max_deps, dep_count)

        return {
            "total_records": len(records),
            "records_with_deps": records_with_deps,
            "max_dependencies": max_deps,
            "avg_dependencies": total_deps / len(records),
        }
