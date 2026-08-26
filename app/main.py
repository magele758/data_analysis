from app.ontology.ontology_engine import get_ontology_engine
from app.ontology.object_type import ObjectType
from app.ontology.link_type import LinkType
from app.ontology.action_type import ActionType
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Request, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.config import settings
from app.logging_setup import configure_logging, set_request_id, get_request_id
from app.security import require_api_key, validate_auth_config
from app.schemas.requests import (
    ConnectDBRequest, EDARequest, CorrelationRequest, OLAPRequest, PivotRequest,
    DriverAnalysisRequest, HypothesisTestRequest, RegressionRequest, OutliersRequest,
    TrendsRequest, DominanceRequest, ClusteringRequest, TimeSeriesRequest, SQLSandboxRequest
)
from app.schemas.responses import AnalysisResponse
from app.cluster.session_manager import SessionManager
from app.connectors.factory import ConnectorFactory
from app.connectors.trace_importer import TraceImporter
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
from app.operators.web_analytics.trace_replay import get_trace_waterfall, get_session_action_replay, list_recent_sessions

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

configure_logging()
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Validated at startup rather than import so the failure surfaces as a
    # refused boot with a readable error. Raises when auth is required but no
    # keys are configured. See app/security.py.
    validate_auth_config()
    logger.info(
        "%s v%s starting (auth_required=%s, keys_configured=%d)",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.REQUIRE_AUTH,
        len(settings.api_key_list),
    )
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="High-performance, stateless, distributed in-memory data analysis and automated insight engine for AI Agents.",
    # One registration covers every /api/v1 route, including routers included
    # later. require_api_key exempts non-/api/v1 paths itself.
    dependencies=[Depends(require_api_key)],
)

# Explicit origins only: allow_credentials with allow_origins=["*"] is rejected
# by browsers, so the old config was both over-permissive and non-functional.
_cors_origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # Safe only because the origin list is explicit and never "*".
    allow_credentials=True,
    # dashboard.js uses GET and POST; OPTIONS is the preflight itself.
    allow_methods=["GET", "POST", "OPTIONS"],
    # Content-Type: dashboard.js + tracker.js JSON posts. X-API-Key: auth.
    # X-Request-ID: lets a caller supply its own correlation id.
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

