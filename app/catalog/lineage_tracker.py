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
    _lock = threading.Lock()

    def __init__(self):
        self._nodes: Dict[str, LineageNode] = {}

    @classmethod
    def get_instance(cls) -> "LineageTracker":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def record_dependency(self, source_table: str, target_table: str):
        with self._lock:
            if source_table not in self._nodes:
                self._nodes[source_table] = LineageNode(source_table)
            if target_table not in self._nodes:
                self._nodes[target_table] = LineageNode(target_table)

            self._nodes[source_table].downstream.add(target_table)
            self._nodes[target_table].upstream.add(source_table)

    def parse_and_record_sql_lineage(self, target_table: str, sql_query: str):
        """Extract source tables from simple FROM / JOIN clauses using regex and record lineage."""
        pattern = re.compile(r'(?:FROM|JOIN)\s+([a-zA-Z0-9_\.]+)', re.IGNORECASE)
        matches = pattern.findall(sql_query)
        for src in matches:
            src_clean = src.split('.')[-1].strip('`"[]')
            if src_clean and src_clean.lower() not in ('where', 'group', 'order', 'limit', 'select', 'join'):
                self.record_dependency(src_clean, target_table)

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
