"""Tests for pgslice.graph.visited_tracker module."""

from __future__ import annotations

import pytest

from pgslice.graph.models import RecordIdentifier
from pgslice.graph.visited_tracker import VisitedTracker


class TestVisitedTracker:
    """Tests for VisitedTracker class."""

    @pytest.fixture
    def tracker(self) -> VisitedTracker:
        """Provide a fresh VisitedTracker instance."""
        return VisitedTracker()

    @pytest.fixture
    def record_id(self) -> RecordIdentifier:
        """Provide a sample RecordIdentifier."""
        return RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )

    @pytest.fixture
    def another_record_id(self) -> RecordIdentifier:
        """Provide another sample RecordIdentifier."""
        return RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(2,),
        )


class TestIsVisited(TestVisitedTracker):
    """Tests for is_visited method."""

    def test_new_record_is_not_visited(
        self, tracker: VisitedTracker, record_id: RecordIdentifier
    ) -> None:
        """New records should not be visited."""
        assert tracker.is_visited(record_id) is False

    def test_marked_record_is_visited(
        self, tracker: VisitedTracker, record_id: RecordIdentifier
    ) -> None:
        """Marked records should be visited."""
        tracker.mark_visited(record_id)
        assert tracker.is_visited(record_id) is True

    def test_different_record_not_affected(
        self,
        tracker: VisitedTracker,
        record_id: RecordIdentifier,
        another_record_id: RecordIdentifier,
    ) -> None:
        """Marking one record should not affect others."""
        tracker.mark_visited(record_id)
        assert tracker.is_visited(another_record_id) is False


class TestMarkVisited(TestVisitedTracker):
    """Tests for mark_visited method."""

    def test_mark_single_record(
        self, tracker: VisitedTracker, record_id: RecordIdentifier
    ) -> None:
        """Can mark a single record as visited."""
        tracker.mark_visited(record_id)
        assert tracker.is_visited(record_id) is True

    def test_mark_multiple_records(
        self,
        tracker: VisitedTracker,
        record_id: RecordIdentifier,
        another_record_id: RecordIdentifier,
    ) -> None:
        """Can mark multiple records as visited."""
        tracker.mark_visited(record_id)
        tracker.mark_visited(another_record_id)
        assert tracker.is_visited(record_id) is True
        assert tracker.is_visited(another_record_id) is True

    def test_marking_twice_is_idempotent(
        self, tracker: VisitedTracker, record_id: RecordIdentifier
    ) -> None:
        """Marking the same record twice should not cause issues."""
        tracker.mark_visited(record_id)
        tracker.mark_visited(record_id)
        assert tracker.is_visited(record_id) is True
        assert tracker.get_visited_count() == 1


class TestReset(TestVisitedTracker):
    """Tests for reset method."""

    def test_reset_clears_all_visited(
        self,
        tracker: VisitedTracker,
        record_id: RecordIdentifier,
        another_record_id: RecordIdentifier,
    ) -> None:
        """Reset should clear all visited records."""
        tracker.mark_visited(record_id)
        tracker.mark_visited(another_record_id)
        assert tracker.get_visited_count() == 2

        tracker.reset()

        assert tracker.is_visited(record_id) is False
        assert tracker.is_visited(another_record_id) is False
        assert tracker.get_visited_count() == 0

    def test_reset_empty_tracker(self, tracker: VisitedTracker) -> None:
        """Reset on empty tracker should not raise."""
        tracker.reset()
        assert tracker.get_visited_count() == 0


