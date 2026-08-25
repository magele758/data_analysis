import threading
import time
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

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
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._assets: Dict[str, TableAsset] = {}

    @classmethod
    def get_instance(cls) -> "MetaRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def register_table(self, asset: TableAsset) -> TableAsset:
        with self._lock:
            asset.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._assets[asset.dataset_name] = asset
            return asset

    def get_table(self, dataset_name: str) -> Optional[TableAsset]:
        with self._lock:
            return self._assets.get(dataset_name)

    def list_tables(self, tag: Optional[str] = None, keyword: Optional[str] = None) -> List[TableAsset]:
        with self._lock:
            res = list(self._assets.values())
            if tag:
                res = [a for a in res if tag in a.tags]
            if keyword:
                kw = keyword.lower()
                res = [a for a in res if kw in a.dataset_name.lower() or kw in (a.description or "").lower()]
            return res

    def delete_table(self, dataset_name: str) -> bool:
        with self._lock:
            if dataset_name in self._assets:
                del self._assets[dataset_name]
                return True
            return False

def get_meta_registry() -> MetaRegistry:
    return MetaRegistry.get_instance()
