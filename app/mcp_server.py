import os
from app.ontology.ontology_engine import get_ontology_engine
import json
from typing import List, Optional, Dict, Any
from fastmcp import FastMCP
from app.cluster.session_manager import SessionManager
from app.connectors.factory import ConnectorFactory
from app.connectors.trace_importer import TraceImporter
from app.catalog.meta_registry import TableAsset as _TA, ColumnMeta as _CM
from app.logging_setup import configure_logging

# MCP 运行在 stdio transport，日志只能写文件或 stderr
# configure_logging() 默认写 stdout 会污染协议流，这里先导入模块让后续代码能用 logger
configure_logging()
from app.operators.eda import run_eda_profile
from app.operators.variance import run_variance_decomposition
from app.operators.correlation import run_correlation_analysis
from app.operators.olap import run_olap_query, run_pivot_table
from app.distributed_ops.dist_driver import DistributedDriverAnalysis
from app.operators.spss.hypothesis import run_spss_hypothesis_test
from app.operators.spss.regression import run_spss_regression
from app.operators.insights.outliers import detect_outliers
from app.operators.insights.trends import detect_trends
from app.operators.insights.dominance import detect_dominance
from app.operators.mining.clustering import run_kmeans_clustering, run_rfm_segmentation
from app.operators.mining.timeseries import run_timeseries_forecast
from app.operators.sandbox import run_duckdb_sql
from app.copilot.insight_engine import discover_insights as _discover_insights
from app.nlg.narrative_builder import NarrativeBuilder
from app.schemas.charts import ChartSpecBuilder

from app.operators.web_analytics.funnel import calculate_funnel
from app.operators.web_analytics.flow import calculate_user_flow
from app.operators.web_analytics.retention import calculate_retention
from app.operators.web_analytics.page_analytics import calculate_page_metrics
from app.operators.web_analytics.trace_replay import get_trace_waterfall, get_session_action_replay

from app.catalog.meta_registry import get_meta_registry, TableAsset, ColumnMeta
from app.catalog.lineage_tracker import get_lineage_tracker
from app.catalog.semantic_store import get_semantic_store, MetricDefinition, SemanticModel, EntityRef
from app.transform.data_cleaner import DataCleaner
from app.transform.materializer import Materializer
from app.transform.pipeline_dag import get_pipeline_engine, DAGModel
from app.retl.destination_sync import DestinationSync
from app.retl.audience_exporter import AudienceExporter
from app.retl.webhook_pusher import WebhookPusher
from app.observability.assertions import DataQualityAssertions
from app.observability.schema_drift import SchemaDrifter

mcp = FastMCP("data-analysis-service")

@mcp.tool(name="connect_and_load_db", description="Connect to PostgreSQL/MySQL/MSSQL/SQLite/File, load data into in-memory session with projection & predicate pushdown. mode='materialize' (ConnectorX, default) or 'scanner' (DuckDB ATTACH + pushdown, PG/MySQL).")
def connect_and_load_db(
    conn_str: str,
    query_or_table: str,
    dataset_name: str,
    session_id: Optional[str] = None,
    select_cols: Optional[List[str]] = None,
    filter_sql: Optional[str] = None,
    partition_col: Optional[str] = None,
    num_partitions: int = 1,
    limit: Optional[int] = None,
    mode: str = "materialize"
) -> str:
    try:
        mgr = SessionManager()
        sess = mgr.get_or_create_session(session_id)
        connector = ConnectorFactory.get_connector(conn_str)
        arrow_table = connector.fetch_to_arrow(
            query_or_table=query_or_table,
            filter_sql=filter_sql,
            select_cols=select_cols,
            partition_col=partition_col,
            num_partitions=num_partitions,
            limit=limit,
            mode=mode,
        )
        meta = sess.register_dataset(dataset_name, arrow_table, {"conn_str": conn_str, "source": query_or_table})
    except (ValueError, FileNotFoundError) as exc:
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)
    
    # Auto-register into Data Catalog
    cat = get_meta_registry(sess.session_id)
    cols = [ColumnMeta(name=c, data_type="UNKNOWN") for c in meta.column_names]
    cat.register_table(TableAsset(
        dataset_name=dataset_name,
        display_name=dataset_name,
        description=f"Imported from {conn_str}",
        row_count=meta.row_count,
        column_count=meta.column_count,
        columns=cols,
        tags=["imported", "raw"]
    ))

    return json.dumps({
        "status": "success",
        "session_id": sess.session_id,
        "dataset_name": dataset_name,
        "row_count": meta.row_count,
        "column_count": meta.column_count,
        "columns": meta.column_names,
        "memory_bytes": meta.memory_bytes,
        "summary": f"Successfully loaded {meta.row_count:,} rows across {meta.column_count} columns into session '{sess.session_id}' (table '{dataset_name}')."
    }, ensure_ascii=False)