class TestGetVisitedCount(TestVisitedTracker):
    """Tests for get_visited_count method."""

    def test_empty_tracker_count_is_zero(self, tracker: VisitedTracker) -> None:
        """Empty tracker should have count of 0."""
        assert tracker.get_visited_count() == 0

    def test_count_after_one_visit(
        self, tracker: VisitedTracker, record_id: RecordIdentifier
    ) -> None:
        """Count should be 1 after one visit."""
        tracker.mark_visited(record_id)
        assert tracker.get_visited_count() == 1

    def test_count_after_multiple_visits(self, tracker: VisitedTracker) -> None:
        """Count should reflect all unique visits."""
        for i in range(5):
            rid = RecordIdentifier(
                table_name="users",
                schema_name="public",
                pk_values=(i,),
            )
            tracker.mark_visited(rid)
        assert tracker.get_visited_count() == 5

    def test_count_does_not_include_duplicates(
        self, tracker: VisitedTracker, record_id: RecordIdentifier
    ) -> None:
        """Count should not include duplicates."""
        tracker.mark_visited(record_id)
        tracker.mark_visited(record_id)
        tracker.mark_visited(record_id)
        assert tracker.get_visited_count() == 1


class TestGetVisitedRecords(TestVisitedTracker):
    """Tests for get_visited_records method."""

    def test_empty_tracker_returns_empty_set(self, tracker: VisitedTracker) -> None:
        """Empty tracker should return empty set."""
        records = tracker.get_visited_records()
        assert records == set()
        assert isinstance(records, set)

    def test_returns_all_visited_records(
        self,
        tracker: VisitedTracker,
        record_id: RecordIdentifier,
        another_record_id: RecordIdentifier,
    ) -> None:
        """Should return all visited records."""
        tracker.mark_visited(record_id)
        tracker.mark_visited(another_record_id)

        records = tracker.get_visited_records()
        assert record_id in records
        assert another_record_id in records
        assert len(records) == 2

    def test_returns_copy_not_reference(
        self, tracker: VisitedTracker, record_id: RecordIdentifier
    ) -> None:
        """Should return a copy, not a reference to internal set."""
        tracker.mark_visited(record_id)
        records = tracker.get_visited_records()

        # Modify the returned set
        new_id = RecordIdentifier(
            table_name="test",
            schema_name="public",
            pk_values=(999,),
        )
        records.add(new_id)

        # Original should not be affected
        assert new_id not in tracker.get_visited_records()
        assert tracker.get_visited_count() == 1


class TestVisitedTrackerIntegration:
    """Integration tests for VisitedTracker."""

    def test_track_records_from_multiple_tables(self) -> None:
        """Should track records from multiple tables correctly."""
        tracker = VisitedTracker()

        user_id = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        order_id = RecordIdentifier(
            table_name="orders",
            schema_name="public",
            pk_values=(100,),
        )
        product_id = RecordIdentifier(
            table_name="products",
            schema_name="public",
            pk_values=(50,),
        )

        tracker.mark_visited(user_id)
        tracker.mark_visited(order_id)
        tracker.mark_visited(product_id)

        assert tracker.is_visited(user_id)
        assert tracker.is_visited(order_id)
        assert tracker.is_visited(product_id)
        assert tracker.get_visited_count() == 3

    def test_track_records_from_different_schemas(self) -> None:
        """Should track records from different schemas correctly."""
        tracker = VisitedTracker()

        public_user = RecordIdentifier(
            table_name="users",
            schema_name="public",
            pk_values=(1,),
        )
        private_user = RecordIdentifier(
            table_name="users",
            schema_name="private",
            pk_values=(1,),
        )

        tracker.mark_visited(public_user)

        assert tracker.is_visited(public_user)
        assert not tracker.is_visited(private_user)  # Different schema

    def test_composite_primary_keys(self) -> None:
        """Should handle composite primary keys correctly."""
        tracker = VisitedTracker()

        composite_id_1 = RecordIdentifier(
            table_name="order_items",
            schema_name="public",
            pk_values=(1, 100),
        )
        composite_id_2 = RecordIdentifier(
            table_name="order_items",
            schema_name="public",
            pk_values=(1, 101),
        )
        composite_id_same = RecordIdentifier(
            table_name="order_items",
            schema_name="public",
            pk_values=(1, 100),
        )

        tracker.mark_visited(composite_id_1)

        assert tracker.is_visited(composite_id_1)
        assert tracker.is_visited(composite_id_same)  # Same composite key
        assert not tracker.is_visited(composite_id_2)  # Different second part
