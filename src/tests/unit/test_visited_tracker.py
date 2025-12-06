"""Tests for visited record tracker."""

import pytest

from snippy.graph.visited_tracker import VisitedTracker
from snippy.graph.models import RecordIdentifier


class TestVisitedTracker:
    """Tests for VisitedTracker class."""

    def test_creation(self):
        """Test VisitedTracker creation."""
        tracker = VisitedTracker()

        assert tracker.count() == 0

    def test_mark_visited(self):
        """Test marking a record as visited."""
        tracker = VisitedTracker()
        record_id = RecordIdentifier("public", "users", {"id": 1})

        tracker.mark_visited(record_id)

        assert tracker.is_visited(record_id)
        assert tracker.count() == 1

    def test_is_visited_false(self):
        """Test is_visited returns False for unvisited record."""
        tracker = VisitedTracker()
        record_id = RecordIdentifier("public", "users", {"id": 1})

        assert not tracker.is_visited(record_id)

    def test_multiple_records(self):
        """Test tracking multiple different records."""
        tracker = VisitedTracker()
        id1 = RecordIdentifier("public", "users", {"id": 1})
        id2 = RecordIdentifier("public", "users", {"id": 2})
        id3 = RecordIdentifier("public", "orders", {"id": 1})

        tracker.mark_visited(id1)
        tracker.mark_visited(id2)
        tracker.mark_visited(id3)

        assert tracker.is_visited(id1)
        assert tracker.is_visited(id2)
        assert tracker.is_visited(id3)
        assert tracker.count() == 3

    def test_same_record_twice(self):
        """Test marking same record visited twice."""
        tracker = VisitedTracker()
        record_id = RecordIdentifier("public", "users", {"id": 1})

        tracker.mark_visited(record_id)
        tracker.mark_visited(record_id)  # Mark again

        assert tracker.count() == 1  # Should still be 1

    def test_reset(self):
        """Test reset clears all visited records."""
        tracker = VisitedTracker()
        id1 = RecordIdentifier("public", "users", {"id": 1})
        id2 = RecordIdentifier("public", "orders", {"id": 1})

        tracker.mark_visited(id1)
        tracker.mark_visited(id2)
        assert tracker.count() == 2

        tracker.reset()

        assert tracker.count() == 0
        assert not tracker.is_visited(id1)
        assert not tracker.is_visited(id2)

    def test_composite_primary_key(self):
        """Test tracking record with composite primary key."""
        tracker = VisitedTracker()
        record_id = RecordIdentifier("public", "user_groups", {"user_id": 1, "group_id": 2})

        tracker.mark_visited(record_id)

        assert tracker.is_visited(record_id)
        assert tracker.count() == 1

    def test_different_tables_same_pk(self):
        """Test records from different tables with same PK value are tracked separately."""
        tracker = VisitedTracker()
        users_id = RecordIdentifier("public", "users", {"id": 1})
        orders_id = RecordIdentifier("public", "orders", {"id": 1})

        tracker.mark_visited(users_id)

        assert tracker.is_visited(users_id)
        assert not tracker.is_visited(orders_id)  # Different table
        assert tracker.count() == 1