@mcp.tool(name="eda_profile", description="Run comprehensive EDA data profiling, distribution statistics, and data quality scoring. Tables over 100,000 rows label distinct_count_method and quantile_method as approximate. skewness, kurtosis, and std are null when the moment is undefined, not 0. When quantile_method is quantile_cont, p50 is also quantile_cont.")
def eda_profile(session_id: str, dataset_name: str) -> str:
    res = run_eda_profile(session_id, dataset_name)
    summary = NarrativeBuilder.generate_eda_narrative(res)
    return json.dumps({
        "status": "success",
        "summary": summary,
        "quality_score": res.get("quality_score"),
        "total_rows": res.get("total_rows"),
        "columns": res.get("columns")
    }, ensure_ascii=False)

@mcp.tool(name="driver_attribution_analysis", description="Drill a metric change by dimension. SUM uses an additive contribution that closes and a Sun-Shapley average over dimension order. Other aggregations leave sun_shapley null. rate_col + volume_col returns Laspeyres on the first dimension only, plus a two-ordering Sun-Shapley of rate and volume.")
def driver_attribution_analysis(
    session_id: str,
    dataset_name: str,
    target_metric: str,
    dimension_path: List[str],
    base_filter: str,
    current_filter: str,
    agg_func: str = "SUM",
    top_k: int = 5,
    rate_col: Optional[str] = None,
    volume_col: Optional[str] = None,
) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    res = DistributedDriverAnalysis.analyze_driver(
        con=con,
        table_name=dataset_name,
        target_metric=target_metric,
        dimension_path=dimension_path,
        base_filter=base_filter,
        current_filter=current_filter,
        agg_func=agg_func,
        top_k=top_k,
        rate_col=rate_col,
        volume_col=volume_col,
    )
    summary = NarrativeBuilder.generate_driver_narrative(res)
    chart_data = []
    if res.get("hierarchy"):
        first_layer = res["hierarchy"][0].get("branches", [])
        chart_data = [{"category": b["dimension_value"], "diff": b["diff_value"]} for b in first_layer]
    chart_spec = ChartSpecBuilder.build_waterfall_chart(chart_data, "category", "diff")
    return json.dumps({
        "status": "success",
        "summary": summary,
        "method": res.get("method"),
        "orderings_used": res.get("orderings_used"),
        "sun_shapley": res.get("sun_shapley"),
        "driver_hierarchy": res.get("hierarchy"),
        "chart_spec": chart_spec,
        "evidence": res.get("evidence"),
    }, ensure_ascii=False)

@mcp.tool(name="spss_hypothesis_test", description="Execute hypothesis tests: independent_t_test, paired_t_test, one_way_anova, two_way_anova (requires factor_b), chi_square, mann_whitney. one_way_anova and two_way_anova include statistics.variance_decomposition. mann_whitney errors unless there are exactly 2 groups. More than 5,000,000 scanned cells returns 请先聚合再检验.")
def spss_hypothesis_test(
    session_id: str,
    dataset_name: str,
    test_type: str,
    dependent_var: str,
    group_var: str,
    alpha: float = 0.05,
    factor_b: Optional[str] = None,
) -> str:
    res = run_spss_hypothesis_test(
        session_id, dataset_name, test_type, dependent_var, group_var, alpha, factor_b=factor_b
    )
    summary = NarrativeBuilder.generate_spss_narrative(res)
    return json.dumps({
        "status": "success",
        "summary": summary,
        "statistics": res
    }, ensure_ascii=False)

