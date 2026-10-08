import hashlib
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
    aggregation_type: str = "SUM" # SUM, AVG, COUNT, RATIO, CUSTOM, CUMULATIVE
    # RATIO divides the numerator metric's aggregate by the denominator metric's aggregate.
    numerator_metric: Optional[str] = None
    denominator_metric: Optional[str] = None
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
        self._models: Dict[str, "SemanticModel"] = {}

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
                if dimensions and m_def.dimensions:
                    unknown = [d for d in dimensions if d not in m_def.dimensions]
                    if unknown:
                        raise ValueError(
                            f"Metric '{m_name}' does not declare dimension(s) {unknown}. "
                            f"Declared: {list(m_def.dimensions)}"
                        )
                select_parts.append(f"({safe_predicate(self._formula_sql(m_def))}) AS {safe_ident(m_name)}")

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

    def _formula_sql(self, metric: MetricDefinition) -> str:
        """Aggregate expression. RATIO divides two aggregates; it does not average a row ratio."""
        if (metric.aggregation_type or "").upper() != "RATIO":
            return metric.formula
        num = self.get_metric(metric.numerator_metric or "")
        den = self.get_metric(metric.denominator_metric or "")
        if num is None or den is None:
            raise ValueError(
                f"RATIO metric '{metric.name}' requires numerator_metric and denominator_metric "
                "that are already registered. Each side is aggregated, then the aggregates are divided."
            )
        if (num.aggregation_type or "").upper() == "RATIO" or (den.aggregation_type or "").upper() == "RATIO":
            raise ValueError("RATIO metrics cannot nest other RATIO metrics")
        return f"({num.formula}) / NULLIF(({den.formula}), 0)"

    def metric_version(self, metric_name: str) -> str:
        metric = self.get_metric(metric_name)
        if metric is None:
            raise ValueError(f"Metric '{metric_name}' not defined in Semantic Store")
        raw = "|".join([
            metric.name,
            metric.table_name,
            metric.formula,
            metric.aggregation_type,
            metric.numerator_metric or "",
            metric.denominator_metric or "",
            ",".join(metric.dimensions),
        ])
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def register_model(self, model: "SemanticModel") -> "SemanticModel":
        with self._lock:
            self._models[model.name] = model
            return model

    def list_models(self) -> List["SemanticModel"]:
        with self._lock:
            return list(self._models.values())

    def _model_for_table(self, table_name: str) -> Optional["SemanticModel"]:
        for model in self._models.values():
            if model.table_name == table_name:
                return model
        return None

    def compile_governed(
        self,
        metric_names: List[str],
        dimensions: Optional[List[str]] = None,
        filters: Optional[str] = None,
        order_by: Optional[str] = None,
        limit: int = 100,
    ) -> str:
        """Compile metrics by aggregating each one on its own table, then joining.

        Joins only follow a foreign key toward a primary key, at most two hops.
        A dimension that would require joining into a one-to-many child is rejected,
        because that fan-out changes the metric.
        """
        dimensions = dimensions or []
        if not metric_names:
            raise ValueError("metric_names cannot be empty")
        metrics = []
        for name in metric_names:
            metric = self.get_metric(name)
            if metric is None:
                raise ValueError(f"Metric '{name}' not defined in Semantic Store")
            metrics.append(metric)

        if all(self._model_for_table(m.table_name) is None for m in metrics):
            return self.compile_query(metric_names, dimensions, filters, order_by, limit)

        ctes = []
        for metric in metrics:
            model = self._model_for_table(metric.table_name)
            if model is None:
                raise ValueError(f"Metric '{metric.name}' has no semantic model for table '{metric.table_name}'")
            if metric.aggregation_type.upper() == "CUMULATIVE":
                if dimensions and dimensions != [model.agg_time_dimension]:
                    raise ValueError(
                        f"Cumulative metric '{metric.name}' compiles on the model time spine only"
                    )
                ctes.append(self._cumulative_cte(metric, model))
                continue
            joins = []
            group_exprs = []
            select_dims = []
            for dim in dimensions:
                path = _join_path(model, dim, list(self._models.values()))
                for step in path:
                    if step not in joins:
                        joins.append(step)
                holder = model if not path else path[-1][2]
                select_dims.append(f"{_alias(holder)}.{safe_ident(dim)} AS {safe_ident(dim)}")
                group_exprs.append(f"{_alias(holder)}.{safe_ident(dim)}")
            from_sql = f"{safe_table_ref(model.table_name)} {_alias(model)}"
            for src, entity, dst in joins:
                from_sql += (
                    f" JOIN {safe_table_ref(dst.table_name)} {_alias(dst)}"
                    f" ON {_alias(src)}.{safe_ident(entity.expr)} = {_alias(dst)}.{safe_ident(_primary_expr(dst, entity.name))}"
                )
            where = ""
            if filters:
                where = f" WHERE {safe_predicate(filters)}"
            dim_sql = (", ".join(select_dims) + ", ") if select_dims else ""
            group_sql = f" GROUP BY {', '.join(str(i + 1) for i in range(len(select_dims)))}" if select_dims else ""
            ctes.append(
                f"{safe_ident(metric.name + '_agg')} AS ("
                f"SELECT {dim_sql}({safe_predicate(self._formula_sql(metric))}) AS {safe_ident(metric.name)} "
                f"FROM {from_sql}{where}{group_sql})"
            )

        order_sql = f" ORDER BY {safe_predicate(order_by)}" if order_by else ""
        if len(ctes) == 1 and metrics[0].aggregation_type.upper() == "CUMULATIVE":
            return (
                f"WITH {ctes[0]} SELECT * FROM {safe_ident(metrics[0].name + '_agg')}"
                f"{order_sql} LIMIT {int(limit)}"
            )

        first = metrics[0].name + "_agg"
        select_cols = [safe_ident(d) for d in dimensions]
        select_cols.extend(safe_ident(m.name) for m in metrics)
        sql = "WITH " + ", ".join(ctes)
        sql += f" SELECT {', '.join(select_cols)} FROM {safe_ident(first)} a0"
        for i, metric in enumerate(metrics[1:], start=1):
            cond = " AND ".join(
                f"a0.{safe_ident(d)} IS NOT DISTINCT FROM a{i}.{safe_ident(d)}" for d in dimensions
            ) or "TRUE"
            sql += f" FULL OUTER JOIN {safe_ident(metric.name + '_agg')} a{i} ON {cond}"
        sql += f"{order_sql} LIMIT {int(limit)}"
        return sql

    def _cumulative_cte(self, metric: "MetricDefinition", model: "SemanticModel") -> str:
        if not model.agg_time_dimension:
            raise ValueError(f"Cumulative metric '{metric.name}' requires agg_time_dimension on its model")
        time_col = safe_ident(model.agg_time_dimension)
        return (
            f"{safe_ident(metric.name + '_agg')} AS ("
            f"WITH daily AS ("
            f"SELECT CAST({time_col} AS DATE) AS {safe_ident('metric_time')}, "
            f"({safe_predicate(self._formula_sql(metric))}) AS v "
            f"FROM {safe_table_ref(model.table_name)} GROUP BY 1), "
            f"spine AS ("
            f"SELECT CAST(d AS DATE) AS {safe_ident('metric_time')} FROM generate_series("
            f"(SELECT MIN({safe_ident('metric_time')}) FROM daily), "
            f"(SELECT MAX({safe_ident('metric_time')}) FROM daily), "
            f"INTERVAL 1 DAY) t(d)) "
            f"SELECT spine.{safe_ident('metric_time')}, "
            f"SUM(COALESCE(daily.v, 0)) OVER (ORDER BY spine.{safe_ident('metric_time')}) "
            f"AS {safe_ident(metric.name)} "
            f"FROM spine LEFT JOIN daily USING ({safe_ident('metric_time')}))"
        )


