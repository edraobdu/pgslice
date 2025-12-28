"""Tests for graph visualization utility."""

from __future__ import annotations

from pgslice.graph.models import RecordData, RecordIdentifier
from pgslice.utils.graph_visualizer import (
    GraphBuilder,
    GraphRenderer,
    TableEdge,
    TableGraph,
    TableNode,
)


class TestGraphBuilder:
    """Tests for GraphBuilder class."""

    def test_single_table_no_dependencies(self) -> None:
        """Should create graph with single node and no edges."""
        # Create single record with no dependencies
        record_id = RecordIdentifier("users", "public", ("1",))
        record = RecordData(identifier=record_id, data={"id": 1})

        builder = GraphBuilder()
        graph = builder.build({record}, "users", "public")

        assert len(graph.nodes) == 1
        assert graph.nodes[0].table_name == "users"
        assert graph.nodes[0].schema_name == "public"
        assert graph.nodes[0].record_count == 1
        assert graph.nodes[0].is_root is True
        assert len(graph.edges) == 0

    def test_simple_parent_child(self) -> None:
        """Should create graph with parent-child relationship."""
        # Create user record (parent)
        user_id = RecordIdentifier("users", "public", ("1",))
        user = RecordData(identifier=user_id, data={"id": 1})

        # Create order records (children) that depend on user
        order1_id = RecordIdentifier("orders", "public", ("101",))
        order1 = RecordData(
            identifier=order1_id, data={"id": 101, "user_id": 1}, dependencies={user_id}
        )

        order2_id = RecordIdentifier("orders", "public", ("102",))
        order2 = RecordData(
            identifier=order2_id, data={"id": 102, "user_id": 1}, dependencies={user_id}
        )

        order3_id = RecordIdentifier("orders", "public", ("103",))
        order3 = RecordData(
            identifier=order3_id, data={"id": 103, "user_id": 1}, dependencies={user_id}
        )

        builder = GraphBuilder()
        graph = builder.build({user, order1, order2, order3}, "users", "public")

        # Should have 2 nodes (users, orders)
        assert len(graph.nodes) == 2

        # Find nodes
        users_node = next(n for n in graph.nodes if n.table_name == "users")
        orders_node = next(n for n in graph.nodes if n.table_name == "orders")

        assert users_node.record_count == 1
        assert users_node.is_root is True
        assert orders_node.record_count == 3
        assert orders_node.is_root is False

        # Should have 1 edge (orders -> users)
        assert len(graph.edges) == 1
        assert graph.edges[0].source_table == "public.orders"
        assert graph.edges[0].target_table == "public.users"

    def test_record_counting(self) -> None:
        """Should correctly count multiple records from same table."""
        # Create 5 user records
        records = set()
        for i in range(1, 6):
            record_id = RecordIdentifier("users", "public", (str(i),))
            record = RecordData(identifier=record_id, data={"id": i})
            records.add(record)

        builder = GraphBuilder()
        graph = builder.build(records, "users", "public")

        assert len(graph.nodes) == 1
        assert graph.nodes[0].record_count == 5

    def test_edge_counting(self) -> None:
        """Should count how many records use same FK relationship."""
        # Create 1 user
        user_id = RecordIdentifier("users", "public", ("1",))
        user = RecordData(identifier=user_id, data={"id": 1})

        # Create 10 orders all referencing same user
        records = {user}
        for i in range(1, 11):
            order_id = RecordIdentifier("orders", "public", (str(i),))
            order = RecordData(
                identifier=order_id,
                data={"id": i, "user_id": 1},
                dependencies={user_id},
            )
            records.add(order)

        builder = GraphBuilder()
        graph = builder.build(records, "users", "public")

        assert len(graph.edges) == 1
        assert graph.edges[0].record_count == 10

    def test_multiple_tables_with_dependencies(self) -> None:
        """Should handle complex graph with multiple tables."""
        # Create: users -> orders -> order_items
        user_id = RecordIdentifier("users", "public", ("1",))
        user = RecordData(identifier=user_id, data={"id": 1})

        order_id = RecordIdentifier("orders", "public", ("101",))
        order = RecordData(
            identifier=order_id, data={"id": 101}, dependencies={user_id}
        )

        item_id = RecordIdentifier("order_items", "public", ("1001",))
        item = RecordData(
            identifier=item_id, data={"id": 1001}, dependencies={order_id}
        )

        builder = GraphBuilder()
        graph = builder.build({user, order, item}, "users", "public")

        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2

        # Verify edges
        edge_sources = {e.source_table for e in graph.edges}
        edge_targets = {e.target_table for e in graph.edges}

        assert "public.orders" in edge_sources
        assert "public.order_items" in edge_sources
        assert "public.users" in edge_targets
        assert "public.orders" in edge_targets

    def test_non_root_table_when_root_not_in_results(self) -> None:
        """Should mark is_root=False if root table not in results."""
        # Create order record but specify users as root
        order_id = RecordIdentifier("orders", "public", ("101",))
        order = RecordData(identifier=order_id, data={"id": 101})

        builder = GraphBuilder()
        graph = builder.build({order}, "users", "public")

        assert len(graph.nodes) == 1
        assert graph.nodes[0].is_root is False  # Not the specified root


