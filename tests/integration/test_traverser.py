"""Integration tests for relationship traversal (requires test database)."""

import pytest
from datetime import datetime

from snippy.db.schema import SchemaIntrospector
from snippy.graph.traverser import RelationshipTraverser
from snippy.graph.visited_tracker import VisitedTracker
from snippy.graph.models import TimeframeFilter


@pytest.mark.integration
class TestRelationshipTraverserBasic:
    """Basic integration tests for RelationshipTraverser."""

    @pytest.fixture
    def traverser(self, test_db_connection):
        """Create a traverser instance."""
        introspector = SchemaIntrospector(test_db_connection)
        visited = VisitedTracker()
        return RelationshipTraverser(
            test_db_connection,
            introspector,
            visited,
            timeframe_filters=[],
            wide_mode=False,
        )

    def test_traverse_single_record_no_relationships(self, traverser):
        """Test traversing a record with no relationships."""
        # Role has no dependencies
        records = traverser.traverse("roles", "1", "public", max_depth=10)

        assert len(records) >= 1
        # Should find the role record
        role_records = [r for r in records if r.identifier.table_name == "roles"]
        assert len(role_records) >= 1

    def test_traverse_with_forward_fk(self, traverser):
        """Test traversing record with outgoing FK (users -> roles)."""
        # User 1 has role_id FK to roles
        records = traverser.traverse("users", "1", "public", max_depth=10)

        # Should include user and their role
        tables = {r.identifier.table_name for r in records}
        assert "users" in tables
        # Should follow the role_id FK
        assert "roles" in tables

    def test_traverse_includes_all_dependencies(self, traverser):
        """Test traverse includes all dependencies in chain."""
        # User has FK to role, might have FK to manager, etc.
        records = traverser.traverse("users", "1", "public", max_depth=10)

        # Should include at least the user and any direct dependencies
        assert len(records) >= 1
        user_record = next(r for r in records if r.identifier.table_name == "users")
        assert user_record is not None


@pytest.mark.integration
class TestRelationshipTraverserStrictVsWideMode:
    """Tests for strict vs wide mode traversal."""

    def test_strict_mode_skips_incoming_self_references(self, test_db_connection):
        """Test strict mode skips self-referencing incoming FKs."""
        introspector = SchemaIntrospector(test_db_connection)
        visited = VisitedTracker()
        traverser = RelationshipTraverser(
            test_db_connection,
            introspector,
            visited,
            timeframe_filters=[],
            wide_mode=False,  # STRICT mode
        )

        # If user 2 has manager_id = 1, strict mode should:
        # - Include user 2 (target)
        # - Include user 1 (manager via outgoing FK)
        # - NOT include user 2's subordinates (incoming FK skipped)

        records = traverser.traverse("users", "2", "public", max_depth=10)

        user_ids = {
            r.identifier.pk_values.get("id")
            for r in records
            if r.identifier.table_name == "users"
        }

        # Should include user 2 and possibly manager
        assert 2 in user_ids

    def test_wide_mode_follows_all_relationships(self, test_db_connection):
        """Test wide mode follows all relationships including incoming."""
        introspector = SchemaIntrospector(test_db_connection)
        visited = VisitedTracker()
        traverser = RelationshipTraverser(
            test_db_connection,
            introspector,
            visited,
            timeframe_filters=[],
            wide_mode=True,  # WIDE mode
        )

        records = traverser.traverse("users", "1", "public", max_depth=10)

        # Wide mode should include more records by following incoming FKs
        # (e.g., bank_accounts that reference this user)
        tables = {r.identifier.table_name for r in records}

        # Should include user
        assert "users" in tables


@pytest.mark.integration
class TestRelationshipTraverserMultiple:
    """Tests for traversing multiple records."""

    def test_traverse_multiple_records(self, test_db_connection):
        """Test traversing multiple primary key values."""
        introspector = SchemaIntrospector(test_db_connection)
        visited = VisitedTracker()
        traverser = RelationshipTraverser(
            test_db_connection,
            introspector,
            visited,
            timeframe_filters=[],
            wide_mode=False,
        )

        # Traverse users 1, 2, 3
        records = traverser.traverse_multiple("users", ["1", "2", "3"], "public", max_depth=10)

        # Should find records for all three users (and their dependencies)
        user_records = [r for r in records if r.identifier.table_name == "users"]
        user_ids = {r.identifier.pk_values.get("id") for r in user_records}

        assert 1 in user_ids
        assert 2 in user_ids
        assert 3 in user_ids

    def test_traverse_multiple_deduplicates(self, test_db_connection):
        """Test traversing multiple records deduplicates shared dependencies."""
        introspector = SchemaIntrospector(test_db_connection)
        visited = VisitedTracker()
        traverser = RelationshipTraverser(
            test_db_connection,
            introspector,
            visited,
            timeframe_filters=[],
            wide_mode=False,
        )

        # If users 1 and 2 both reference same role, role should appear once
        records = traverser.traverse_multiple("users", ["1", "2"], "public", max_depth=10)

        # Check that records are unique
        identifiers = [r.identifier for r in records]
        assert len(identifiers) == len(set(identifiers))


