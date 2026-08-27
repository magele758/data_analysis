import threading
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from app.catalog.metadata_db import MetadataDB
from app.engine.sql_guard import safe_ident, safe_predicate, safe_table_ref

class MetricDefinition(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = ""
    table_name: str
    formula: str # e.g. "SUM(sales)", "AVG(dwell_time)", "SUM(profit) / NULLIF(SUM(sales), 0)"
    aggregation_type: str = "SUM" # SUM, AVG, COUNT, RATIO, CUSTOM
    dimensions: List[str] = Field(default_factory=list)
    filter_expr: Optional[str] = None
    format: str = "number" # number, currency, percentage

class SemanticMetricStore:
    """Semantic metric layer. Default ("_global") namespace is DB-backed; per-session
    namespaces are in-memory and isolated."""

    _instance = None
    _lock = threading.RLock()
    _session_instances: Dict[str, "SemanticMetricStore"] = {}

    def __init__(self, persistent: bool = True):
        self.persistent = persistent
        self.db = MetadataDB.get_instance() if persistent else None
        self._metrics: Dict[str, MetricDefinition] = {}

    @classmethod
    def get_instance(cls) -> "SemanticMetricStore":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(persistent=True)
            return cls._instance

    def register_metric(self, metric: MetricDefinition) -> MetricDefinition:
        with self._lock:
            if self.persistent:
                self.db.save_metric(metric.model_dump())
            else:
                self._metrics[metric.name] = metric
            return metric

    def get_metric(self, metric_name: str) -> Optional[MetricDefinition]:
        with self._lock:
            if self.persistent:
                data = self.db.get_metric(metric_name)
                return MetricDefinition(**data) if data else None
            return self._metrics.get(metric_name)

    def list_metrics(self) -> List[MetricDefinition]:
        with self._lock:
            if self.persistent:
                return [MetricDefinition(**r) for r in self.db.list_metrics()]
            return list(self._metrics.values())

    def compile_query(
        self,
        metric_names: List[str],
        dimensions: Optional[List[str]] = None,
        filters: Optional[str] = None,
        order_by: Optional[str] = None,
        limit: int = 100
    ) -> str:
        """Compile standardized semantic metrics and dimensions into executable DuckDB SQL."""
        if not metric_names:
            raise ValueError("metric_names cannot be empty")

        with self._lock:
            first_m = self.get_metric(metric_names[0])
            if not first_m:
                raise ValueError(f"Metric '{metric_names[0]}' not defined in Semantic Store")
            
            table_name = first_m.table_name

            select_parts = []
            if dimensions:
                for dim in dimensions:
                    select_parts.append(safe_ident(dim))

            for m_name in metric_names:
                m_def = self.get_metric(m_name)
                if not m_def:
                    raise ValueError(f"Metric '{m_name}' not defined in Semantic Store")
                if m_def.table_name != table_name:
                    raise ValueError(f"Cross-table semantic joins not supported in single query: {m_def.table_name} vs {table_name}")
                select_parts.append(f"({safe_predicate(m_def.formula)}) AS {safe_ident(m_name)}")

            sql = f"SELECT {', '.join(select_parts)} FROM {safe_table_ref(table_name)}"

            where_clauses = []
            if filters:
                where_clauses.append(safe_predicate(filters))
            if first_m.filter_expr:
                where_clauses.append(safe_predicate(first_m.filter_expr))

            if where_clauses:
                sql += f" WHERE {' AND '.join(where_clauses)}"

            if dimensions:
                dim_indices = [str(i + 1) for i in range(len(dimensions))]
                sql += f" GROUP BY {', '.join(dim_indices)}"

            if order_by:
                sql += f" ORDER BY {safe_predicate(order_by)}"
            elif metric_names:
                sql += f" ORDER BY {safe_ident(metric_names[0])} DESC"

            sql += f" LIMIT {int(limit)}"
            return sql

def get_semantic_store(session_id: str = "_global") -> SemanticMetricStore:
    with SemanticMetricStore._lock:
        inst = SemanticMetricStore._session_instances.get(session_id)
        if inst is None:
            inst = SemanticMetricStore(persistent=(session_id == "_global"))
            SemanticMetricStore._session_instances[session_id] = inst
        return inst
