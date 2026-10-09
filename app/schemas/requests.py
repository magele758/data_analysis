from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ConnectDBRequest(BaseModel):
    conn_str: str = Field(..., description="Target database connection URI (e.g., postgresql://user:pass@host:5432/db)")
    query_or_table: str = Field(..., description="Table name or custom SQL query")
    dataset_name: str = Field(..., description="In-memory dataset alias for this session")
    session_id: Optional[str] = Field(None, description="Existing session ID, or None to create new")
    select_cols: Optional[List[str]] = Field(None, description="Columns to project (projection pushdown)")
    filter_sql: Optional[str] = Field(None, description="WHERE filter condition to pushdown to source DB")
    partition_col: Optional[str] = Field(None, description="Column for parallel partition loading")
    num_partitions: int = Field(1, ge=1, le=32, description="Number of parallel partitions to load")
    limit: Optional[int] = Field(None, description="Limit rows to fetch")
    mode: str = Field("materialize", description="'materialize' (ConnectorX, default) or 'scanner' (DuckDB ATTACH + pushdown, PG/MySQL)")

class EDARequest(BaseModel):
    session_id: str
    dataset_name: str

class CorrelationRequest(BaseModel):
    session_id: str
    dataset_name: str
    columns: Optional[List[str]] = None
    method: str = Field("pearson", description="'pearson' or 'spearman'")
    group_col: Optional[str] = Field(None, description="Optional group column. Opposite within-group correlation is reported as a Simpson caveat.")

class OLAPRequest(BaseModel):
    session_id: str
    dataset_name: str
    dimensions: List[str] = Field(..., description="Group by dimension columns")
    metrics: List[str] = Field(..., description="Aggregated measure columns")
    agg_funcs: Optional[List[str]] = Field(None, description="Aggregation functions matching metrics (e.g. ['sum', 'avg'])")
    filters: Optional[str] = None
    rollup: bool = False
    cube: bool = False
    order_by: Optional[str] = None
    limit: int = 100

class PivotRequest(BaseModel):
    session_id: str
    dataset_name: str
    rows: List[str]
    columns: str
    values: str
    agg_func: str = "SUM"
    filters: Optional[str] = None
    limit: int = 100

class DriverAnalysisRequest(BaseModel):
    session_id: str
    dataset_name: str
    target_metric: str = Field(..., description="Metric to analyze, e.g. 'profit', 'sales'")
    dimension_path: List[str] = Field(..., description="Hierarchy of dimensions to drill down, e.g. ['region', 'category']")
    base_filter: str = Field(..., description="Baseline condition, e.g. 'month = 1'")
    current_filter: str = Field(..., description="Current condition, e.g. 'month = 2'")
    agg_func: str = "SUM"
    top_k: int = 5
    rate_col: Optional[str] = Field(None, description="Rate column. With volume_col, only the first dimension is a Laspeyres split plus a two-ordering Sun-Shapley.")
    volume_col: Optional[str] = Field(None, description="Volume column paired with rate_col. Later dimensions are not drilled.")

class HypothesisTestRequest(BaseModel):
    session_id: str
    dataset_name: str
    test_type: str = Field(..., description="'independent_t_test', 'paired_t_test', 'one_way_anova', 'two_way_anova', 'chi_square', 'mann_whitney'. one_way_anova and two_way_anova include variance_decomposition. mann_whitney requires exactly 2 groups.")
    dependent_var: str = Field(..., description="Dependent continuous or categorical variable. For paired_t_test, the first numeric column.")
    group_var: str = Field(..., description="Grouping column. For paired_t_test, the second numeric column. For two_way_anova, the first factor.")
    factor_b: Optional[str] = Field(None, description="Second factor column. Required for two_way_anova.")
    alpha: float = Field(0.05, description="Significance level")

class RegressionRequest(BaseModel):
    session_id: str
    dataset_name: str
    dependent_var: str
    independent_vars: List[str]
    model_type: str = Field("ols", description="'ols' or 'logistic'")

class OutliersRequest(BaseModel):
    session_id: str
    dataset_name: str
    metric: str
    dimension_cols: Optional[List[str]] = None
    method: str = Field("z_score", description="'z_score', 'iqr', 'isolation_forest'")
    threshold: float = 3.0
    top_k: int = 10

