from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class InsightItem(BaseModel):
    type: str  # driver, outlier, trend, dominance, anomaly
    title: str
    summary: str
    significance_score: float = 1.0
    details: Dict[str, Any] = {}

class StatSummary(BaseModel):
    test_name: Optional[str] = None
    statistic_value: Optional[float] = None
    p_value: Optional[float] = None
    significant: Optional[bool] = None
    effect_size: Optional[Dict[str, Any]] = None

class AnalysisResponse(BaseModel):
    status: str = "success"
    session_id: Optional[str] = None
    summary_text: str = Field(..., description="HTTP narrative from NarrativeBuilder. MCP tools expose the same text as summary.")
    insights: List[InsightItem] = Field(default_factory=list)
    statistics: Optional[Dict[str, Any]] = None
    data_preview: Optional[List[Dict[str, Any]]] = None
    chart_spec: Optional[Dict[str, Any]] = Field(None, description="Vega-Lite v5 ($schema) or ECharts option. Driver waterfall, forecast, funnel, retention heatmap, and user-flow sankey attach one.")
    metadata: Dict[str, Any] = Field(default_factory=dict)

class BusinessReportResponse(BaseModel):
    session_id: str
    dataset_name: str
    summary: str
    statistics: Dict[str, Any]
    series: List[Dict[str, Any]]
    dimensions: List[Dict[str, Any]]
    anomalies: List[Dict[str, Any]]
    profit_bridge: List[Dict[str, Any]] = Field(default_factory=list)
    checks: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    skipped: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)

class ToolEvidence(BaseModel):
    schema_version: str = '2.0'
    operator: str
    method: str
    session_id: str
    dataset_name: str
    parameters: Dict[str, Any]
    population: Dict[str, Any]
    metric_semantics: Dict[str, Any]
    time_semantics: Dict[str, Any]
    assumptions: List[str]
    warnings: List[str]
    truncation: Dict[str, Any]
    sql: List[str]
    query_sha256: str
    duration_ms: float
    causal_claim: bool = False

class AnalyticalToolResponse(BaseModel):
    status: str = 'success'
    summary: str
    result: Dict[str, Any]
    evidence: ToolEvidence

class OrderInvestigationResponse(AnalyticalToolResponse):
    """Evidence v2; result includes categories, orders, line_evidence and reconciliation.

    Category contributions cover all scoped order-periods; order_ids limits details only.
    Checks-passed labels are provisional, never a claim of business approval.
    """
    result: Dict[str, Any] = Field(description="comparison, categories (mutually exclusive contributions), reconciliation, orders (flags and drilldown requests), line_evidence, line_evidence_truncated, next_checks")

class OrderReconciliationResponse(AnalyticalToolResponse):
    result: Dict[str, Any] = Field(description='comparison, selection, orders, line_evidence, tax_fee_status, duplicate_id_status, profit_bridges, effect_changes, exclusion_summary, skipped; evidence hypotheses are not verified root causes')

class DiscountDriversResponse(AnalyticalToolResponse):
    result: Dict[str, Any] = Field(description='original_comparison, comparison (retained scope), selection, excluded_order_ids, profit_bridge, views (within-SKU rate/structure contributions and closure), focus (stable-reference cells and orders)')

class DiscountOrderAuditResponse(AnalyticalToolResponse):
    result: Dict[str, Any] = Field(description='original_comparison, selection, audit_summary, orders with priorities/drilldown, breakdown, reference_coverage, priority_rules, focus; burden is a current-volume benchmark, not period-change attribution')

class DiscountScenarioResponse(AnalyticalToolResponse):
    result: Dict[str, Any] = Field(description='scenario_selection, scenarios, product_scenarios, scenario_orders with break-even and restore uplift, scenario_lines, variable_cost_share, risk_frontiers (bounded preserve-profit/nonloss limits, algebraic roots and initial-loss status), robustness (all configured cost cases and products), next_checks; demand stress is assumed, not forecast')
