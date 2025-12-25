"""Tests for pgslice.dumper.dependency_sorter module."""

from __future__ import annotations

import pytest

from pgslice.dumper.dependency_sorter import DependencySorter
from pgslice.graph.models import RecordData, RecordIdentifier
from pgslice.utils.exceptions import CircularDependencyError


class TestDependencySorter:
    """Tests for DependencySorter class."""

    @pytest.fixture
    def sorter(self) -> DependencySorter:
        """Provide a DependencySorter instance."""
        return DependencySorter()


class TestSort(TestDependencySorter):
    """Tests for sort method."""

    def test_empty_set_returns_empty_list(self, sorter: DependencySorter) -> None:
        """Sorting empty set should return empty list."""
        result = sorter.sort(set())
        assert result == []

    def test_single_record_no_dependencies(self, sorter: DependencySorter) -> None:
        """Single record with no dependencies should be returned as-is."""
        record = RecordData(
            identifier=RecordIdentifier(
                schema_name="public",
                table_name="users",
                pk_values=(1,),
            ),
            data={"id": 1},
            dependencies=set(),
        )
        result = sorter.sort({record})
        assert len(result) == 1
        assert result[0] == record

    def test_linear_dependency_chain(
        self, sorter: DependencySorter, record_chain: list[RecordData]
    ) -> None:
        """
        Linear chain A -> B -> C should be sorted as C, B, A.

        Dependencies should come before dependents.
        """
        record_a, record_b, record_c = record_chain
        result = sorter.sort({record_a, record_b, record_c})

        # C has no dependencies, should be first
        # B depends on C, should be second
        # A depends on B, should be last
        result_ids = [r.identifier for r in result]
        c_idx = result_ids.index(record_c.identifier)
        b_idx = result_ids.index(record_b.identifier)
        a_idx = result_ids.index(record_a.identifier)

        assert c_idx < b_idx < a_idx

    def test_diamond_dependency(
        self, sorter: DependencySorter, diamond_dependency_records: set[RecordData]
    ) -> None:
        """
        Diamond dependency: A depends on B and C, both depend on D.

        D should come first, then B and C (order between them doesn't matter),
        then A should come last.
        """
        result = sorter.sort(diamond_dependency_records)

        # Find indices
        d_idx = next(
            i for i, r in enumerate(result) if r.identifier.table_name == "base"
        )
        b_idx = next(
            i for i, r in enumerate(result) if r.identifier.table_name == "middle_b"
        )
        c_idx = next(
            i for i, r in enumerate(result) if r.identifier.table_name == "middle_c"
        )
        a_idx = next(
            i for i, r in enumerate(result) if r.identifier.table_name == "top"
        )

        # D should come before B and C
        assert d_idx < b_idx
        assert d_idx < c_idx
        # B and C should come before A
        assert b_idx < a_idx
        assert c_idx < a_idx

    def test_circular_dependency_raises_error(self, sorter: DependencySorter) -> None:
        """Circular dependencies should raise CircularDependencyError."""
        # Create circular: A -> B -> A
        id_a = RecordIdentifier(
            schema_name="public",
            table_name="table_a",
            pk_values=(1,),
        )
        id_b = RecordIdentifier(
            schema_name="public",
            table_name="table_b",
            pk_values=(2,),
        )

        record_a = RecordData(
            identifier=id_a,
            data={"id": 1},
            dependencies={id_b},
        )
        record_b = RecordData(
            identifier=id_b,
            data={"id": 2},
            dependencies={id_a},
        )

        with pytest.raises(CircularDependencyError, match="Circular dependency"):
            sorter.sort({record_a, record_b})

    def test_self_referencing_dependency_raises_error(
        self, sorter: DependencySorter
    ) -> None:
        """Self-referencing dependency should raise CircularDependencyError."""
        id_a = RecordIdentifier(
            schema_name="public",
            table_name="self_ref",
            pk_values=(1,),
        )

        record_a = RecordData(
            identifier=id_a,
            data={"id": 1},
            dependencies={id_a},  # Self-reference
        )

        with pytest.raises(CircularDependencyError):
            sorter.sort({record_a})

    def test_multiple_independent_records(self, sorter: DependencySorter) -> None:
        """Records with no dependencies between them can be in any order."""
        records = set()
        for i in range(5):
            records.add(
                RecordData(
                    identifier=RecordIdentifier(
                        schema_name="public",
                        table_name=f"table_{i}",
                        pk_values=(i,),
                    ),
                    data={"id": i},
                    dependencies=set(),
                )
            )

        result = sorter.sort(records)
        assert len(result) == 5
        # All records should be in result
        assert set(result) == records

    def test_external_dependencies_ignored(self, sorter: DependencySorter) -> None:
        """Dependencies to records not in the set should be ignored."""
        external_id = RecordIdentifier(
            schema_name="public",
            table_name="external",
            pk_values=(999,),
        )
        record = RecordData(
            identifier=RecordIdentifier(
                schema_name="public",
                table_name="internal",
                pk_values=(1,),
            ),
            data={"id": 1},
            dependencies={external_id},  # External dependency
        )

        result = sorter.sort({record})
        assert len(result) == 1
        assert result[0] == record

    def test_complex_dependency_graph(self, sorter: DependencySorter) -> None:
        """
        Complex graph with multiple dependency paths.

        Structure:
            E
            |
            D
           / \\
          B   C
           \\ /
            A

        Valid orders include: A, B, C (or C, B), D, E
        """
        id_a = RecordIdentifier(schema_name="public", table_name="a", pk_values=(1,))
        id_b = RecordIdentifier(schema_name="public", table_name="b", pk_values=(2,))
        id_c = RecordIdentifier(schema_name="public", table_name="c", pk_values=(3,))
        id_d = RecordIdentifier(schema_name="public", table_name="d", pk_values=(4,))
        id_e = RecordIdentifier(schema_name="public", table_name="e", pk_values=(5,))

        record_a = RecordData(identifier=id_a, data={"id": 1}, dependencies=set())
        record_b = RecordData(identifier=id_b, data={"id": 2}, dependencies={id_a})
        record_c = RecordData(identifier=id_c, data={"id": 3}, dependencies={id_a})
        record_d = RecordData(
            identifier=id_d, data={"id": 4}, dependencies={id_b, id_c}
        )
        record_e = RecordData(identifier=id_e, data={"id": 5}, dependencies={id_d})

        result = sorter.sort({record_a, record_b, record_c, record_d, record_e})

        result_ids = [r.identifier for r in result]
        a_idx = result_ids.index(id_a)
        b_idx = result_ids.index(id_b)
        c_idx = result_ids.index(id_c)
        d_idx = result_ids.index(id_d)
        e_idx = result_ids.index(id_e)

        # Verify ordering constraints
        assert a_idx < b_idx  # A before B
        assert a_idx < c_idx  # A before C
        assert b_idx < d_idx  # B before D
        assert c_idx < d_idx  # C before D
        assert d_idx < e_idx  # D before E


