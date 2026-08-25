import time
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

class PropertyMeta(BaseModel):
    name: str
    data_type: str # string, integer, float, timestamp, boolean
    description: Optional[str] = ""
    is_primary_key: bool = False
    is_title: bool = False
    formula: Optional[str] = None # Optional calculated/virtual property

class ObjectType(BaseModel):
    name: str # e.g. "Customer", "Order", "Product", "Flight", "Warehouse"
    display_name: Optional[str] = None
    description: Optional[str] = ""
    primary_key: str # e.g. "customer_id", "order_id"
    title_property: Optional[str] = None # property used as display label
    backed_by_table: str # Underlying DuckDB / SQL table name
    properties: List[PropertyMeta] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