@mcp.tool(name="variance_decomposition", description="Decompose a numeric metric across categorical dimensions. Between-group and within-group sums of squares close. sun_shapley averages sequential increments over dimension order (at most 4 dimensions, 24 orderings). An interaction term is returned only for exactly two dimensions when the design is balanced.")
def variance_decomposition(
    session_id: str,
    dataset_name: str,
    metric: str,
    dimensions: List[str],
    filters: Optional[str] = None,
) -> str:
    res = run_variance_decomposition(session_id, dataset_name, metric, dimensions, filters)
    return json.dumps({"status": "success", "variance_decomposition": res}, ensure_ascii=False)

@mcp.tool(name="spss_regression_analysis", description="Run OLS or Logistic regression with full diagnostic battery (R2, F-test, VIF, DW residual test).")
def spss_regression_analysis(
    session_id: str,
    dataset_name: str,
    dependent_var: str,
    independent_vars: List[str],
    model_type: str = "ols"
) -> str:
    res = run_spss_regression(session_id, dataset_name, dependent_var, independent_vars, model_type)
    summary = NarrativeBuilder.generate_regression_narrative(res)
    return json.dumps({
        "status": "success",
        "summary": summary,
        "model_report": res
    }, ensure_ascii=False)

@mcp.tool(name="detect_automated_insights", description="Detect anomaly outliers, temporal change points, and Gini dominance patterns. outlier_method is z_score, iqr, or isolation_forest. group_col is passed only to the trend action. top_k limits outliers and dominance.")
def detect_automated_insights(
    session_id: str,
    dataset_name: str,
    metric: str,
    category_col: Optional[str] = None,
    time_col: Optional[str] = None,
    outlier_method: str = "z_score",
    threshold: float = 3.0,
    dimension_cols: Optional[List[str]] = None,
    top_k: int = 10,
    group_col: Optional[str] = None,
) -> str:
    insights = {}
    if metric:
        insights["outliers"] = detect_outliers(
            session_id, dataset_name, metric,
            dimension_cols=dimension_cols,
            method=outlier_method,
            threshold=threshold,
            top_k=top_k,
        )
    if category_col and metric:
        insights["dominance"] = detect_dominance(
            session_id, dataset_name, category_col, metric, top_k=top_k
        )
    if time_col and metric:
        insights["trends"] = detect_trends(
            session_id, dataset_name, time_col, metric, group_col=group_col
        )

    return json.dumps({"status": "success", "insights": insights}, ensure_ascii=False)

@mcp.tool(name="memory_olap_aggregation", description="Fast multi-dimensional OLAP aggregation (Rollup/Cube/Slice&Dice) in memory.")
def memory_olap_aggregation(
    session_id: str,
    dataset_name: str,
    dimensions: List[str],
    metrics: List[str],
    agg_funcs: Optional[List[str]] = None,
    filters: Optional[str] = None,
    rollup: bool = False,
    cube: bool = False,
    order_by: Optional[str] = None,
    limit: int = 100
) -> str:
    res = run_olap_query(
        session_id, dataset_name, dimensions, metrics, agg_funcs, filters,
        rollup=rollup, cube=cube, order_by=order_by, limit=limit,
    )
    return json.dumps({"status": "success", "result": res}, ensure_ascii=False)

@mcp.tool(name="duckdb_sql_sandbox", description="Execute read-only SQL directly against DuckDB in-memory session.")
def duckdb_sql_sandbox(session_id: str, sql_query: str, limit: int = 100) -> str:
    res = run_duckdb_sql(session_id, sql_query, limit)
    return json.dumps({"status": "success", "result": res}, ensure_ascii=False)

