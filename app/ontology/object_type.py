import time
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class PropertyMeta(BaseModel):
    name: str
    data_type: str  # string, integer, float, timestamp, boolean, json
    description: Optional[str] = ""
    is_primary_key: bool = False
    is_title: bool = False
    formula: Optional[str] = None  # Optional calculated/virtual property
    # Closed-world (CWA / SHACL-style) ontological constraints
    required: bool = False
    unique: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    # Fine-grained governance & column-level masking
    sensitive: bool = False
    allowed_roles: List[str] = Field(default_factory=list)


class ObjectType(BaseModel):
    name: str  # e.g. "Customer", "Order", "Product", "Flight", "Warehouse"
    display_name: Optional[str] = None
    description: Optional[str] = ""
    primary_key: str  # e.g. "customer_id", "order_id"
    title_property: Optional[str] = None  # property used as display label
    backed_by_table: str  # Underlying DuckDB / SQL table name
    properties: List[PropertyMeta] = Field(default_factory=list)
    # Polymorphic interfaces (Palantir Interfaces)
    implements: List[str] = Field(default_factory=list)
    property_mappings: Dict[str, str] = Field(default_factory=dict)  # interface_prop -> object_prop
    # Formal ontological commitment (Guarino mutual exclusion axiom)
    disjoint_with: List[str] = Field(default_factory=list)
    # Default writeback dataset for overlay reads
    writeback_table: Optional[str] = None
    # Fine-grained RBAC governance
    allowed_roles: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
