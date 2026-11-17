import time
from typing import List, Optional
from pydantic import BaseModel, Field

from app.ontology.object_type import PropertyMeta


class InterfaceType(BaseModel):
    """
    Palantir-style Ontology Interface:
    Defines an abstract, polymorphic contract of shared properties that multiple ObjectTypes
    can implement (e.g. 'SchedulableAsset', 'AuditableTransaction', 'Party').
    Supports multi-level interface inheritance via `extends`.
    """
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = ""
    required_properties: List[PropertyMeta] = Field(default_factory=list)
    extends: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
