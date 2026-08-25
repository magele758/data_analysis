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
    summary_text: str = Field(..., description="High-density deterministic natural language summary for LLM context")
    insights: List[InsightItem] = Field(default_factory=list)
    statistics: Optional[Dict[str, Any]] = None
    data_preview: Optional[List[Dict[str, Any]]] = None
    chart_spec: Optional[Dict[str, Any]] = Field(None, description="Vega-Lite / ECharts declarative visual spec")
    metadata: Dict[str, Any] = Field(default_factory=dict)