class TestGraphRenderer:
    """Tests for GraphRenderer class."""

    def test_single_root_no_children(self) -> None:
        """Should render single node without tree structure."""
        node = TableNode("users", "public", 1, is_root=True)
        graph = TableGraph(nodes=[node], edges=[])

        renderer = GraphRenderer()
        output = renderer.render(graph)

        # Check for content (output now has ANSI color codes)
        assert "users" in output
        assert "1 records" in output
        assert "(No related tables)" in output

    def test_linear_chain(self) -> None:
        """Should render linear dependency chain."""
        # A -> B -> C
        node_a = TableNode("table_a", "public", 1, is_root=True)
        node_b = TableNode("table_b", "public", 1, is_root=False)
        node_c = TableNode("table_c", "public", 1, is_root=False)

        edge_ab = TableEdge("public.table_b", "public.table_a", None, 1)
        edge_bc = TableEdge("public.table_c", "public.table_b", None, 1)

        graph = TableGraph(nodes=[node_a, node_b, node_c], edges=[edge_ab, edge_bc])

        renderer = GraphRenderer()
        output = renderer.render(graph)

        lines = output.split("\n")
        assert len(lines) == 3
        # Check for table names (output has color codes)
        assert "table_a" in lines[0] and "1 records" in lines[0]
        assert "table_b" in lines[1] and "1 records" in lines[1]
        assert "table_c" in lines[2] and "1 records" in lines[2]

    def test_multiple_children(self) -> None:
        """Should render multiple children with correct connectors."""
        # Root with 3 children
        root = TableNode("users", "public", 1, is_root=True)
        child1 = TableNode("orders", "public", 2, is_root=False)
        child2 = TableNode("addresses", "public", 3, is_root=False)
        child3 = TableNode("reviews", "public", 4, is_root=False)

        edges = [
            TableEdge("public.orders", "public.users", None, 2),
            TableEdge("public.addresses", "public.users", None, 3),
            TableEdge("public.reviews", "public.users", None, 4),
        ]

        graph = TableGraph(nodes=[root, child1, child2, child3], edges=edges)

        renderer = GraphRenderer()
        output = renderer.render(graph)

        # Should have root + 3 children (check for content)
        assert "users" in output and "1 records" in output
        assert "orders" in output and "2 records" in output
        assert "addresses" in output and "3 records" in output
        assert "reviews" in output and "4 records" in output

        # Should use branch characters (├── for non-last, └── for last)
        assert "├──" in output  # First two children
        assert "└──" in output  # Last child

    def test_circular_dependency_detection(self) -> None:
        """Should detect and mark circular dependencies."""
        # A -> B -> A (circular)
        node_a = TableNode("table_a", "public", 1, is_root=True)
        node_b = TableNode("table_b", "public", 1, is_root=False)

        # Create circular edges
        edge_ab = TableEdge("public.table_b", "public.table_a", None, 1)
        edge_ba = TableEdge("public.table_a", "public.table_b", None, 1)

        graph = TableGraph(nodes=[node_a, node_b], edges=[edge_ab, edge_ba])

        renderer = GraphRenderer()
        output = renderer.render(graph)

        # Should mark cycle
        assert "[shown above]" in output

    def test_unicode_characters(self) -> None:
        """Should use Unicode box-drawing characters."""
        root = TableNode("users", "public", 1, is_root=True)
        child = TableNode("orders", "public", 2, is_root=False)
        edge = TableEdge("public.orders", "public.users", None, 2)

        graph = TableGraph(nodes=[root, child], edges=[edge])

        renderer = GraphRenderer()
        output = renderer.render(graph)

        # Should contain box-drawing chars (├──, │, └──)
        # At least one should be present
        has_unicode = any(char in output for char in ["├", "└", "│", "─"])
        assert has_unicode

    def test_empty_graph(self) -> None:
        """Should handle empty graph gracefully."""
        graph = TableGraph(nodes=[], edges=[])

        renderer = GraphRenderer()
        output = renderer.render(graph)

        assert output == "(No records found)"

    def test_nested_hierarchy(self) -> None:
        """Should render nested hierarchy with proper indentation."""
        # users -> orders -> order_items
        users = TableNode("users", "public", 1, is_root=True)
        orders = TableNode("orders", "public", 2, is_root=False)
        items = TableNode("order_items", "public", 5, is_root=False)

        edges = [
            TableEdge("public.orders", "public.users", None, 2),
            TableEdge("public.order_items", "public.orders", None, 5),
        ]

        graph = TableGraph(nodes=[users, orders, items], edges=edges)

        renderer = GraphRenderer()
        output = renderer.render(graph)

        lines = output.split("\n")
        assert len(lines) == 3

        # Check that all tables appear in output
        assert "users" in output
        assert "orders" in output
        assert "order_items" in output

        # Check for tree structure characters (output has ANSI color codes)
        assert "└" in output or "├" in output  # Has tree structure

    def test_multiple_roots(self) -> None:
        """Should handle multiple root nodes."""
        root1 = TableNode("users", "public", 1, is_root=True)
        root2 = TableNode("products", "public", 2, is_root=True)

        graph = TableGraph(nodes=[root1, root2], edges=[])

        renderer = GraphRenderer()
        output = renderer.render(graph)

        # Both roots should appear (output has color codes)
        assert "users" in output and "1 records" in output
        assert "products" in output and "2 records" in output
