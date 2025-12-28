"""Graph visualization for relationship traversal results."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from printy import raw

from ..graph.models import RecordData


@dataclass
class TableNode:
    """Represents a table in the relationship graph."""

    table_name: str
    schema_name: str
    record_count: int
    is_root: bool = False


@dataclass
class TableEdge:
    """Represents a FK relationship between tables."""

    source_table: str  # Child table (has FK column)
    target_table: str  # Parent table (referenced by FK)
    fk_column: str | None  # FK column name (if available)
    record_count: int  # Number of records using this relationship


@dataclass
class TableGraph:
    """Complete table-level graph structure."""

    nodes: list[TableNode]
    edges: list[TableEdge]


class GraphBuilder:
    """Builds table-level graph from RecordData set."""

    def build(
        self, records: set[RecordData], root_table: str, root_schema: str
    ) -> TableGraph:
        """
        Build table-level graph from RecordData set.

        Args:
            records: Set of all fetched records
            root_table: Name of the starting table
            root_schema: Schema of the starting table

        Returns:
            TableGraph with nodes and edges
        """
        # 1. Count records per table
        table_counts: dict[tuple[str, str], int] = defaultdict(int)
        for record in records:
            key = (record.identifier.schema_name, record.identifier.table_name)
            table_counts[key] += 1

        # 2. Extract FK relationships from dependencies
        edges: dict[tuple[str, str], dict[tuple[str, str], int]] = defaultdict(
            lambda: defaultdict(int)
        )
        for record in records:
            source_key = (
                record.identifier.schema_name,
                record.identifier.table_name,
            )
            for dep in record.dependencies:
                target_key = (dep.schema_name, dep.table_name)
                # Count how many records use this FK relationship
                edges[source_key][target_key] += 1

        # 3. Create nodes (mark root)
        nodes = [
            TableNode(
                table_name=table,
                schema_name=schema,
                record_count=count,
                is_root=(table == root_table and schema == root_schema),
            )
            for (schema, table), count in table_counts.items()
        ]

        # 4. Create edges
        edge_list = []
        for (src_schema, src_table), targets in edges.items():
            for (tgt_schema, tgt_table), count in targets.items():
                edge_list.append(
                    TableEdge(
                        source_table=f"{src_schema}.{src_table}",
                        target_table=f"{tgt_schema}.{tgt_table}",
                        fk_column=None,  # Can enhance later with FK column name
                        record_count=count,
                    )
                )

        return TableGraph(nodes=nodes, edges=edge_list)


class GraphRenderer:
    """Renders table graph as ASCII tree using Unicode box-drawing."""

    # Unicode box-drawing characters
    BRANCH = "├── "
    PIPE = "│   "
    LAST = "└── "
    SPACE = "    "

    def render(self, graph: TableGraph) -> str:
        """
        Render graph as tree using Unicode box-drawing.

        Args:
            graph: TableGraph to render

        Returns:
            Formatted string with tree visualization
        """
        # 1. Find root nodes
        roots = [node for node in graph.nodes if node.is_root]
        if not roots:
            # Fallback: find nodes with no incoming edges
            incoming = {edge.target_table for edge in graph.edges}
            roots = [
                node
                for node in graph.nodes
                if f"{node.schema_name}.{node.table_name}" not in incoming
            ]

        # Handle empty graph
        if not roots:
            if graph.nodes:
                # No clear root, use first node
                roots = [graph.nodes[0]]
            else:
                return "(No records found)"

        # 2. Build adjacency list (bidirectional to show full traversal)
        children: dict[str, list[tuple[TableNode, TableEdge]]] = defaultdict(list)
        for edge in graph.edges:
            # Find both child and parent nodes
            child_node = next(
                (
                    n
                    for n in graph.nodes
                    if f"{n.schema_name}.{n.table_name}" == edge.source_table
                ),
                None,
            )
            parent_node = next(
                (
                    n
                    for n in graph.nodes
                    if f"{n.schema_name}.{n.table_name}" == edge.target_table
                ),
                None,
            )

            if child_node and parent_node:
                # Add child to parent's list (reverse FK: parent <- child)
                children[edge.target_table].append((child_node, edge))

                # Add parent to child's list (forward FK: child -> parent)
                # This allows showing full traversal tree
                children[edge.source_table].append((parent_node, edge))

        # 3. Render tree with DFS
        lines: list[str] = []
        visited: set[str] = set()

        for root in roots:
            self._render_node(
                root, children, "", True, lines, visited, is_root=True, parent=None
            )

        # Handle single table with no relationships
        if len(lines) == 1 and not children:
            lines.append("(No related tables)")

        return "\n".join(lines)

    def _render_node(
        self,
        node: TableNode,
        children: dict[str, list[tuple[TableNode, TableEdge]]],
        prefix: str,
        is_last: bool,
        lines: list[str],
        visited: set[str],
        is_root: bool = False,
        parent: TableNode | None = None,
    ) -> None:
        """
        Recursively render node and its children.

        Args:
            node: Current node to render
            children: Adjacency list of parent -> children
            prefix: Current indentation prefix
            is_last: Whether this is the last child of its parent
            lines: Accumulator for output lines
            visited: Set of already visited nodes (for cycle detection)
            is_root: Whether this is a root node
            parent: Parent node we came from (to avoid immediate back-references)
        """
        full_name = f"{node.schema_name}.{node.table_name}"

        # Format current node with colors using printy
        if is_root:
            # Root nodes: cyan (bold) table name + yellow count
            line = raw(f"[cB]{node.table_name}@ [y]({node.record_count} records)@")
        else:
            connector = self.LAST if is_last else self.BRANCH
            # Tree structure: dark connectors + cyan table name + yellow count
            line = (
                prefix
                + raw(f"[n]{connector}@")
                + raw(f"[c]{node.table_name}@ ")
                + raw(f"[y]({node.record_count} records)@")
            )

        # Check if already shown (cycle detection)
        if full_name in visited and not is_root:
            line += raw(" [n][shown above]@")
            lines.append(line)
            return

        lines.append(line)
        visited.add(full_name)

        # Render children (filter out immediate parent to avoid back-reference)
        child_list = children.get(full_name, [])

        # Filter out the parent we just came from
        if parent:
            parent_name = f"{parent.schema_name}.{parent.table_name}"
            child_list = [
                (child, edge)
                for child, edge in child_list
                if f"{child.schema_name}.{child.table_name}" != parent_name
            ]

        for i, (child_node, _edge) in enumerate(child_list):
            is_last_child = i == len(child_list) - 1

            # Update prefix for child (with colored tree characters)
            if is_root:
                child_prefix = ""
            elif is_last:
                child_prefix = prefix + self.SPACE
            else:
                child_prefix = prefix + raw(f"[n]{self.PIPE}@")

            self._render_node(
                child_node,
                children,
                child_prefix,
                is_last_child,
                lines,
                visited,
                parent=node,
            )
