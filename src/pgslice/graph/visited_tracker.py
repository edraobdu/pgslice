"""Track visited records to prevent circular traversal."""

from __future__ import annotations

from ..graph.models import RecordIdentifier


class VisitedTracker:
    """Tracks visited records to prevent infinite loops in circular relationships."""

    def __init__(self) -> None:
        """Initialize empty visited set."""
        self._visited: set[RecordIdentifier] = set()

    def is_visited(self, record_id: RecordIdentifier) -> bool:
        """
        Check if a record has been visited.

        Args:
            record_id: Record identifier to check

        Returns:
            True if record has been visited
        """
        return record_id in self._visited

    def mark_visited(self, record_id: RecordIdentifier) -> None:
        """
        Mark a record as visited.

        Args:
            record_id: Record identifier to mark as visited
        """
        self._visited.add(record_id)

    def reset(self) -> None:
        """Clear all visited records."""
        self._visited.clear()

    def get_visited_count(self) -> int:
        """
        Get the number of visited records.

        Returns:
            Count of visited records
        """
        return len(self._visited)

    def get_visited_records(self) -> set[RecordIdentifier]:
        """
        Get all visited record identifiers.

        Returns:
            Set of all visited record identifiers
        """
        return self._visited.copy()