@mcp.tool(name="correlation_analysis", description="Compute a Pearson/Spearman correlation matrix and surface strongly-correlated column pairs. When DATA_AGENT_RAY_ENABLED is set, a large Pearson scan merges hash partitions and records the backend in evidence caveats.")
def correlation_analysis(session_id: str, dataset_name: str, columns: Optional[List[str]] = None, method: str = "pearson", group_col: Optional[str] = None) -> str:
    res = run_correlation_analysis(session_id, dataset_name, columns, method, group_col=group_col)
    return json.dumps({"status": "success", "correlation": res}, ensure_ascii=False)

@mcp.tool(name="pivot_table", description="Build a multi-dimensional pivot table (rows x columns aggregated by a measure).")
def pivot_table(session_id: str, dataset_name: str, rows: List[str], columns: str, values: str, agg_func: str = "SUM", filters: Optional[str] = None, limit: int = 100) -> str:
    res = run_pivot_table(session_id, dataset_name, rows, columns, values, agg_func, filters, limit)
    return json.dumps({"status": "success", "pivot": res}, ensure_ascii=False)

@mcp.tool(name="kmeans_clustering", description="KMeans clustering with optional automatic k selection (silhouette) over feature columns.")
def kmeans_clustering(session_id: str, dataset_name: str, feature_cols: List[str], n_clusters: Optional[int] = None, auto_k_range: Optional[List[int]] = None) -> str:
    res = run_kmeans_clustering(session_id, dataset_name, feature_cols, n_clusters, auto_k_range or [2, 6])
    return json.dumps({"status": "success", "clustering": res}, ensure_ascii=False)

@mcp.tool(name="rfm_segmentation", description="RFM (Recency/Frequency/Monetary) customer value segmentation.")
def rfm_segmentation(session_id: str, dataset_name: str, user_col: str, date_col: str, amount_col: str) -> str:
    res = run_rfm_segmentation(session_id, dataset_name, user_col, date_col, amount_col)
    return json.dumps({"status": "success", "rfm": res}, ensure_ascii=False)

@mcp.tool(name="timeseries_forecast", description="Time-series forecast (ARIMA-family) for a value column over a horizon. chart_spec is a Vega-Lite line with a 95% interval band built from historical_preview and forecasts.")
def timeseries_forecast(session_id: str, dataset_name: str, time_col: str, value_col: str, horizon: int = 12, model_type: str = "arima") -> str:
    res = run_timeseries_forecast(session_id, dataset_name, time_col, value_col, horizon, model_type)
    chart_spec = ChartSpecBuilder.build_time_series_forecast_chart(
        res.get("historical_preview") or [],
        res.get("forecasts") or [],
        time_col,
        value_col,
    )
    return json.dumps({"status": "success", "forecast": res, "chart_spec": chart_spec}, ensure_ascii=False)

@mcp.tool(name="discover_insights", description="Automated insight discovery: orchestrates Analysis Actions (anomaly/correlation/dominance/trend) into ranked insights, an Insight Graph, and a data-story narrative. Rank is severity unless DATA_AGENT_LLM_BASE_URL is set, in which case the endpoint reorders ids from evidence fields and falls back to severity. Optional intent biases which actions run.")
def discover_insights(session_id: str, dataset_name: str, intent: Optional[str] = None, target_metric: Optional[str] = None, category_col: Optional[str] = None, time_col: Optional[str] = None, max_insights: int = 8) -> str:
    res = _discover_insights(session_id, dataset_name, intent=intent, target_metric=target_metric, category_col=category_col, time_col=time_col, max_insights=max_insights)
    return json.dumps({"status": "success", "insight_report": res}, ensure_ascii=False)

# ---------------- Trace Ingestion (Path B) ----------------

