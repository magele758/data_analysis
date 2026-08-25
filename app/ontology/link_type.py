import time
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

class LinkType(BaseModel):
    name: str # e.g. "customer_orders", "order_items", "order_warehouse"
    display_name: Optional[str] = None
    description: Optional[str] = ""
    source_object_type: str # e.g. "Customer"
    target_object_type: str # e.g. "Order"
    cardinality: str = "ONE_TO_MANY" # ONE_TO_ONE, ONE_TO_MANY, MANY_TO_ONE, MANY_TO_MANY
    # Join specification: how source table relates to target table
    source_join_key: str # e.g. "customer_id" in Customer
    target_join_key: str # e.g. "customer_id" in Order
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
