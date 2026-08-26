import os
from app.ontology.ontology_engine import get_ontology_engine
import json
from typing import List, Optional, Dict, Any
from fastmcp import FastMCP
from app.cluster.session_manager import SessionManager
from app.connectors.factory import ConnectorFactory
from app.logging_setup import configure_logging

# MCP 运行在 stdio transport，日志只能写文件或 stderr
# configure_logging() 默认写 stdout 会污染协议流，这里先导入模块让后续代码能用 logger
configure_logging()
from app.operators.eda import run_eda_profile
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
from app.nlg.narrative_builder import NarrativeBuilder
from app.schemas.charts import ChartSpecBuilder

from app.operators.web_analytics.funnel import calculate_funnel
from app.operators.web_analytics.flow import calculate_user_flow
from app.operators.web_analytics.retention import calculate_retention
from app.operators.web_analytics.page_analytics import calculate_page_metrics
from app.operators.web_analytics.trace_replay import get_trace_waterfall, get_session_action_replay

from app.catalog.meta_registry import get_meta_registry, TableAsset, ColumnMeta
from app.catalog.lineage_tracker import get_lineage_tracker
from app.catalog.semantic_store import get_semantic_store, MetricDefinition
from app.transform.data_cleaner import DataCleaner
from app.transform.pipeline_dag import get_pipeline_engine, DAGModel
from app.retl.destination_sync import DestinationSync
from app.retl.audience_exporter import AudienceExporter
from app.retl.webhook_pusher import WebhookPusher
from app.observability.assertions import DataQualityAssertions
from app.observability.schema_drift import SchemaDrifter

mcp = FastMCP("data-analysis-service")

@mcp.tool(name="connect_and_load_db", description="Connect to PostgreSQL/MySQL/MSSQL/SQLite/File, load data into in-memory session with projection & predicate pushdown.")
def connect_and_load_db(
    conn_str: str,
    query_or_table: str,
    dataset_name: str,
    session_id: Optional[str] = None,
    select_cols: Optional[List[str]] = None,
    filter_sql: Optional[str] = None,
    partition_col: Optional[str] = None,
    num_partitions: int = 1,
    limit: Optional[int] = None
) -> str:
    mgr = SessionManager()
    sess = mgr.get_or_create_session(session_id)
    connector = ConnectorFactory.get_connector(conn_str)
    arrow_table = connector.fetch_to_arrow(
        query_or_table=query_or_table,
        filter_sql=filter_sql,
        select_cols=select_cols,
        partition_col=partition_col,
        num_partitions=num_partitions,
        limit=limit
    )
    meta = sess.register_dataset(dataset_name, arrow_table, {"conn_str": conn_str, "source": query_or_table})
    
    # Auto-register into Data Catalog
    cat = get_meta_registry()
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

@mcp.tool(name="eda_profile", description="Run comprehensive EDA data profiling, distribution statistics, and data quality scoring.")
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

@mcp.tool(name="driver_attribution_analysis", description="Execute multi-dimensional drill-down & Shapley-style fluctuation attribution for an indicator.")
def driver_attribution_analysis(
    session_id: str,
    dataset_name: str,
    target_metric: str,
    dimension_path: List[str],
    base_filter: str,
    current_filter: str,
    agg_func: str = "SUM",
    top_k: int = 5
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
        top_k=top_k
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
        "driver_hierarchy": res.get("hierarchy"),
        "chart_spec": chart_spec
    }, ensure_ascii=False)

@mcp.tool(name="spss_hypothesis_test", description="Execute SPSS-grade hypothesis tests (independent_t_test, paired_t_test, one_way_anova, chi_square, mann_whitney).")
def spss_hypothesis_test(
    session_id: str,
    dataset_name: str,
    test_type: str,
    dependent_var: str,
    group_var: str,
    alpha: float = 0.05
) -> str:
    res = run_spss_hypothesis_test(session_id, dataset_name, test_type, dependent_var, group_var, alpha)
    summary = NarrativeBuilder.generate_spss_narrative(res)
    return json.dumps({
        "status": "success",
        "summary": summary,
        "statistics": res
    }, ensure_ascii=False)

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

@mcp.tool(name="detect_automated_insights", description="Detect anomaly outliers, temporal change points, and Gini dominance patterns.")
def detect_automated_insights(
    session_id: str,
    dataset_name: str,
    metric: str,
    category_col: Optional[str] = None,
    time_col: Optional[str] = None
) -> str:
    insights = {}
    if metric:
        outliers = detect_outliers(session_id, dataset_name, metric)
        insights["outliers"] = outliers
    if category_col and metric:
        dominance = detect_dominance(session_id, dataset_name, category_col, metric)
        insights["dominance"] = dominance
    if time_col and metric:
        trends = detect_trends(session_id, dataset_name, time_col, metric)
        insights["trends"] = trends

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
    limit: int = 100
) -> str:
    res = run_olap_query(session_id, dataset_name, dimensions, metrics, agg_funcs, filters, rollup=rollup, limit=limit)
    return json.dumps({"status": "success", "result": res}, ensure_ascii=False)

@mcp.tool(name="duckdb_sql_sandbox", description="Execute read-only SQL directly against DuckDB in-memory session.")
def duckdb_sql_sandbox(session_id: str, sql_query: str, limit: int = 100) -> str:
    res = run_duckdb_sql(session_id, sql_query, limit)
    return json.dumps({"status": "success", "result": res}, ensure_ascii=False)