class TestAnalyzeDependencies(TestDependencySorter):
    """Tests for analyze_dependencies method."""

    def test_empty_set_returns_zeros(self, sorter: DependencySorter) -> None:
        """Empty set should return all zeros."""
        stats = sorter.analyze_dependencies(set())
        assert stats["total_records"] == 0
        assert stats["records_with_deps"] == 0
        assert stats["max_dependencies"] == 0
        assert stats["avg_dependencies"] == 0.0

    def test_single_record_no_deps(self, sorter: DependencySorter) -> None:
        """Single record with no dependencies."""
        record = RecordData(
            identifier=RecordIdentifier(
                schema_name="public",
                table_name="users",
                pk_values=(1,),
            ),
            data={"id": 1},
            dependencies=set(),
        )
        stats = sorter.analyze_dependencies({record})
        assert stats["total_records"] == 1
        assert stats["records_with_deps"] == 0
        assert stats["max_dependencies"] == 0
        assert stats["avg_dependencies"] == 0.0

    def test_single_record_with_deps(self, sorter: DependencySorter) -> None:
        """Single record with dependencies."""
        dep_id = RecordIdentifier(
            schema_name="public", table_name="other", pk_values=(99,)
        )
        record = RecordData(
            identifier=RecordIdentifier(
                schema_name="public",
                table_name="users",
                pk_values=(1,),
            ),
            data={"id": 1},
            dependencies={dep_id},
        )
        stats = sorter.analyze_dependencies({record})
        assert stats["total_records"] == 1
        assert stats["records_with_deps"] == 1
        assert stats["max_dependencies"] == 1
        assert stats["avg_dependencies"] == 1.0

    def test_multiple_records_mixed_deps(self, sorter: DependencySorter) -> None:
        """Multiple records with varying dependencies."""
        dep1 = RecordIdentifier(schema_name="public", table_name="dep", pk_values=(1,))
        dep2 = RecordIdentifier(schema_name="public", table_name="dep", pk_values=(2,))
        dep3 = RecordIdentifier(schema_name="public", table_name="dep", pk_values=(3,))

        record_no_deps = RecordData(
            identifier=RecordIdentifier(
                schema_name="public", table_name="a", pk_values=(1,)
            ),
            data={"id": 1},
            dependencies=set(),
        )
        record_one_dep = RecordData(
            identifier=RecordIdentifier(
                schema_name="public", table_name="b", pk_values=(2,)
            ),
            data={"id": 2},
            dependencies={dep1},
        )
        record_three_deps = RecordData(
            identifier=RecordIdentifier(
                schema_name="public", table_name="c", pk_values=(3,)
            ),
            data={"id": 3},
            dependencies={dep1, dep2, dep3},
        )

        stats = sorter.analyze_dependencies(
            {record_no_deps, record_one_dep, record_three_deps}
        )
        assert stats["total_records"] == 3
        assert stats["records_with_deps"] == 2  # Two records have deps
        assert stats["max_dependencies"] == 3  # Max is 3
        # Average: (0 + 1 + 3) / 3 = 1.333...
        assert abs(stats["avg_dependencies"] - 4 / 3) < 0.001

    def test_stats_on_chain(
        self, sorter: DependencySorter, record_chain: list[RecordData]
    ) -> None:
        """Statistics on linear chain A -> B -> C."""
        record_a, record_b, record_c = record_chain
        stats = sorter.analyze_dependencies({record_a, record_b, record_c})

        assert stats["total_records"] == 3
        assert stats["records_with_deps"] == 2  # A and B have deps
        assert stats["max_dependencies"] == 1  # Each has at most 1 dep
        assert abs(stats["avg_dependencies"] - 2 / 3) < 0.001