class TrendsRequest(BaseModel):
    session_id: str
    dataset_name: str
    time_col: str
    metric: str
    group_col: Optional[str] = None

class VarianceDecompositionRequest(BaseModel):
    session_id: str
    dataset_name: str
    metric: str = Field(..., description="Numeric column. Must not also appear in dimensions.")
    dimensions: List[str] = Field(..., description="At least one categorical dimension. Names must be unique.")
    filters: Optional[str] = Field(None, description="WHERE fragment passed through safe_predicate.")

class DominanceRequest(BaseModel):
    session_id: str
    dataset_name: str
    category_col: str
    metric: str
    top_k: int = 5

class ClusteringRequest(BaseModel):
    session_id: str
    dataset_name: str
    feature_cols: List[str]
    n_clusters: Optional[int] = None
    auto_k_range: List[int] = [2, 6]

class TimeSeriesRequest(BaseModel):
    session_id: str
    dataset_name: str
    time_col: str
    value_col: str
    horizon: int = 12
    model_type: str = "arima"

class SQLSandboxRequest(BaseModel):
    session_id: str
    sql_query: str
    limit: int = 100

class RFMRequest(BaseModel):
    session_id: str
    dataset_name: str
    user_col: str
    date_col: str
    amount_col: str

class InsightDiscoverRequest(BaseModel):
    session_id: str
    dataset_name: str
    intent: Optional[str] = None
    target_metric: Optional[str] = None
    category_col: Optional[str] = None
    time_col: Optional[str] = None
    max_insights: int = 8

class RunExampleRequest(BaseModel):
    session_id: Optional[str] = None

class FunnelRequest(BaseModel):
    session_id: str
    dataset_name: str
    steps: List[str]
    date_from: Optional[str] = None
    date_to: Optional[str] = None

class SemanticQueryRequest(BaseModel):
    session_id: str
    metric_names: List[str]
    dimensions: Optional[List[str]] = None
    filters: Optional[str] = None
    order_by: Optional[str] = None
    limit: int = 100

class CleanTableRequest(BaseModel):
    session_id: str
    source_table: str
    target_table: str
    dedup_keys: Optional[List[str]] = None
    fillna_rules: Optional[Dict[str, Any]] = None
    outlier_clip_cols: Optional[Dict[str, Dict[str, float]]] = None

class ReverseSyncRequest(BaseModel):
    session_id: str
    source_table: str
    dest_conn_str: str
    dest_table_name: str
    mode: str = "replace"
    chunk_size: int = Field(50000, description="Arrow batch size for database destinations. Must be >= 1.")

class WideTableRequest(BaseModel):
    session_id: str
    target_name: str
    fact_table: str
    dimension_joins: List[Dict[str, Any]]

class AudienceExportRequest(BaseModel):
    session_id: str
    source_table: str
    filter_sql: Optional[str] = None
    export_columns: Optional[List[str]] = None
    format_type: str = "json"
    limit: int = 1000

class WebhookAlertRequest(BaseModel):
    webhook_url: str
    title: str
    message: str
    platform: str = "generic"
    extra_metrics: Optional[Dict[str, Any]] = None

class QualitySuiteRequest(BaseModel):
    session_id: str
    table: str
    rules: List[Dict[str, Any]]

class SchemaDriftRequest(BaseModel):
    session_id: str
    table: str
    baseline_schema: Dict[str, str]

class OntologyQueryRequest(BaseModel):
    session_id: str
    object_type: str
    filters: Optional[str] = None
    properties: Optional[List[str]] = None
    limit: int = 50

class OntologyTraverseRequest(BaseModel):
    session_id: str
    source_object_type: str
    source_instance_id: Any
    link_name: str
    limit: int = 50
    link_path: Optional[List[str]] = None
    max_hops: int = 4

class OntologyActionExecRequest(BaseModel):
    session_id: str
    action_name: str
    instance_id: Any
    parameters: Dict[str, Any]
    dry_run: bool = False

class TraceImportRequest(BaseModel):
    source: Optional[str] = None
    records: Optional[List[Dict[str, Any]]] = None
    dataset_name: str = "traces"
    session_id: Optional[str] = None
    format: Optional[str] = None