@mcp.tool(name="import_traces", description="Ingest trace/telemetry data (OTLP JSON, span JSON/NDJSON array, or CSV/Parquet) as a data source into an in-memory session table, so the full MDS pipeline (clean/model/EDA/OLAP/SPSS/funnel/waterfall/quality/reverse-ETL) can run on it — the same engine as the DB-connector path.")
def import_traces(
    source: Optional[str] = None,
    dataset_name: str = "traces",
    session_id: Optional[str] = None,
    fmt: Optional[str] = None,
    records: Optional[List[Dict[str, Any]]] = None,
) -> str:
    mgr = SessionManager()
    sess = mgr.get_or_create_session(session_id)
    arrow_table = TraceImporter.load_source(source=source, records=records, fmt=fmt)
    meta = sess.register_dataset(dataset_name, arrow_table, {"source": source, "kind": "trace"})

    cat = get_meta_registry(sess.session_id)
    cols = [_CM(name=c, data_type="UNKNOWN") for c in meta.column_names]
    cat.register_table(_TA(
        dataset_name=dataset_name, display_name=dataset_name,
        description=f"Trace data imported from {source}",
        row_count=meta.row_count, column_count=meta.column_count,
        columns=cols, tags=["trace", "imported"]
    ))
    return json.dumps({
        "status": "success",
        "session_id": sess.session_id,
        "dataset_name": dataset_name,
        "row_count": meta.row_count,
        "columns": meta.column_names,
        "summary": f"Imported {meta.row_count:,} trace spans/events into session '{sess.session_id}' (table '{dataset_name}')."
    }, ensure_ascii=False)

# ---------------- Trace / Web Analytics (on a session-resident table) ----------------

@mcp.tool(name="analyze_conversion_funnel", description="Calculate sequential conversion funnel, drop-off and step conversion over a session-resident trace/event table. chart_spec is a Vega-Lite bar of step user counts.")
def analyze_conversion_funnel(session_id: str, dataset_name: str, steps: List[str], date_from: Optional[str] = None, date_to: Optional[str] = None) -> str:
    res = calculate_funnel(session_id, dataset_name, steps, date_from, date_to)
    chart_spec = ChartSpecBuilder.build_funnel_chart(res.get("steps") or [])
    return json.dumps({"status": "success", "funnel": res, "chart_spec": chart_spec}, ensure_ascii=False)

@mcp.tool(name="analyze_user_flow", description="Calculate page navigation transition matrix and an ECharts Sankey option over a session-resident trace/event table.")
def analyze_user_flow(session_id: str, dataset_name: str, limit_paths: int = 15) -> str:
    res = calculate_user_flow(session_id, dataset_name, limit_paths=limit_paths)
    chart_spec = ChartSpecBuilder.build_sankey_chart(res.get("nodes") or [], res.get("links") or [])
    return json.dumps({"status": "success", "user_flow": res, "chart_spec": chart_spec}, ensure_ascii=False)

@mcp.tool(name="analyze_cohort_retention", description="Calculate N-day cohort retention grid over a session-resident trace/event table. chart_spec is a Vega-Lite heatmap of day rates.")
def analyze_cohort_retention(session_id: str, dataset_name: str, days: int = 7) -> str:
    res = calculate_retention(session_id, dataset_name, days=days)
    chart_spec = ChartSpecBuilder.build_retention_heatmap(res.get("retention_matrix") or [])
    return json.dumps({"status": "success", "retention": res, "chart_spec": chart_spec}, ensure_ascii=False)

@mcp.tool(name="analyze_page_performance", description="Calculate PV/UV and average dwell by page path over a session-resident trace/event table.")
def analyze_page_performance(session_id: str, dataset_name: str, limit: int = 20) -> str:
    res = calculate_page_metrics(session_id, dataset_name, limit=limit)
    return json.dumps({"status": "success", "page_metrics": res}, ensure_ascii=False)

@mcp.tool(name="inspect_trace_and_replay", description="Retrieve an OpenTelemetry span waterfall (by trace_id) or a breadcrumb replay timeline (by telemetry session) from a session-resident trace table.")
def inspect_trace_and_replay(session_id: str, dataset_name: str, trace_id: Optional[str] = None, telemetry_session_id: Optional[str] = None) -> str:
    result = {}
    if trace_id:
        result["waterfall"] = get_trace_waterfall(session_id, dataset_name, trace_id)
    if telemetry_session_id:
        result["replay"] = get_session_action_replay(session_id, dataset_name, telemetry_session_id)
    return json.dumps({"status": "success", "data": result}, ensure_ascii=False)

# ---------------- Modern Data Stack (MDS) Tools ----------------

