"""Tests for traverser progress callback functionality."""

from __future__ import annotations

from unittest.mock import MagicMock

from pgslice.graph.models import RecordData
from pgslice.graph.traverser import RelationshipTraverser


class TestProgressCallback:
    """Tests for progress callback parameter and invocation."""

    def test_traverser_accepts_progress_callback(self) -> None:
        """Should accept progress_callback parameter without errors."""
        mock_conn = MagicMock()
        mock_introspector = MagicMock()
        mock_visited = MagicMock()
        mock_callback = MagicMock()

        traverser = RelationshipTraverser(
            mock_conn,
            mock_introspector,
            mock_visited,
            progress_callback=mock_callback,
        )

        assert traverser.progress_callback == mock_callback

    def test_progress_callback_none_does_not_error(self) -> None:
        """Should work correctly when progress_callback is None."""
        mock_conn = MagicMock()
        mock_introspector = MagicMock()
        mock_visited = MagicMock()

        # Should not raise any errors
        traverser = RelationshipTraverser(
            mock_conn,
            mock_introspector,
            mock_visited,
            progress_callback=None,
        )

        assert traverser.progress_callback is None

    def test_progress_callback_invoked_per_record(self, mocker: MagicMock) -> None:
        """Should invoke callback after each record is fetched."""
        mock_conn = MagicMock()
        mock_introspector = MagicMock()
        mock_visited = MagicMock()
        mock_callback = MagicMock()

        # Mock table metadata
        mock_table = MagicMock()
        mock_table.primary_keys = ["id"]
        mock_table.foreign_keys_outgoing = []
        mock_table.foreign_keys_incoming = []
        mock_introspector.get_table_metadata.return_value = mock_table

        # Mock visited tracker
        mock_visited.is_visited.return_value = False
        mock_visited.mark_visited.return_value = None

        # Mock fetch_record to return a valid record
        def mock_fetch(record_id):
            return RecordData(
                identifier=record_id,
                data={"id": record_id.pk_values[0]},
            )

        traverser = RelationshipTraverser(
            mock_conn,
            mock_introspector,
            mock_visited,
            progress_callback=mock_callback,
        )

        # Patch _fetch_record method
        mocker.patch.object(traverser, "_fetch_record", side_effect=mock_fetch)

        # Traverse a single record
        traverser.traverse("users", "1", "public", max_depth=0)

        # Callback should be invoked at least once
        assert mock_callback.called
        mock_callback.assert_called_with(1)

    def test_progress_callback_receives_correct_count(self, mocker: MagicMock) -> None:
        """Should pass accurate record count to callback."""
        mock_conn = MagicMock()
        mock_introspector = MagicMock()
        mock_visited = MagicMock()
        mock_callback = MagicMock()

        # Mock table metadata with no relationships
        mock_table = MagicMock()
        mock_table.primary_keys = ["id"]
        mock_table.foreign_keys_outgoing = []
        mock_table.foreign_keys_incoming = []
        mock_introspector.get_table_metadata.return_value = mock_table

        # Track visited records
        visited_records = set()

        def is_visited(record_id):
            return record_id in visited_records

        def mark_visited(record_id):
            visited_records.add(record_id)

        mock_visited.is_visited.side_effect = is_visited
        mock_visited.mark_visited.side_effect = mark_visited

        # Mock fetch_record
        def mock_fetch(record_id):
            return RecordData(
                identifier=record_id,
                data={"id": record_id.pk_values[0]},
            )

        traverser = RelationshipTraverser(
            mock_conn,
            mock_introspector,
            mock_visited,
            progress_callback=mock_callback,
        )

        mocker.patch.object(traverser, "_fetch_record", side_effect=mock_fetch)

        # Traverse
        traverser.traverse("users", "1", "public", max_depth=0)

        # Should be called with count 1 (only the starting record)
        mock_callback.assert_called_with(1)

    def test_traverse_multiple_updates_progress(self, mocker: MagicMock) -> None:
        """Should invoke callback when traversing multiple starting records."""
        mock_conn = MagicMock()
        mock_introspector = MagicMock()
        mock_visited = MagicMock()
        mock_callback = MagicMock()

        # Mock table metadata
        mock_table = MagicMock()
        mock_table.primary_keys = ["id"]
        mock_table.foreign_keys_outgoing = []
        mock_table.foreign_keys_incoming = []
        mock_introspector.get_table_metadata.return_value = mock_table

        # Track visited records to avoid duplicates
        visited_records = set()

        def is_visited(record_id):
            return record_id in visited_records

        def mark_visited(record_id):
            visited_records.add(record_id)

        mock_visited.is_visited.side_effect = is_visited
        mock_visited.mark_visited.side_effect = mark_visited

        # Mock fetch_record
        def mock_fetch(record_id):
            return RecordData(
                identifier=record_id,
                data={"id": record_id.pk_values[0]},
            )

        traverser = RelationshipTraverser(
            mock_conn,
            mock_introspector,
            mock_visited,
            progress_callback=mock_callback,
        )

        mocker.patch.object(traverser, "_fetch_record", side_effect=mock_fetch)

        # Traverse multiple records
        traverser.traverse_multiple("users", ["1", "2", "3"], "public", max_depth=0)

        # Should be called multiple times (once per record + final callback)
        assert mock_callback.call_count >= 3
        # Final call should have count of 3 unique records
        final_call_arg = mock_callback.call_args[0][0]
        assert final_call_arg == 3
