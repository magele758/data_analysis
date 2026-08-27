import threading
import time
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from app.catalog.metadata_db import MetadataDB

class ColumnMeta(BaseModel):
    name: str
    data_type: str
    semantic_type: str = "DIMENSION" # MEASURE, DIMENSION, IDENTIFIER, TEMPORAL
    description: Optional[str] = ""
    is_primary_key: bool = False
    is_nullable: bool = True
    tags: List[str] = Field(default_factory=list)

class TableAsset(BaseModel):
    dataset_name: str
    display_name: Optional[str] = None
    description: Optional[str] = ""
    table_type: str = "TABLE" # TABLE, VIEW, MARTS, STAGING
    owner: str = "admin"
    tags: List[str] = Field(default_factory=list)
    row_count: int = 0
    column_count: int = 0
    columns: List[ColumnMeta] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

class MetaRegistry:
    """Data Catalog registry. The default ("_global") namespace is DB-backed and
    shared; a per-session namespace keeps assets in-memory and isolated so
    multiple tenants/sessions do not see each other's datasets."""

    _instance = None
    _lock = threading.RLock()
    _session_instances: Dict[str, "MetaRegistry"] = {}

    def __init__(self, persistent: bool = True):
        self.persistent = persistent
        self.db = MetadataDB.get_instance() if persistent else None
        self._assets: Dict[str, TableAsset] = {}

    @classmethod
    def get_instance(cls) -> "MetaRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(persistent=True)
            return cls._instance

    def register_table(self, asset: TableAsset) -> TableAsset:
        with self._lock:
            asset.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if self.persistent:
                self.db.save_table_asset(asset.model_dump())
            else:
                self._assets[asset.dataset_name] = asset
            return asset

    def get_table(self, dataset_name: str) -> Optional[TableAsset]:
        with self._lock:
            if self.persistent:
                data = self.db.get_table_asset(dataset_name)
                return TableAsset(**data) if data else None
            return self._assets.get(dataset_name)

    def list_tables(self, tag: Optional[str] = None, keyword: Optional[str] = None) -> List[TableAsset]:
        with self._lock:
            if self.persistent:
                assets = [TableAsset(**d) for d in self.db.list_table_assets()]
            else:
                assets = list(self._assets.values())
            if tag:
                assets = [a for a in assets if tag in a.tags]
            if keyword:
                kw = keyword.lower()
                assets = [a for a in assets if kw in a.dataset_name.lower() or kw in (a.description or "").lower()]
            return assets

    def delete_table(self, dataset_name: str) -> bool:
        with self._lock:
            if not self.persistent:
                self._assets.pop(dataset_name, None)
            return True

def get_meta_registry(session_id: str = "_global") -> MetaRegistry:
    with MetaRegistry._lock:
        inst = MetaRegistry._session_instances.get(session_id)
        if inst is None:
            inst = MetaRegistry(persistent=(session_id == "_global"))
            MetaRegistry._session_instances[session_id] = inst
        return inst