# Static assets for the pipeline dashboard. Telemetry collection is NOT part of
# this service; it lives in examples/telemetry-collector-demo and feeds data in
# via the trace import endpoint below.
os.makedirs("app/web/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Assign a request id, log the outcome, and echo the id back.

    Logs method/path/status/duration only. Never the body, query secrets, or the
    X-API-Key value.
    """
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    set_request_id(request_id)
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started) * 1000
        # exc_info=True gives the traceback in the log, never in the response.
        logger.error(
            "%s %s failed after %.2fms",
            request.method,
            request.url.path,
            duration_ms,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "detail": "Internal server error",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "%s %s -> %d in %.2fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Generic 500 carrying only the request id, never the stack trace."""
    request_id = get_request_id()
    logger.error(
        "Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "detail": "Internal server error",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


@app.get("/health")
def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}

@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    with open("app/web/templates/dashboard.html", "r", encoding="utf-8") as f:
        return f.read()

# ----------------- Core IQuery Analysis Endpoints -----------------

@app.post("/api/v1/connect", response_model=AnalysisResponse)
def connect_db(req: ConnectDBRequest):
    mgr = SessionManager()
    sess = mgr.get_or_create_session(req.session_id)
    connector = ConnectorFactory.get_connector(req.conn_str)
    arrow_table = connector.fetch_to_arrow(
        query_or_table=req.query_or_table,
        filter_sql=req.filter_sql,
        select_cols=req.select_cols,
        partition_col=req.partition_col,
        num_partitions=req.num_partitions,
        limit=req.limit
    )
    meta = sess.register_dataset(req.dataset_name, arrow_table, {"conn_str": req.conn_str, "source": req.query_or_table})
    
    # Auto-register into Data Catalog
    cat = get_meta_registry()
    cols = [ColumnMeta(name=c, data_type="UNKNOWN") for c in meta.column_names]
    cat.register_table(TableAsset(
        dataset_name=req.dataset_name,
        display_name=req.dataset_name,
        description=f"Loaded from {req.conn_str}",
        row_count=meta.row_count,
        column_count=meta.column_count,
        columns=cols,
        tags=["raw", "imported"]
    ))

    return AnalysisResponse(
        status="success",
        session_id=sess.session_id,
        summary_text=f"Successfully loaded dataset '{req.dataset_name}' with {meta.row_count:,} rows into session '{sess.session_id}'.",
        metadata={"row_count": meta.row_count, "columns": meta.column_names, "memory_bytes": meta.memory_bytes}
    )

@app.post("/api/v1/tools/eda", response_model=AnalysisResponse)
def api_eda(req: EDARequest):
    res = run_eda_profile(req.session_id, req.dataset_name)
    summary = NarrativeBuilder.generate_eda_narrative(res)
    return AnalysisResponse(
        status="success",
        session_id=req.session_id,
        summary_text=summary,
        statistics=res
    )

@app.post("/api/v1/tools/driver_analysis", response_model=AnalysisResponse)
def api_driver_analysis(req: DriverAnalysisRequest):
    mgr = SessionManager()
    sess = mgr.get_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    con = sess.get_duckdb_conn()
    res = DistributedDriverAnalysis.analyze_driver(
        con=con,
        table_name=req.dataset_name,
        target_metric=req.target_metric,
        dimension_path=req.dimension_path,
        base_filter=req.base_filter,
        current_filter=req.current_filter,
        agg_func=req.agg_func,
        top_k=req.top_k
    )
    summary = NarrativeBuilder.generate_driver_narrative(res)
    chart_data = []
    if res.get("hierarchy"):
        first_layer = res["hierarchy"][0].get("branches", [])
        chart_data = [{"category": b["dimension_value"], "diff": b["diff_value"]} for b in first_layer]
    chart_spec = ChartSpecBuilder.build_waterfall_chart(chart_data, "category", "diff")
    return AnalysisResponse(
        status="success",
        session_id=req.session_id,
        summary_text=summary,
        statistics=res,
        chart_spec=chart_spec
    )

@app.post("/api/v1/tools/spss_test", response_model=AnalysisResponse)
def api_spss_test(req: HypothesisTestRequest):
    res = run_spss_hypothesis_test(
        session_id=req.session_id,
        dataset_name=req.dataset_name,
        test_type=req.test_type,
        dependent_var=req.dependent_var,
        group_var=req.group_var,
        alpha=req.alpha
    )
    summary = NarrativeBuilder.generate_spss_narrative(res)
    return AnalysisResponse(
        status="success",
        session_id=req.session_id,
        summary_text=summary,
        statistics=res
    )

@app.post("/api/v1/tools/spss_regression", response_model=AnalysisResponse)
def api_spss_regression(req: RegressionRequest):
    res = run_spss_regression(
        session_id=req.session_id,
        dataset_name=req.dataset_name,
        dependent_var=req.dependent_var,
        independent_vars=req.independent_vars,
        model_type=req.model_type
    )
    summary = NarrativeBuilder.generate_regression_narrative(res)
    return AnalysisResponse(
        status="success",
        session_id=req.session_id,
        summary_text=summary,
        statistics=res
    )

@app.post("/api/v1/tools/olap", response_model=AnalysisResponse)
def api_olap(req: OLAPRequest):
    res = run_olap_query(
        session_id=req.session_id,
        dataset_name=req.dataset_name,
        dimensions=req.dimensions,
        metrics=req.metrics,
        agg_funcs=req.agg_funcs,
        filters=req.filters,
        rollup=req.rollup,
        cube=req.cube,
        order_by=req.order_by,
        limit=req.limit
    )
    return AnalysisResponse(
        status="success",
        session_id=req.session_id,
        summary_text=f"Aggregated {res['total_records']} multi-dimensional rows.",
        data_preview=res["records"],
        metadata={"columns": res["schema"]}
    )

@app.post("/api/v1/tools/sql", response_model=AnalysisResponse)
def api_sql(req: SQLSandboxRequest):
    res = run_duckdb_sql(req.session_id, req.sql_query, req.limit)
    return AnalysisResponse(
        status="success",
        session_id=req.session_id,
        summary_text=f"SQL executed successfully returning {res['row_count']} rows.",
        data_preview=res["data"],
        metadata={"columns": res["columns"]}
    )

# ----------------- Trace / Web Analytics (on a session-resident table) -----------------
# These run on an imported trace dataset inside an analytical session, the same
# engine the DB-connector path uses. The DB path and the trace path thus share
# one analysis core rather than each maintaining a separate silo.

class FunnelRequest(BaseModel):
    session_id: str
    dataset_name: str
    steps: List[str]
    date_from: Optional[str] = None
    date_to: Optional[str] = None

@app.post("/api/v1/analytics/funnel")
def api_funnel(req: FunnelRequest):
    return calculate_funnel(req.session_id, req.dataset_name, req.steps, req.date_from, req.date_to)

@app.get("/api/v1/analytics/flow")
def api_flow(session_id: str, dataset_name: str, limit: int = 15):
    return calculate_user_flow(session_id, dataset_name, limit_paths=limit)

@app.get("/api/v1/analytics/retention")
def api_retention(session_id: str, dataset_name: str, days: int = 7):
    return calculate_retention(session_id, dataset_name, days=days)

@app.get("/api/v1/analytics/pages")
def api_pages(session_id: str, dataset_name: str, limit: int = 20):
    return calculate_page_metrics(session_id, dataset_name, limit=limit)

@app.get("/api/v1/analytics/trace/{trace_id}")
def api_trace_waterfall(trace_id: str, session_id: str, dataset_name: str):
    return get_trace_waterfall(session_id, dataset_name, trace_id)

@app.get("/api/v1/analytics/replay/{telemetry_session_id}")
def api_session_replay(telemetry_session_id: str, session_id: str, dataset_name: str):
    return get_session_action_replay(session_id, dataset_name, telemetry_session_id)

@app.get("/api/v1/analytics/sessions")
def api_list_sessions(session_id: str, dataset_name: str, limit: int = 20):
    return {"sessions": list_recent_sessions(session_id, dataset_name, limit=limit)}

# ----------------- Modern Data Stack: Catalog & Lineage -----------------

@app.get("/api/v1/catalog/tables")
def api_list_catalog_tables(tag: Optional[str] = None, keyword: Optional[str] = None):
    cat = get_meta_registry()
    return {"tables": cat.list_tables(tag=tag, keyword=keyword)}

@app.post("/api/v1/catalog/tables")
def api_register_catalog_table(asset: TableAsset):
    cat = get_meta_registry()
    return cat.register_table(asset)

@app.get("/api/v1/catalog/lineage")
def api_get_lineage():
    lineage = get_lineage_tracker()
    return lineage.get_lineage_graph()

@app.get("/api/v1/catalog/metrics")
def api_list_semantic_metrics():
    store = get_semantic_store()
    return {"metrics": store.list_metrics()}

@app.post("/api/v1/catalog/metrics")
def api_register_semantic_metric(metric: MetricDefinition):
    store = get_semantic_store()
    return store.register_metric(metric)

class SemanticQueryRequest(BaseModel):
    session_id: str
    metric_names: List[str]
    dimensions: Optional[List[str]] = None
    filters: Optional[str] = None
    order_by: Optional[str] = None
    limit: int = 100

@app.post("/api/v1/catalog/metrics/query")
def api_query_semantic_metrics(req: SemanticQueryRequest):
    store = get_semantic_store()
    sql = store.compile_query(req.metric_names, req.dimensions, req.filters, req.order_by, req.limit)
    res = run_duckdb_sql(req.session_id, sql, limit=req.limit)
    return {"compiled_sql": sql, "data": res["data"], "columns": res["columns"]}

# ----------------- Modern Data Stack: Transform & ELT DAG -----------------

class CleanTableRequest(BaseModel):
    session_id: str
    source_table: str
    target_table: str
    dedup_keys: Optional[List[str]] = None
    fillna_rules: Optional[Dict[str, Any]] = None
    outlier_clip_cols: Optional[Dict[str, Dict[str, float]]] = None

@app.post("/api/v1/transform/clean")
def api_clean_table(req: CleanTableRequest):
    mgr = SessionManager()
    sess = mgr.get_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    con = sess.get_duckdb_conn()
    res = DataCleaner.clean_table(con, req.source_table, req.target_table, req.dedup_keys, req.fillna_rules, req.outlier_clip_cols)
    return res

@app.post("/api/v1/transform/dag/models")
def api_register_dag_model(model: DAGModel):
    pipe = get_pipeline_engine()
    return pipe.register_model(model)

@app.get("/api/v1/transform/dag/models")
def api_list_dag_models():
    pipe = get_pipeline_engine()
    return {"models": pipe.list_models(), "execution_order": pipe.get_execution_order() if pipe.list_models() else []}

@app.post("/api/v1/transform/dag/run")
def api_run_dag_pipeline(session_id: str):
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    con = sess.get_duckdb_conn()
    pipe = get_pipeline_engine()
    return pipe.run_pipeline(con)

# ----------------- Modern Data Stack: Reverse ETL & Activation -----------------

class ReverseSyncRequest(BaseModel):
    session_id: str
    source_table: str
    dest_conn_str: str
    dest_table_name: str
    mode: str = "replace"

@app.post("/api/v1/retl/sync")
def api_reverse_sync(req: ReverseSyncRequest):
    mgr = SessionManager()
    sess = mgr.get_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    con = sess.get_duckdb_conn()
    return DestinationSync.sync_table_to_destination(con, req.source_table, req.dest_conn_str, req.dest_table_name, req.mode)

class AudienceExportRequest(BaseModel):
    session_id: str
    source_table: str
    filter_sql: Optional[str] = None
    export_columns: Optional[List[str]] = None
    format_type: str = "json"
    limit: int = 1000

@app.post("/api/v1/retl/audience")
def api_export_audience(req: AudienceExportRequest):
    mgr = SessionManager()
    sess = mgr.get_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    con = sess.get_duckdb_conn()
    return AudienceExporter.export_cohort(con, req.source_table, req.filter_sql, req.export_columns, req.format_type, req.limit)

class WebhookAlertRequest(BaseModel):
    webhook_url: str
    title: str
    message: str
    platform: str = "generic"
    extra_metrics: Optional[Dict[str, Any]] = None

@app.post("/api/v1/retl/alert")
def api_send_webhook_alert(req: WebhookAlertRequest):
    return WebhookPusher.send_alert(req.webhook_url, req.title, req.message, req.platform, req.extra_metrics)

# ----------------- Modern Data Stack: Observability & Quality -----------------

class QualitySuiteRequest(BaseModel):
    session_id: str
    table: str
    rules: List[Dict[str, Any]]

@app.post("/api/v1/observability/assert")
def api_run_quality_assertions(req: QualitySuiteRequest):
    mgr = SessionManager()
    sess = mgr.get_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    con = sess.get_duckdb_conn()
    return DataQualityAssertions.run_suite(con, req.table, req.rules)

class SchemaDriftRequest(BaseModel):
    session_id: str
    table: str
    baseline_schema: Dict[str, str]

@app.post("/api/v1/observability/drift")
def api_detect_schema_drift(req: SchemaDriftRequest):
    mgr = SessionManager()
    sess = mgr.get_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    con = sess.get_duckdb_conn()
    return SchemaDrifter.detect_drift(con, req.table, req.baseline_schema)

# ----------------- Palantir-Style Agentic Ontology Endpoints -----------------

@app.get("/api/v1/ontology/schema")
def api_get_ontology_schema():
    engine = get_ontology_engine()
    return engine.get_ontology_schema_summary()

@app.get("/api/v1/ontology/objects")
def api_list_ontology_objects():
    engine = get_ontology_engine()
    return {"object_types": engine.list_object_types()}

@app.post("/api/v1/ontology/objects")
def api_register_ontology_object(obj: ObjectType):
    engine = get_ontology_engine()
    return engine.register_object_type(obj)

@app.get("/api/v1/ontology/links")
def api_list_ontology_links():
    engine = get_ontology_engine()
    return {"link_types": engine.list_link_types()}

@app.post("/api/v1/ontology/links")
def api_register_ontology_link(link: LinkType):
    engine = get_ontology_engine()
    return engine.register_link_type(link)

@app.get("/api/v1/ontology/actions")
def api_list_ontology_actions(target_object_type: Optional[str] = None):
    engine = get_ontology_engine()
    return {"action_types": engine.list_action_types(target_object_type=target_object_type)}

@app.post("/api/v1/ontology/actions")
def api_register_ontology_action(action: ActionType):
    engine = get_ontology_engine()
    return engine.register_action_type(action)

class OntologyQueryRequest(BaseModel):
    session_id: str
    object_type: str
    filters: Optional[str] = None
    properties: Optional[List[str]] = None
    limit: int = 50

@app.post("/api/v1/ontology/instances/query")
def api_query_ontology_instances(req: OntologyQueryRequest):
    mgr = SessionManager()
    sess = mgr.get_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    con = sess.get_duckdb_conn()
    engine = get_ontology_engine()
    return engine.query_object_instances(con, req.object_type, req.filters, req.properties, req.limit)

class OntologyTraverseRequest(BaseModel):
    session_id: str
    source_object_type: str
    source_instance_id: Any
    link_name: str
    limit: int = 50

@app.post("/api/v1/ontology/instances/traverse")
def api_traverse_ontology_links(req: OntologyTraverseRequest):
    mgr = SessionManager()
    sess = mgr.get_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    con = sess.get_duckdb_conn()
    engine = get_ontology_engine()
    return engine.traverse_links(con, req.source_object_type, req.source_instance_id, req.link_name, req.limit)

class OntologyActionExecRequest(BaseModel):
    session_id: str
    action_name: str
    instance_id: Any
    parameters: Dict[str, Any]
    dry_run: bool = False

@app.post("/api/v1/ontology/actions/execute")
def api_execute_ontology_action(req: OntologyActionExecRequest):
    mgr = SessionManager()
    sess = mgr.get_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    con = sess.get_duckdb_conn()
    engine = get_ontology_engine()
    return engine.execute_action(con, req.action_name, req.instance_id, req.parameters, req.dry_run)

@app.get("/api/v1/ontology/audit")
def api_list_ontology_audits(limit: int = 50):
    engine = get_ontology_engine()
    return {"audits": engine.list_action_audits(limit=limit)}

# ----------------- Excel & CSV High-Performance Ingestion Endpoints -----------------

@app.post("/api/v1/import/file")
async def api_import_file(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Form(None),
    dataset_name: str = Form("uploaded_dataset"),
    session_id: Optional[str] = Form(None),
    sheet_name: Optional[str] = Form(None),
    limit: Optional[int] = Form(None)
):
    mgr = SessionManager()
    sess = mgr.get_or_create_session(session_id)
    
    target_path = file_path
    if file:
        os.makedirs("data/uploads", exist_ok=True)
        target_path = f"data/uploads/{file.filename}"
        with open(target_path, "wb") as f_out:
            while chunk := await file.read(1024 * 1024 * 5): # 5MB stream chunks
                f_out.write(chunk)

    if not target_path or not os.path.exists(target_path):
        raise HTTPException(status_code=400, detail="Invalid file or file_path provided")

    conn_str = f"file://{target_path}"
    connector = ConnectorFactory.get_connector(conn_str)
    arrow_table = connector.fetch_to_arrow(
        query_or_table=sheet_name or "Sheet1",
        limit=limit
    )

    meta = sess.register_dataset(dataset_name, arrow_table, {"source_file": target_path})

    # Register into Catalog
    cat = get_meta_registry()
    cols = [ColumnMeta(name=c, data_type="UNKNOWN") for c in meta.column_names]
    cat.register_table(TableAsset(
        dataset_name=dataset_name,
        display_name=dataset_name,
        description=f"Imported from {os.path.basename(target_path)}",
        row_count=meta.row_count,
        column_count=meta.column_count,
        columns=cols,
        tags=["file_import", "raw"]
    ))

    return {
        "status": "success",
        "session_id": sess.session_id,
        "dataset_name": dataset_name,
        "row_count": meta.row_count,
        "column_count": meta.column_count,
        "columns": meta.column_names,
        "memory_bytes": meta.memory_bytes,
        "summary": f"Successfully loaded {os.path.basename(target_path)} ({meta.row_count:,} rows, {meta.column_count} cols) into dataset '{dataset_name}'."
    }

# ----------------- Trace Ingestion (Path B): import traces as a data source -----------------

class TraceImportRequest(BaseModel):
    source: Optional[str] = None
    records: Optional[List[Dict[str, Any]]] = None
    dataset_name: str = "traces"
    session_id: Optional[str] = None
    format: Optional[str] = None

@app.post("/api/v1/import/traces")
def api_import_traces(req: TraceImportRequest):
    """Ingest OTLP/JSON/NDJSON/CSV/Parquet trace data into an analytical session.

    Traces become an ordinary session table, so the whole MDS pipeline
    (clean/model/EDA/OLAP/SPSS/funnel/waterfall/quality/reverse-ETL) applies —
    the same engine used by the DB-connector path.
    """
    mgr = SessionManager()
    sess = mgr.get_or_create_session(req.session_id)
    try:
        arrow_table = TraceImporter.load_source(source=req.source, records=req.records, fmt=req.format)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    meta = sess.register_dataset(req.dataset_name, arrow_table, {"source": req.source or "inline", "kind": "trace"})

    cat = get_meta_registry()
    cols = [ColumnMeta(name=c, data_type="UNKNOWN") for c in meta.column_names]
    cat.register_table(TableAsset(
        dataset_name=req.dataset_name,
        display_name=req.dataset_name,
        description=f"Trace data imported from {req.source or 'inline records'}",
        row_count=meta.row_count,
        column_count=meta.column_count,
        columns=cols,
        tags=["trace", "imported"]
    ))

    return {
        "status": "success",
        "session_id": sess.session_id,
        "dataset_name": req.dataset_name,
        "row_count": meta.row_count,
        "column_count": meta.column_count,
        "columns": meta.column_names,
        "summary": f"Imported {meta.row_count:,} trace spans/events into session '{sess.session_id}' (table '{req.dataset_name}'). Ready for the full MDS pipeline."
    }