@mcp.tool(name="query_semantic_metric", description="Query standardized business metrics from Semantic Metric Store with auto-compiled SQL.")
def query_semantic_metric(
    session_id: str,
    metric_names: List[str],
    dimensions: Optional[List[str]] = None,
    filters: Optional[str] = None,
    order_by: Optional[str] = None,
    limit: int = 100
) -> str:
    store = get_semantic_store(session_id)
    sql = store.compile_governed(metric_names, dimensions, filters, order_by=order_by, limit=limit)
    res = run_duckdb_sql(session_id, sql, limit=limit, governed=True)
    versions = {name: store.metric_version(name) for name in metric_names}
    return json.dumps({"status": "success", "compiled_sql": sql, "result": res, "governed": True, "metric_versions": versions}, ensure_ascii=False)

@mcp.tool(name="register_semantic_metric", description="Register a metric formula on a session table. On the single-table compile path, a non-empty dimension list is a whitelist; an empty list does not restrict the caller. A registered semantic model uses the governed join path.")
def register_semantic_metric(
    session_id: str,
    name: str,
    table_name: str,
    formula: str,
    aggregation_type: str = "SUM",
    dimensions: Optional[List[str]] = None,
    display_name: Optional[str] = None,
    description: str = "",
    numerator_metric: Optional[str] = None,
    denominator_metric: Optional[str] = None,
) -> str:
    metric = MetricDefinition(
        name=name,
        display_name=display_name,
        description=description,
        table_name=table_name,
        formula=formula,
        aggregation_type=aggregation_type,
        dimensions=dimensions or [],
        numerator_metric=numerator_metric,
        denominator_metric=denominator_metric,
    )
    get_semantic_store(session_id).register_metric(metric)
    return json.dumps({"status": "success", "metric": metric.model_dump()}, ensure_ascii=False)

@mcp.tool(name="list_semantic_metrics", description="List metric definitions registered in this session.")
def list_semantic_metrics(session_id: str) -> str:
    metrics = [m.model_dump() for m in get_semantic_store(session_id).list_metrics()]
    return json.dumps({"status": "success", "metrics": metrics}, ensure_ascii=False)

@mcp.tool(name="register_semantic_model", description="Register a semantic model: grain, columns, and many-to-one entities. Joins follow a foreign key toward a primary key, at most two hops.")
def register_semantic_model(
    session_id: str,
    name: str,
    table_name: str,
    grain: List[str],
    columns: Optional[List[str]] = None,
    entities: Optional[List[Dict[str, str]]] = None,
    agg_time_dimension: Optional[str] = None,
) -> str:
    model = SemanticModel(
        name=name,
        table_name=table_name,
        grain=grain,
        columns=columns or [],
        entities=[EntityRef(**entity) for entity in (entities or [])],
        agg_time_dimension=agg_time_dimension,
    )
    get_semantic_store(session_id).register_model(model)
    return json.dumps({"status": "success", "model": model.model_dump()}, ensure_ascii=False)

@mcp.tool(name="list_session_datasets", description="List datasets registered in the session, with row counts and redacted source info.")
def list_session_datasets(session_id: str) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    rows = []
    for name, meta in sess.datasets.items():
        rows.append({
            "name": name,
            "row_count": meta.row_count,
            "column_count": meta.column_count,
            "columns": meta.column_names,
            "memory_bytes": meta.memory_bytes,
            "source": meta.source_info,
        })
    return json.dumps({"status": "success", "datasets": rows}, ensure_ascii=False)

@mcp.tool(name="execute_data_cleaning", description="Clean dirty data: deduplicate, fill missing values (mean/median/mode/constant), and clip outliers.")
def execute_data_cleaning(
    session_id: str,
    source_table: str,
    target_table: str,
    dedup_keys: Optional[List[str]] = None,
    fillna_rules: Optional[Dict[str, Any]] = None,
    outlier_clip_cols: Optional[Dict[str, Dict[str, float]]] = None
) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    res = DataCleaner.clean_table(con, source_table, target_table, dedup_keys, fillna_rules, outlier_clip_cols)
    return json.dumps({"status": "success", "cleaning_result": res}, ensure_ascii=False)

