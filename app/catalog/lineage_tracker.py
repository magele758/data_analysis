import threading
import re
from typing import Dict, List, Set, Any, Optional

class LineageNode:
    def __init__(self, name: str, node_type: str = "TABLE"):
        self.name = name
        self.node_type = node_type
        self.upstream: Set[str] = set()
        self.downstream: Set[str] = set()

class LineageTracker:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._nodes: Dict[str, LineageNode] = {}

    @classmethod
    def get_instance(cls) -> "LineageTracker":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def record_dependency(self, source_table: str, target_table: str):
        if not source_table or not target_table or source_table == target_table:
            return
        with self._lock:
            if source_table not in self._nodes:
                self._nodes[source_table] = LineageNode(source_table)
            if target_table not in self._nodes:
                self._nodes[target_table] = LineageNode(target_table)

            self._nodes[source_table].downstream.add(target_table)
            self._nodes[target_table].upstream.add(source_table)

    def parse_and_record_sql_lineage(self, target_table: str, sql_query: str):
        """
        Robust SQL Lineage Parser:
        1. Identifies CTEs (Common Table Expressions) declared in `WITH cte AS (...)` to avoid treating CTE aliases as external physical tables.
        2. Extracts all physical source tables referenced in FROM and JOIN clauses.
        3. Records dependencies into the DAG lineage graph.
        """
        if not sql_query:
            return

        # 1. Extract CTE names to exclude them from external dependencies
        cte_names = set()
        cte_pattern = re.compile(r'(?:WITH|,)\s*([a-zA-Z0-9_]+)\s+AS\s*\(', re.IGNORECASE)
        for match in cte_pattern.finditer(sql_query):
            cte_names.add(match.group(1).lower())

        # 2. Extract FROM and JOIN target sources
        source_pattern = re.compile(
            r'(?:FROM|JOIN)\s+([a-zA-Z0-9_\.]+)(?:\s+(?:AS\s+)?([a-zA-Z0-9_]+))?',
            re.IGNORECASE
        )
        
        # Reserved SQL keywords that cannot be table names
        reserved = {
            'select', 'where', 'group', 'order', 'having', 'limit', 'union', 
            'left', 'right', 'inner', 'full', 'outer', 'cross', 'join', 'on', 
            'as', 'case', 'when', 'then', 'else', 'end', 'values', 'table',
            'unnest', 'generate_series', 'read_parquet', 'read_csv', 'read_csv_auto'
        }

        matches = source_pattern.findall(sql_query)
        for table_ref, alias in matches:
            clean_name = table_ref.strip('`"[]')
            # Extract base table if schema-qualified
            parts = clean_name.split('.')
            base_table = parts[-1].strip('`"[]')

            base_lower = base_table.lower()
            if base_lower in reserved:
                continue
            if base_lower in cte_names:
                continue
            if not base_table.isidentifier():
                continue

            self.record_dependency(base_table, target_table)

    def get_lineage_graph(self) -> Dict[str, Any]:
        with self._lock:
            nodes = [{"id": k, "name": k, "type": v.node_type} for k, v in self._nodes.items()]
            edges = []
            for src_name, node in self._nodes.items():
                for tgt_name in node.downstream:
                    edges.append({"source": src_name, "target": tgt_name})
            return {"nodes": nodes, "edges": edges}

    def get_impact_analysis(self, table_name: str) -> Dict[str, Any]:
        """Find all downstream affected models/tables if table_name changes."""
        with self._lock:
            visited = set()
            queue = [table_name]
            while queue:
                curr = queue.pop(0)
                if curr in self._nodes:
                    for ds in self._nodes[curr].downstream:
                        if ds not in visited:
                            visited.add(ds)
                            queue.append(ds)
            return {
                "source": table_name,
                "affected_downstream_count": len(visited),
                "affected_tables": list(visited)
            }

def get_lineage_tracker() -> LineageTracker:
    return LineageTracker.get_instance()