# ---------------- Web Analytics & Trace Tools ----------------

@mcp.tool(name="analyze_conversion_funnel", description="Calculate sequential user conversion funnel, drop-off rates, and step conversion metrics.")
def analyze_conversion_funnel(steps: List[str], date_from: Optional[str] = None, date_to: Optional[str] = None) -> str:
    res = calculate_funnel(steps, date_from, date_to)
    return json.dumps({"status": "success", "funnel": res}, ensure_ascii=False)

@mcp.tool(name="analyze_user_flow", description="Calculate user page navigation transition matrix and Sankey flow diagram nodes/links.")
def analyze_user_flow(limit_paths: int = 15) -> str:
    res = calculate_user_flow(limit_paths=limit_paths)
    return json.dumps({"status": "success", "user_flow": res}, ensure_ascii=False)

@mcp.tool(name="analyze_cohort_retention", description="Calculate N-day user cohort retention grid matrix heatmap.")
def analyze_cohort_retention(days: int = 7) -> str:
    res = calculate_retention(days=days)
    return json.dumps({"status": "success", "retention": res}, ensure_ascii=False)

@mcp.tool(name="analyze_page_performance", description="Calculate Pageview (PV), Unique Visitors (UV), and average stay dwell duration by page path.")
def analyze_page_performance(limit: int = 20) -> str:
    res = calculate_page_metrics(limit=limit)
    return json.dumps({"status": "success", "page_metrics": res}, ensure_ascii=False)

@mcp.tool(name="inspect_trace_and_replay", description="Retrieve OpenTelemetry span waterfall tree or user interaction breadcrumb timeline for session replay.")
def inspect_trace_and_replay(trace_id: Optional[str] = None, session_id: Optional[str] = None) -> str:
    result = {}
    if trace_id:
        result["waterfall"] = get_trace_waterfall(trace_id)
    if session_id:
        result["replay"] = get_session_action_replay(session_id)
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
    store = get_semantic_store()
    sql = store.compile_query(metric_names, dimensions, filters, order_by, limit)
    res = run_duckdb_sql(session_id, sql, limit=limit)
    return json.dumps({"status": "success", "compiled_sql": sql, "result": res}, ensure_ascii=False)

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

@mcp.tool(name="run_dag_pipeline", description="Execute dbt-style topological DAG SQL transformation pipeline.")
def run_dag_pipeline(session_id: str) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    pipe = get_pipeline_engine()
    res = pipe.run_pipeline(con)
    return json.dumps({"status": "success", "pipeline_execution": res}, ensure_ascii=False)

@mcp.tool(name="reverse_sync_destination", description="Reverse ETL: sync analytical table/RFM scores back to target database or file.")
def reverse_sync_destination(
    session_id: str,
    source_table: str,
    dest_conn_str: str,
    dest_table_name: str,
    mode: str = "replace"
) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    res = DestinationSync.sync_table_to_destination(con, source_table, dest_conn_str, dest_table_name, mode)
    return json.dumps({"status": "success", "sync_result": res}, ensure_ascii=False)

@mcp.tool(name="export_audience_cohort", description="Export specific audience segment or churn-risk users to JSON or CSV for CRM/marketing activation.")
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

@mcp.tool(name="send_operational_webhook_alert", description="Send automated operational alerts or attribution findings to Feishu, DingTalk, Slack, or Webhook.")
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

@mcp.tool(name="ontology_traverse_links", description="Graph-traverse from a source entity instance along relation links to discover connected business entities.")
def ontology_traverse_links(
    session_id: str,
    source_object_type: str,
    source_instance_id: str,
    link_name: str,
    limit: int = 50
) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    engine = get_ontology_engine()
    res = engine.traverse_links(con, source_object_type, source_instance_id, link_name, limit)
    return json.dumps({"status": "success", "traversal": res}, ensure_ascii=False)

@mcp.tool(name="ontology_execute_action", description="Execute an atomic business action on an entity instance (e.g. ApplyDiscount, RerouteOrder) with audit logging.")
def ontology_execute_action(
    session_id: str,
    action_name: str,
    instance_id: str,
    parameters: Dict[str, Any],
    dry_run: bool = False
) -> str:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        return json.dumps({"status": "error", "message": f"Session '{session_id}' not found"})
    con = sess.get_duckdb_conn()
    engine = get_ontology_engine()
    audit = engine.execute_action(con, action_name, instance_id, parameters, dry_run)
    return json.dumps({"status": "success", "action_audit": audit}, ensure_ascii=False)


@mcp.tool(name="import_excel_or_csv", description="High-performance ingestion of large Excel (.xlsx, .xls) and CSV files into memory with zero copy.")
def import_excel_or_csv(
    file_path: str,
    dataset_name: str,
    session_id: Optional[str] = None,
    sheet_name: Optional[str] = None,
    limit: Optional[int] = None
) -> str:
    mgr = SessionManager()
    sess = mgr.get_or_create_session(session_id)
    conn_str = f"file://{file_path}"
    connector = ConnectorFactory.get_connector(conn_str)
    arrow_table = connector.fetch_to_arrow(
        query_or_table=sheet_name or "Sheet1",
        limit=limit
    )
    meta = sess.register_dataset(dataset_name, arrow_table, {"source_file": file_path})

    # Register into Catalog
    cat = get_meta_registry()
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