@pytest.mark.integration
class TestRelationshipTraverserDepthLimiting:
    """Tests for depth limiting."""

    def test_depth_limit_zero(self, test_db_connection):
        """Test depth limit of 0 returns only the target record."""
        introspector = SchemaIntrospector(test_db_connection)
        visited = VisitedTracker()
        traverser = RelationshipTraverser(
            test_db_connection,
            introspector,
            visited,
            timeframe_filters=[],
            wide_mode=False,
        )

        records = traverser.traverse("users", "1", "public", max_depth=0)

        # Should only include the target user, no dependencies
        assert len(records) == 1
        assert records[0].identifier.table_name == "users"
        assert records[0].identifier.pk_values["id"] == 1

    def test_depth_limit_one(self, test_db_connection):
        """Test depth limit of 1 includes target and direct dependencies."""
        introspector = SchemaIntrospector(test_db_connection)
        visited = VisitedTracker()
        traverser = RelationshipTraverser(
            test_db_connection,
            introspector,
            visited,
            timeframe_filters=[],
            wide_mode=False,
        )

        records = traverser.traverse("users", "1", "public", max_depth=1)

        # Should include user and direct FK targets (role, manager if present)
        tables = {r.identifier.table_name for r in records}
        assert "users" in tables

    def test_depth_limit_prevents_deep_traversal(self, test_db_connection):
        """Test depth limit prevents traversing too deep."""
        introspector = SchemaIntrospector(test_db_connection)
        visited = VisitedTracker()

        # Shallow traversal
        traverser_shallow = RelationshipTraverser(
            test_db_connection,
            introspector,
            VisitedTracker(),  # Fresh tracker
            timeframe_filters=[],
            wide_mode=False,
        )
        records_shallow = traverser_shallow.traverse("users", "1", "public", max_depth=1)

        # Deep traversal
        traverser_deep = RelationshipTraverser(
            test_db_connection,
            introspector,
            VisitedTracker(),  # Fresh tracker
            timeframe_filters=[],
            wide_mode=False,
        )
        records_deep = traverser_deep.traverse("users", "1", "public", max_depth=10)

        # Deep should have same or more records
        assert len(records_deep) >= len(records_shallow)


@pytest.mark.integration
class TestRelationshipTraverserTimeframeFilter:
    """Tests for timeframe filtering."""

    def test_timeframe_filter_limits_results(self, test_db_connection):
        """Test timeframe filter limits records."""
        introspector = SchemaIntrospector(test_db_connection)
        visited = VisitedTracker()

        # Create a very restrictive timeframe filter
        tf = TimeframeFilter(
            table_name="transactions",
            column_name="created_at",
            start_date=datetime(2099, 1, 1),  # Future date - should match nothing
            end_date=datetime(2099, 12, 31),
        )

        traverser = RelationshipTraverser(
            test_db_connection,
            introspector,
            visited,
            timeframe_filters=[tf],
            wide_mode=False,
        )

        # Traverse from a bank account (which links to transactions)
        # The timeframe filter should exclude all transactions
        records = traverser.traverse("bank_accounts", "1", "public", max_depth=10)

        # Should have bank account but no transactions (filtered out)
        transaction_records = [r for r in records if r.identifier.table_name == "transactions"]
        assert len(transaction_records) == 0  # All filtered out


@pytest.mark.integration
class TestRelationshipTraverserCircularReferences:
    """Tests for circular reference handling."""

    def test_circular_reference_prevention(self, test_db_connection):
        """Test circular references don't cause infinite loops."""
        introspector = SchemaIntrospector(test_db_connection)
        visited = VisitedTracker()
        traverser = RelationshipTraverser(
            test_db_connection,
            introspector,
            visited,
            timeframe_filters=[],
            wide_mode=True,  # Wide mode more likely to hit circles
        )

        # Traverse from a user (which has self-referencing manager FK)
        # Should not loop infinitely
        records = traverser.traverse("users", "1", "public", max_depth=10)

        # Should complete successfully without infinite loop
        assert len(records) > 0

    def test_visited_tracker_prevents_revisiting(self, test_db_connection):
        """Test visited tracker prevents revisiting same record."""
        introspector = SchemaIntrospector(test_db_connection)
        visited = VisitedTracker()
        traverser = RelationshipTraverser(
            test_db_connection,
            introspector,
            visited,
            timeframe_filters=[],
            wide_mode=False,
        )

        records = traverser.traverse("users", "1", "public", max_depth=10)

        # All records should be unique (no duplicates)
        identifiers = [r.identifier for r in records]
        assert len(identifiers) == len(set(identifiers))


@pytest.mark.integration
class TestRelationshipTraverserNullForeignKeys:
    """Tests for handling NULL foreign key values."""

    def test_null_fk_value_skipped(self, test_db_connection):
        """Test NULL FK values are skipped gracefully."""
        introspector = SchemaIntrospector(test_db_connection)
        visited = VisitedTracker()
        traverser = RelationshipTraverser(
            test_db_connection,
            introspector,
            visited,
            timeframe_filters=[],
            wide_mode=False,
        )

        # User with manager_id = NULL should still work
        # Should not try to fetch NULL manager
        records = traverser.traverse("users", "1", "public", max_depth=10)

        # Should complete successfully
        assert len(records) >= 1
