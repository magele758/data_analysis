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

class HypothesisTestRequest(BaseModel):
    session_id: str
    dataset_name: str
    test_type: str = Field(..., description="'independent_t_test', 'paired_t_test', 'one_way_anova', 'chi_square', 'mann_whitney'")
    dependent_var: str = Field(..., description="Dependent continuous or categorical variable")
    group_var: str = Field(..., description="Independent grouping variable")
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
