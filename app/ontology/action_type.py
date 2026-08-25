import time
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

class ActionParameter(BaseModel):
    name: str
    data_type: str # string, integer, float, boolean, json
    description: Optional[str] = ""
    required: bool = True
    default_value: Optional[Any] = None

class ActionType(BaseModel):
    name: str # e.g. "ApplyDiscountAction", "RerouteShipmentAction", "SendRetentionCouponAction"
    display_name: Optional[str] = None
    description: Optional[str] = ""
    target_object_type: str # The entity type this action operates upon (e.g. "Customer", "Order")
    parameters: List[ActionParameter] = Field(default_factory=list)
    handler_type: str = "WEBHOOK" # WEBHOOK, REVERSE_ETL_SYNC, SQL_MUTATION
    handler_config: Dict[str, Any] = Field(default_factory=dict)
    # E.g. {"webhook_url": "http...", "platform": "feishu"} or {"sql_template": "UPDATE orders SET status = ..."}
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

class ActionExecutionAudit(BaseModel):
    audit_id: str
    action_name: str
    target_object_type: str
    target_instance_id: str
    parameters: Dict[str, Any]
    status: str # SUCCESS, FAILED, SIMULATED
    execution_result: Dict[str, Any] = Field(default_factory=dict)
    executed_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