class EntityRef(BaseModel):
    name: str
    type: str  # primary or foreign
    expr: str


class SemanticModel(BaseModel):
    name: str
    table_name: str
    grain: List[str]
    columns: List[str] = Field(default_factory=list)
    entities: List[EntityRef] = Field(default_factory=list)
    agg_time_dimension: Optional[str] = None


def _alias(model: SemanticModel) -> str:
    return safe_ident("_m_" + model.name)


def _primary_expr(model: SemanticModel, entity_name: str) -> str:
    for entity in model.entities:
        if entity.name == entity_name and entity.type == "primary":
            return entity.expr
    raise ValueError(f"Model '{model.name}' has no primary entity '{entity_name}'")


def _join_path(start: SemanticModel, column: str, models: List[SemanticModel], max_hops: int = 2):
    """Foreign-key to primary-key hops only. One-to-many is rejected by omission."""
    if column in start.columns:
        return []
    primary = {}
    for model in models:
        for entity in model.entities:
            if entity.type == "primary":
                primary.setdefault(entity.name, []).append(model)
    found = []

    def walk(model: SemanticModel, hops: list, seen: set):
        if len(hops) >= max_hops:
            return
        for entity in model.entities:
            if entity.type != "foreign":
                continue
            for target in primary.get(entity.name, []):
                if target.name in seen:
                    continue
                step = (model, entity, target)
                path = hops + [step]
                if column in target.columns:
                    found.append(path)
                else:
                    walk(target, path, seen | {target.name})

    walk(start, [], {start.name})
    if len(found) > 1:
        raise ValueError(f"Ambiguous join path to dimension '{column}' ({len(found)} routes)")
    if not found:
        raise ValueError(
            f"Dimension '{column}' is not reachable from '{start.table_name}' within {max_hops} many-to-one hops. "
            "Joining into a one-to-many child is refused because it would fan out the metric."
        )
    return found[0]


def get_semantic_store(session_id: str = "_global") -> SemanticMetricStore:
    with SemanticMetricStore._lock:
        inst = SemanticMetricStore._session_instances.get(session_id)
        if inst is None:
            inst = SemanticMetricStore(persistent=(session_id == "_global"))
            SemanticMetricStore._session_instances[session_id] = inst
        return inst
