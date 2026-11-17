import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


def utc_stamp() -> str:
    """UTC time with microseconds so two audits in the same second stay ordered."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ActionParameter(BaseModel):
    name: str
    data_type: str  # string, integer, float, boolean, json
    description: Optional[str] = ""
    required: bool = True
    default_value: Optional[Any] = None
    # Closed-world parameter value constraints
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    regex_pattern: Optional[str] = None


class ActionPrecondition(BaseModel):
    """
    Closed-world (CWA) state precondition evaluated against the target instance before
    an ActionType is allowed to execute (e.g. "status = 'PENDING' AND amount <= 10000").
    """
    name: str = "precondition"
    sql_predicate: str
    description: Optional[str] = ""


class ActionType(BaseModel):
    name: str  # e.g. "ApplyDiscountAction", "RerouteShipmentAction", "SendRetentionCouponAction"
    display_name: Optional[str] = None
    description: Optional[str] = ""
    target_object_type: str  # Entity type or InterfaceType this action operates upon
    target_interface: Optional[str] = None  # Explicit polymorphic interface target
    parameters: List[ActionParameter] = Field(default_factory=list)
    preconditions: List[ActionPrecondition] = Field(default_factory=list)
    allowed_roles: List[str] = Field(default_factory=list)
    handler_type: str = "WEBHOOK"  # WEBHOOK, REVERSE_ETL_SYNC, SQL_MUTATION, FUNCTION
    handler_config: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


class FunctionType(BaseModel):
    """
    Palantir-style 'Function on Objects' (FoO):
    Deterministic calculation/simulation mounted on an ObjectType or InterfaceType.
    Evaluates `sql_expression` over entity properties and typed parameters in DuckDB.
    """
    name: str  # e.g. "ComputeOrderRiskScore", "SimulateRetentionCredit"
    display_name: Optional[str] = None
    description: Optional[str] = ""
    target_object_type: str  # ObjectType or InterfaceType name
    parameters: List[ActionParameter] = Field(default_factory=list)
    sql_expression: str  # e.g. "balance * {rate} + CASE WHEN tier = 'VIP' THEN 100 ELSE 0 END"
    return_type: str = "float"  # string, integer, float, boolean, json
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


class ActionExecutionAudit(BaseModel):
    audit_id: str
    action_name: str
    target_object_type: str
    target_instance_id: str
    parameters: Dict[str, Any]
    status: str  # SUCCESS, FAILED, SIMULATED
    actor_role: Optional[str] = None
    precondition_results: List[Dict[str, Any]] = Field(default_factory=list)
    execution_result: Dict[str, Any] = Field(default_factory=dict)
    executed_at: str = Field(default_factory=utc_stamp)