@mcp.tool(name="create_wide_table", description="Join a fact table to dimension tables into one wide table. Returns wide_table_name, row_count, and columns.")
def create_wide_table(
    session_id: str,
    target_name: str,
    fact_table: str,
    dimension_joins: List[Dict[str, Any]],
) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    try:
        res = Materializer.create_wide_table(sess.get_duckdb_conn(), target_name, fact_table, dimension_joins)
    except (ValueError, FileNotFoundError) as exc:
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)
    return json.dumps({"status": "success", "wide_table": res}, ensure_ascii=False)

@mcp.tool(name="run_dag_pipeline", description="Execute a dbt-style DAG. Models in the same stage run one after another on the session connection, not concurrently.")
def run_dag_pipeline(session_id: str) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    pipe = get_pipeline_engine(session_id)
    res = pipe.run_pipeline(con)
    return json.dumps({"status": "success", "pipeline_execution": res}, ensure_ascii=False)

@mcp.tool(name="reverse_sync_destination", description="Reverse ETL: sync analytical table/RFM scores back to target database or file.")
def reverse_sync_destination(
    session_id: str,
    source_table: str,
    dest_conn_str: str,
    dest_table_name: str,
    mode: str = "replace",
    chunk_size: int = 50000,
) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    try:
        res = DestinationSync.sync_table_to_destination(
            con, source_table, dest_conn_str, dest_table_name, mode, chunk_size=chunk_size,
        )
    except (ValueError, FileNotFoundError) as exc:
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)
    return json.dumps({"status": "success", "sync_result": res}, ensure_ascii=False)

@mcp.tool(name="export_audience_cohort", description="Export an audience segment to JSON or CSV. total_audience_count is the filtered total. exported_count is the returned page. truncated is true when the page is shorter than the total.")
def export_audience_cohort(
    session_id: str,
    source_table: str,
    filter_sql: Optional[str] = None,
    export_columns: Optional[List[str]] = None,
    format_type: str = "json",
    limit: int = 1000
) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    res = AudienceExporter.export_cohort(con, source_table, filter_sql, export_columns, format_type, limit)
    return json.dumps({"status": "success", "audience": res}, ensure_ascii=False)

@mcp.tool(name="send_operational_webhook_alert", description="Send an alert. feishu is a post card, dingtalk and slack have their own bodies. wecom, wechat, weixin, qywx, wxwork, and wechat_work send WeCom markdown. Any other platform sends generic JSON. A failed send is status FAILED and still includes simulated_payload.")
def send_operational_webhook_alert(
    webhook_url: str,
    title: str,
    message: str,
    platform: str = "generic",
    extra_metrics: Optional[Dict[str, Any]] = None
) -> str:
    res = WebhookPusher.send_alert(webhook_url, title, message, platform, extra_metrics)
    return json.dumps({"status": "success", "alert_result": res}, ensure_ascii=False)

@mcp.tool(name="assert_data_quality", description="Run Great-Expectations style declarative data quality assertions suite (nulls, uniqueness, range, rows).")
def assert_data_quality(session_id: str, table: str, rules: List[Dict[str, Any]]) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    res = DataQualityAssertions.run_suite(con, table, rules)
    return json.dumps({"status": "success", "quality_report": res}, ensure_ascii=False)

@mcp.tool(name="detect_table_schema_drift", description="Detect column additions, removals, and type alterations against baseline schema.")
def detect_table_schema_drift(session_id: str, table: str, baseline_schema: Dict[str, str]) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    res = SchemaDrifter.detect_drift(con, table, baseline_schema)
    return json.dumps({"status": "success", "drift_report": res}, ensure_ascii=False)


# ---------------- Palantir-Style Agentic Ontology Tools ----------------

@mcp.tool(name="ontology_list_schema", description="List business entities (ObjectTypes), relation graphs (LinkTypes), and available actions (ActionTypes).")
def ontology_list_schema() -> str:
    engine = get_ontology_engine()
    summary = engine.get_ontology_schema_summary()
    return json.dumps({"status": "success", "ontology_schema": summary}, ensure_ascii=False)

