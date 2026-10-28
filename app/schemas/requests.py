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
    endorsed_only: Optional[bool] = None

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
    endorsed_only: Optional[bool] = None

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

# Reusable evidence report: names are verified against the session table schema.
from datetime import date
from typing import Literal
from pydantic import model_validator

class ReportFieldMapping(BaseModel):
    product: Optional[str] = None
    quantity: Optional[str] = None
    price: Optional[str] = None
    discount: Optional[str] = None
    sales: Optional[str] = None
    cost: Optional[str] = None
    order: Optional[str] = None
    discount_scale: Literal[1, 100] = 1

class BusinessReportRequest(BaseModel):
    session_id: str
    dataset_name: str
    metric: str
    time_column: str
    dimensions: List[str] = Field(default_factory=list, max_length=2)
    grain: Literal['day', 'week', 'month', 'quarter', 'year'] = 'month'
    base_start: date
    base_end: date
    current_start: date
    current_end: date
    mapping: ReportFieldMapping = Field(default_factory=ReportFieldMapping)
    filters: Dict[str, str] = Field(default_factory=dict, max_length=8)
    filter_dimension: Optional[str] = None
    filter_value: Optional[str] = None

    @model_validator(mode='after')
    def validate_periods(self):
        if not self.base_start < self.base_end <= self.current_start < self.current_end:
            raise ValueError('日期必须满足 基期开始 < 基期结束 ≤ 当期开始 < 当期结束；结束日期不包含在内')
        if (self.current_end-self.base_start).days > 3653:
            raise ValueError('单次报告时间跨度不能超过十年，请缩小窗口')
        if self.grain == 'day' and (self.current_end-self.base_start).days > 2000:
            raise ValueError('日粒度最多2000天，请改用周/月或缩小窗口')
        if bool(self.filter_dimension) != (self.filter_value is not None):
            raise ValueError('下钻字段和值必须同时提供')
        return self

class ReportDiscoverRequest(BaseModel):
    session_id: str
    dataset_name: str
    grain: Literal['day', 'week', 'month', 'quarter', 'year'] = 'month'

# Typed contracts for external analytical clients. Legacy endpoints remain compatible.
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import ConfigDict

