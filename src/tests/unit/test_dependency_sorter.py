"""Tests for dependency sorting using topological sort."""

import pytest

from snippy.dumper.dependency_sorter import DependencySorter
from snippy.graph.models import RecordIdentifier, RecordData
from snippy.utils.exceptions import CircularDependencyError


class TestDependencySorter:
    """Tests for DependencySorter class."""

    def test_empty_records(self):
        """Test sorting empty list returns empty list."""
        sorter = DependencySorter()

        result = sorter.sort([])

        assert result == []

    def test_single_record_no_dependencies(self):
        """Test sorting single record with no dependencies."""
        sorter = DependencySorter()
        record = RecordData(
            identifier=RecordIdentifier("public", "roles", {"id": 1}),
            data={"id": 1, "name": "admin"},
            dependencies=[],
        )

        result = sorter.sort([record])

        assert len(result) == 1
        assert result[0] == record

    def test_linear_dependency_chain(self):
        """Test A depends on B, B depends on C => order: C, B, A."""
        sorter = DependencySorter()

        c = RecordData(
            identifier=RecordIdentifier("public", "c", {"id": 1}),
            data={"id": 1},
            dependencies=[],
        )
        b = RecordData(
            identifier=RecordIdentifier("public", "b", {"id": 1}),
            data={"id": 1, "c_id": 1},
            dependencies=[c.identifier],
        )
        a = RecordData(
            identifier=RecordIdentifier("public", "a", {"id": 1}),
            data={"id": 1, "b_id": 1},
            dependencies=[b.identifier],
        )

        result = sorter.sort([a, b, c])

        assert len(result) == 3
        assert result[0].identifier.table_name == "c"
        assert result[1].identifier.table_name == "b"
        assert result[2].identifier.table_name == "a"

    def test_multiple_dependencies(self):
        """Test record with multiple dependencies."""
        sorter = DependencySorter()

        role = RecordData(
            identifier=RecordIdentifier("public", "roles", {"id": 1}),
            data={"id": 1, "name": "admin"},
            dependencies=[],
        )
        group = RecordData(
            identifier=RecordIdentifier("public", "groups", {"id": 1}),
            data={"id": 1, "name": "engineering"},
            dependencies=[],
        )
        user = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 1}),
            data={"id": 1, "role_id": 1, "group_id": 1},
            dependencies=[role.identifier, group.identifier],
        )

        result = sorter.sort([user, role, group])

        assert len(result) == 3
        # role and group must come before user
        user_index = next(i for i, r in enumerate(result) if r.identifier.table_name == "users")
        role_index = next(i for i, r in enumerate(result) if r.identifier.table_name == "roles")
        group_index = next(i for i, r in enumerate(result) if r.identifier.table_name == "groups")

        assert role_index < user_index
        assert group_index < user_index

    def test_complex_dependency_graph(self):
        """Test complex multi-level dependency graph."""
        sorter = DependencySorter()

        # Create a graph:
        # roles (no deps)
        # groups (no deps)
        # users -> roles
        # bank_accounts -> users
        # transactions -> bank_accounts

        role = RecordData(
            identifier=RecordIdentifier("public", "roles", {"id": 1}),
            data={"id": 1},
            dependencies=[],
        )
        group = RecordData(
            identifier=RecordIdentifier("public", "groups", {"id": 1}),
            data={"id": 1},
            dependencies=[],
        )
        user = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 1}),
            data={"id": 1, "role_id": 1},
            dependencies=[role.identifier],
        )
        account = RecordData(
            identifier=RecordIdentifier("public", "bank_accounts", {"id": 1}),
            data={"id": 1, "user_id": 1},
            dependencies=[user.identifier],
        )
        transaction = RecordData(
            identifier=RecordIdentifier("public", "transactions", {"id": 1}),
            data={"id": 1, "bank_account_id": 1},
            dependencies=[account.identifier],
        )

        result = sorter.sort([transaction, account, user, group, role])

        # Build index map
        indices = {r.identifier.table_name: i for i, r in enumerate(result)}

        # Verify dependency order
        assert indices["roles"] < indices["users"]
        assert indices["users"] < indices["bank_accounts"]
        assert indices["bank_accounts"] < indices["transactions"]

    def test_circular_dependency_detection(self):
        """Test circular dependency raises CircularDependencyError."""
        sorter = DependencySorter()

        # Create circular dependency: A -> B -> A
        a_id = RecordIdentifier("public", "a", {"id": 1})
        b_id = RecordIdentifier("public", "b", {"id": 1})

        a = RecordData(identifier=a_id, data={"id": 1}, dependencies=[b_id])
        b = RecordData(identifier=b_id, data={"id": 1}, dependencies=[a_id])

        with pytest.raises(CircularDependencyError) as exc_info:
            sorter.sort([a, b])

        assert "circular" in str(exc_info.value).lower()

    def test_self_referencing_dependency(self):
        """Test self-referencing record (e.g., user.manager_id -> user.id)."""
        sorter = DependencySorter()

        # User 2 depends on User 1 (manager relationship)
        user1 = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 1}),
            data={"id": 1, "manager_id": None},
            dependencies=[],
        )
        user2 = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 2}),
            data={"id": 2, "manager_id": 1},
            dependencies=[user1.identifier],
        )

        result = sorter.sort([user2, user1])

        assert len(result) == 2
        assert result[0].identifier.pk_values["id"] == 1  # User 1 first
        assert result[1].identifier.pk_values["id"] == 2  # User 2 second

    def test_multiple_records_same_table_no_deps(self):
        """Test multiple records from same table with no dependencies."""
        sorter = DependencySorter()

        role1 = RecordData(
            identifier=RecordIdentifier("public", "roles", {"id": 1}),
            data={"id": 1, "name": "admin"},
            dependencies=[],
        )
        role2 = RecordData(
            identifier=RecordIdentifier("public", "roles", {"id": 2}),
            data={"id": 2, "name": "user"},
            dependencies=[],
        )

        result = sorter.sort([role1, role2])

        assert len(result) == 2
        # Order doesn't matter when no dependencies, just check both are present
        assert role1 in result
        assert role2 in result

    def test_preserves_order_when_no_dependencies(self):
        """Test sorting preserves input order when records have no dependencies."""
        sorter = DependencySorter()

        records = [
            RecordData(
                identifier=RecordIdentifier("public", "a", {"id": i}),
                data={"id": i},
                dependencies=[],
            )
            for i in range(10)
        ]

        result = sorter.sort(records)

        # When no dependencies, stable sort should preserve original order
        assert result == records

    def test_missing_dependency_not_in_set(self):
        """Test record with dependency not in the input set (should still work)."""
        sorter = DependencySorter()

        # User depends on role, but role is not in the input set
        # This represents a valid FK reference to existing data
        user = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 1}),
            data={"id": 1, "role_id": 1},
            dependencies=[RecordIdentifier("public", "roles", {"id": 1})],
        )

        result = sorter.sort([user])

        # Should work - missing dependencies are external references
        assert len(result) == 1
        assert result[0] == user

    def test_composite_primary_keys(self):
        """Test sorting with composite primary keys."""
        sorter = DependencySorter()

        user = RecordData(
            identifier=RecordIdentifier("public", "users", {"id": 1}),
            data={"id": 1},
            dependencies=[],
        )
        group = RecordData(
            identifier=RecordIdentifier("public", "groups", {"id": 2}),
            data={"id": 2},
            dependencies=[],
        )
        user_group = RecordData(
            identifier=RecordIdentifier("public", "user_groups", {"user_id": 1, "group_id": 2}),
            data={"user_id": 1, "group_id": 2},
            dependencies=[user.identifier, group.identifier],
        )

        result = sorter.sort([user_group, user, group])

        # user_group must come after both user and group
        indices = {r.identifier.table_name: i for i, r in enumerate(result)}
        ug_index = indices["user_groups"]
        u_index = indices["users"]
        g_index = indices["groups"]

        assert u_index < ug_index
        assert g_index < ug_index