@mcp.tool(name="ontology_query_objects", description="Query business entity instances (e.g. Customers, Orders, Devices) with property projections and filters.")
def ontology_query_objects(
    session_id: str,
    object_type: str,
    filters: Optional[str] = None,
    properties: Optional[List[str]] = None,
    limit: int = 50
) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    engine = get_ontology_engine()
    res = engine.query_object_instances(con, object_type, filters, properties, limit)
    return json.dumps({"status": "success", "data": res}, ensure_ascii=False)

@mcp.tool(name="ontology_traverse_links", description="Graph-traverse from a source entity instance along relation links. link_path and max_hops are passed through. The traversal includes hop_details and truncated.")
def ontology_traverse_links(
    session_id: str,
    source_object_type: str,
    source_instance_id: str,
    link_name: str,
    limit: int = 50,
    link_path: Optional[List[str]] = None,
    max_hops: int = 4,
) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    engine = get_ontology_engine()
    try:
        res = engine.traverse_links(
            con, source_object_type, source_instance_id, link_name, limit,
            link_path=link_path, max_hops=max_hops,
        )
    except (ValueError, FileNotFoundError) as exc:
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)
    return json.dumps({"status": "success", "traversal": res}, ensure_ascii=False)

@mcp.tool(name="ontology_entity_graph", description="Return the ontology entity graph: nodes, edges, and broken_edges whose endpoints are not registered.")
def ontology_entity_graph() -> str:
    graph = get_ontology_engine().entity_graph()
    return json.dumps({"status": "success", "entity_graph": graph}, ensure_ascii=False)

@mcp.tool(name="ontology_execute_action", description="Execute an atomic business action on an entity instance with audit logging. dry_run defaults to true so a tool call previews the action before it writes. A webhook push that returns FAILED is audited as FAILED even when the result still carries simulated_payload.")
def ontology_execute_action(
    session_id: str,
    action_name: str,
    instance_id: str,
    parameters: Dict[str, Any],
    dry_run: bool = True
) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    engine = get_ontology_engine()
    try:
        audit = engine.execute_action(con, action_name, instance_id, parameters, dry_run)
    except (ValueError, FileNotFoundError) as exc:
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)
    return json.dumps({"status": "success", "action_audit": audit}, ensure_ascii=False)


@mcp.tool(name="import_excel_or_csv", description="Ingest .xlsx or CSV into a session. Omitting sheet_name reads the first worksheet. A sheet name that is not in the workbook is an error. Legacy .xls is rejected.")
def import_excel_or_csv(
    file_path: str,
    dataset_name: str,
    session_id: Optional[str] = None,
    sheet_name: Optional[str] = None,
    limit: Optional[int] = None
) -> str:
    try:
        mgr = SessionManager()
        sess = mgr.get_or_create_session(session_id)
        conn_str = f"file://{file_path}"
        connector = ConnectorFactory.get_connector(conn_str)
        arrow_table = connector.fetch_to_arrow(
            query_or_table=sheet_name or "",
            limit=limit
        )
        meta = sess.register_dataset(dataset_name, arrow_table, {"source_file": file_path})
    except (ValueError, FileNotFoundError) as exc:
        return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)

    # Register into Catalog
    cat = get_meta_registry(sess.session_id)
    cols = [ColumnMeta(name=c, data_type="UNKNOWN") for c in meta.column_names]
    cat.register_table(TableAsset(
        dataset_name=dataset_name,
        display_name=dataset_name,
        description=f"Imported from {os.path.basename(file_path)}",
        row_count=meta.row_count,
        column_count=meta.column_count,
        columns=cols,
        tags=["file_import", "excel_csv"]
    ))

    return json.dumps({
        "status": "success",
        "session_id": sess.session_id,
        "dataset_name": dataset_name,
        "row_count": meta.row_count,
        "column_count": meta.column_count,
        "columns": meta.column_names,
        "memory_bytes": meta.memory_bytes,
        "summary": f"Successfully loaded {os.path.basename(file_path)} with {meta.row_count:,} rows and {meta.column_count} columns into session '{sess.session_id}'."
    }, ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()