class MetricContract(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['sum', 'ratio', 'distinct_count', 'closing_balance']
    column: Optional[str] = None
    numerator: Optional[str] = None
    denominator: Optional[str] = None
    entity_keys: List[str] = Field(default_factory=list, max_length=5)
    unit: str = 'source_unit'

    @model_validator(mode='after')
    def check_kind(self):
        if self.kind == 'ratio':
            if not self.numerator or not self.denominator or self.column or self.entity_keys:
                raise ValueError('ratio requires numerator/denominator only; aggregate sums before dividing')
        elif not self.column or self.numerator or self.denominator:
            raise ValueError('metric requires column; numerator/denominator are only for ratio')
        if self.kind == 'closing_balance' and not self.entity_keys:
            raise ValueError('closing_balance requires entity_keys to select each entity latest observation')
        if self.kind != 'closing_balance' and self.entity_keys:
            raise ValueError('entity_keys only apply to closing_balance')
        return self

class TimeContract(BaseModel):
    model_config = ConfigDict(extra='forbid')
    column: str
    input_mode: Literal['date', 'aware_timestamp'] = 'date'
    timezone: str = 'UTC'
    grain: Literal['day','week','month','quarter','year'] = 'month'
    base_start: date
    base_end: date
    current_start: date
    current_end: date
    completeness: Literal['strict','warn'] = 'strict'
    complete_until: Optional[date] = None
    require_aligned: bool = True
    require_equal_buckets: bool = True

    @model_validator(mode='after')
    def check_time(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('timezone must be an IANA timezone')
        if not self.base_start < self.base_end <= self.current_start < self.current_end:
            raise ValueError('Require base_start < base_end <= current_start < current_end (end-exclusive)')
        if (self.current_end-self.base_start).days>3653:
            raise ValueError('Maximum comparison span is ten years')
        if self.grain=='day' and (self.current_end-self.base_start).days>2000:
            raise ValueError('Daily comparison is limited to 2000 days')
        if self.completeness=='strict' and (self.complete_until is None or self.complete_until<self.current_end):
            raise ValueError('Strict completeness requires an explicit complete_until watermark >= current_end; max observed date is not proof of completeness')
        return self

class MetricCompareRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session_id: str
    dataset_name: str
    metric: MetricContract
    time: TimeContract
    filters: Dict[str,str] = Field(default_factory=dict,max_length=8)
    invalid_rows: Literal['reject','exclude'] = 'reject'

class DecompositionRequest(MetricCompareRequest):
    mode: Literal['dimension','ratio','profit'] = 'dimension'
    dimension: Optional[str] = None
    mapping: ReportFieldMapping = Field(default_factory=ReportFieldMapping)
    top_k: int = Field(50,ge=1,le=500)

    @model_validator(mode='after')
    def compatible_method(self):
        if self.mode=='dimension' and (self.metric.kind!='sum' or not self.dimension):
            raise ValueError('Dimension additive contributions require sum and dimension; distinct counts, ratios and balances cannot be summed across groups')
        if self.mode=='ratio' and self.metric.kind!='ratio':
            raise ValueError('Ratio decomposition requires ratio metric')
        if self.mode=='profit':
            if self.metric.kind!='sum' or any(not getattr(self.mapping,k) for k in ['product','quantity','price','discount','sales','cost']):
                raise ValueError('Profit decomposition requires sum metric and complete product/quantity/price/discount/sales/cost mapping')
        return self

class SensitivityRequest(MetricCompareRequest):
    method: Literal['zscore','iqr','mad'] = 'mad'
    threshold: Optional[float] = Field(None,gt=0,allow_inf_nan=False)
    anomaly_column: str
    reference: Literal['base','pooled'] = 'base'
    group_by: Optional[str] = None
    removal: Literal['row','entity'] = 'row'
    entity_column: Optional[str] = None
    limit: int = Field(20,ge=1,le=500)

    @model_validator(mode='after')
    def entity_required(self):
        if self.removal=='entity' and not self.entity_column:
            raise ValueError('Entity sensitivity requires entity_column')
        return self

class OrderInvestigationRequest(SensitivityRequest):
    mapping: ReportFieldMapping
    amount_tolerance: float = Field(0.01, ge=0, allow_inf_nan=False)
    discount_threshold: Optional[float] = Field(None, ge=0, le=1, allow_inf_nan=False)
    min_reference_rows: int = Field(5, ge=2)
    order_ids: List[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def order_mapping(self):
        if self.metric.kind != 'sum' or any(not getattr(self.mapping,k) for k in ['product','quantity','price','discount','sales','cost','order']):
            raise ValueError('Order investigation requires SUM profit and complete order/product/quantity/price/discount/sales/cost mapping')
        return self

class OrderReconciliationRequest(MetricCompareRequest):
    mapping: ReportFieldMapping
    order_ids: List[str] = Field(default_factory=list, max_length=100)
    line_id: Optional[str] = None
    adjustments: List[str] = Field(default_factory=list, max_length=8)
    amount_tolerance: float = Field(0.01, ge=0, allow_inf_nan=False)
    multipliers: List[float] = Field(default_factory=lambda:[0.01,0.1,10,100,1000], max_length=20)
    limit: int = Field(100, ge=1, le=500)

    @model_validator(mode='after')
    def validate_reconciliation(self):
        import math
        if self.metric.kind!='sum' or any(not getattr(self.mapping,k) for k in ['order','product','quantity','price','discount','sales','cost']):
            raise ValueError('Requires SUM profit and complete order/product/quantity/price/discount/sales/cost mapping')
        if any(not math.isfinite(v) or v<=0 or v==1 for v in self.multipliers):
            raise ValueError('Candidate multipliers must be finite positive values other than 1')
        if len(set(self.adjustments))!=len(self.adjustments):
            raise ValueError('Adjustment columns must not repeat')
        return self

class DiscountDriversRequest(MetricCompareRequest):
    mapping: ReportFieldMapping
    dimensions: List[str] = Field(default_factory=list, max_length=4)
    exclude_order_ids: List[str] = Field(default_factory=list, max_length=100)
    exclude_amount_mismatches: bool = True
    amount_tolerance: float = Field(0.01, ge=0, allow_inf_nan=False)
    top_k: int = Field(10, ge=1, le=100)
    focus_dimension: Optional[str] = None
    focus_member: Optional[str] = None

    @model_validator(mode='after')
    def validate_discount_drivers(self):
        if self.metric.kind!='sum' or any(not getattr(self.mapping,k) for k in ['order','product','quantity','price','discount','sales','cost']):
            raise ValueError('Discount drivers require SUM profit and complete order/product/quantity/price/discount/sales/cost mapping')
        if len(set(self.dimensions))!=len(self.dimensions):
            raise ValueError('dimensions must be unique')
        if bool(self.focus_dimension)!=(self.focus_member is not None):
            raise ValueError('focus_dimension and focus_member must be supplied together')
        if self.focus_dimension and self.focus_dimension not in [self.mapping.product,*self.dimensions]:
            raise ValueError('Focus dimension must be product or a requested dimension')
        return self

class DiscountOrderAuditRequest(MetricCompareRequest):
    mapping: ReportFieldMapping
    customer_column: str
    channel_column: str
    product_ids: List[str] = Field(default_factory=list, max_length=100)
    exclude_order_ids: List[str] = Field(default_factory=list, max_length=100)
    exclude_amount_mismatches: bool = True
    amount_tolerance: float = Field(0.01, ge=0, allow_inf_nan=False)
    min_reference_orders: int = Field(3, ge=1)
    materiality: float = Field(500, ge=0, allow_inf_nan=False)
    top_k: int = Field(20, ge=1, le=100)
    focus_order_id: Optional[str] = None
    focus_customer: Optional[str] = None
    focus_channel: Optional[str] = None

    @model_validator(mode='after')
    def validate_discount_order_audit(self):
        if self.metric.kind!='sum' or any(not getattr(self.mapping,k) for k in ['order','product','quantity','price','discount','sales','cost']):
            raise ValueError('Requires SUM profit and complete order/product/quantity/price/discount/sales/cost mapping')
        return self


class DiscountScenarioRequest(DiscountOrderAuditRequest):
    discount_caps: List[float] = Field(default_factory=lambda:[.1,.2,.3,.35], min_length=1, max_length=12)
    volume_reductions: List[float] = Field(default_factory=lambda:[0,.05,.1,.2], min_length=1, max_length=12)
    cost_share_cases: List[float] = Field(default_factory=lambda:[0,.5,1], min_length=1, max_length=5)
    robustness_volume_drop: float = Field(.2, ge=0, le=1, allow_inf_nan=False)
    variable_cost_share: float = Field(1, ge=0, le=1, allow_inf_nan=False)
    order_ids: List[str] = Field(default_factory=list, max_length=100, description='Detail only; never limits scenario population')

    @model_validator(mode='after')
    def validate_scenario_rates(self):
        import math
        for values in (self.discount_caps,self.volume_reductions,self.cost_share_cases):
            if any(not math.isfinite(x) or x<0 or x>1 for x in values):
                raise ValueError('Scenario rates must be finite fractions between 0 and 1')
        return self


# --- Hex-inspired Context Studio, dbt Semantic YAML, Trail Playbooks & Health Schemas ---

class WorkspaceRuleRequest(BaseModel):
    session_id: str = "_global"
    system_rules: str = ""
    endorsed_only_default: bool = False
    naming_conventions: Dict[str, str] = Field(default_factory=dict)


class ContextGuideRequest(BaseModel):
    session_id: str = "_global"
    name: str
    title: str
    content: str
    scope: Literal["workspace", "table", "metric", "model"] = "workspace"
    target_names: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    endorsement_status: Literal["endorsed", "draft", "deprecated", "warning"] = "endorsed"


class EndorseAssetRequest(BaseModel):
    session_id: str = "_global"
    asset_type: Literal["table", "metric", "model", "guide"]
    name: str
    status: Literal["endorsed", "draft", "deprecated", "warning"] = "endorsed"
    endorsement_note: str = ""
    endorsed_by: Optional[str] = None


class ContextResolveRequest(BaseModel):
    session_id: str = "_global"
    dataset_name: Optional[str] = None
    metric_names: Optional[List[str]] = None
    endorsed_only: Optional[bool] = None


class DbtSemanticYamlImportRequest(BaseModel):
    session_id: str = "_global"
    yaml_content: str
    default_endorsement_status: Literal["endorsed", "draft", "deprecated", "warning"] = "endorsed"


class ExportPlaybookRequest(BaseModel):
    session_id: str
    title: str
    description: str = ""
    step_ids: Optional[List[str]] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    playbook_id: Optional[str] = None
    endorsement_status: Literal["endorsed", "draft", "deprecated", "warning"] = "endorsed"


class ReplayPlaybookRequest(BaseModel):
    playbook_id: str
    target_session_id: Optional[str] = None
    parameter_overrides: Dict[str, Any] = Field(default_factory=dict)
