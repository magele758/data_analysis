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

        sqlglot is used when installed. Its tables are unioned with the regex
        result, and regex CTE names are always excluded, so a parser miss cannot
        drop a physical table or promote a CTE.
        """
        if not sql_query:
            return
        for base_table in _lineage_sources(sql_query):
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

_LINEAGE_RESERVED = {
    'select', 'where', 'group', 'order', 'having', 'limit', 'union',
    'left', 'right', 'inner', 'full', 'outer', 'cross', 'join', 'on',
    'as', 'case', 'when', 'then', 'else', 'end', 'values', 'table',
    'unnest', 'generate_series', 'read_parquet', 'read_csv', 'read_csv_auto'
}
_CTE_RE = re.compile(r'(?:WITH|,)\s*([a-zA-Z0-9_]+)\s+AS\s*\(', re.IGNORECASE)
_SOURCE_RE = re.compile(
    r'(?:FROM|JOIN)\s+([a-zA-Z0-9_\.]+)(?:\s+(?:AS\s+)?([a-zA-Z0-9_]+))?',
    re.IGNORECASE,
)


def _regex_ctes(sql_query: str) -> set:
    return {match.group(1).lower() for match in _CTE_RE.finditer(sql_query)}


def _regex_sources(sql_query: str, cte_names: set) -> List[str]:
    names = []
    for table_ref, _alias in _SOURCE_RE.findall(sql_query):
        base_table = table_ref.strip('`"[]').split('.')[-1].strip('`"[]')
        base_lower = base_table.lower()
        if base_lower in _LINEAGE_RESERVED or base_lower in cte_names:
            continue
        if not base_table.isidentifier():
            continue
        names.append(base_table)
    return names


def _sqlglot_sources(sql_query: str) -> Optional[List[str]]:
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:
        return None
    try:
        try:
            tree = sqlglot.parse_one(sql_query, read="duckdb")
        except TypeError:
            tree = sqlglot.parse_one(sql_query, dialect="duckdb")
    except Exception:
        return None
    ctes = set()
    for cte in tree.find_all(exp.CTE):
        alias = getattr(cte, "alias_or_name", None) or getattr(cte, "alias", None)
        if alias:
            ctes.add(str(alias).split(".")[-1].strip('"').lower())
    names = []
    for table in tree.find_all(exp.Table):
        name = table.name
        if not name or name.lower() in ctes or name.lower() in _LINEAGE_RESERVED:
            continue
        names.append(name)
    return names


def _lineage_sources(sql_query: str) -> List[str]:
    cte_names = _regex_ctes(sql_query)
    regex_tables = _regex_sources(sql_query, cte_names)
    glot_tables = _sqlglot_sources(sql_query) or []
    merged = []
    seen = set()
    for name in list(glot_tables) + list(regex_tables):
        if name.lower() in cte_names or name.lower() in seen:
            continue
        seen.add(name.lower())
        merged.append(name)
    return merged


_lineage_session_instances: Dict[str, "LineageTracker"] = {}


def get_lineage_tracker(session_id: str = "_global") -> LineageTracker:
    with LineageTracker._lock:
        inst = _lineage_session_instances.get(session_id)
        if inst is None:
            inst = LineageTracker()
            _lineage_session_instances[session_id] = inst
        return inst
