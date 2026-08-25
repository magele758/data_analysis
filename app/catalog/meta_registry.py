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
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self.db = MetadataDB.get_instance()

    @classmethod
    def get_instance(cls) -> "MetaRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def register_table(self, asset: TableAsset) -> TableAsset:
        with self._lock:
            asset.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self.db.save_table_asset(asset.model_dump())
            return asset

    def get_table(self, dataset_name: str) -> Optional[TableAsset]:
        with self._lock:
            data = self.db.get_table_asset(dataset_name)
            if not data:
                return None
            return TableAsset(**data)

    def list_tables(self, tag: Optional[str] = None, keyword: Optional[str] = None) -> List[TableAsset]:
        with self._lock:
            raw_list = self.db.list_table_assets()
            assets = [TableAsset(**d) for d in raw_list]
            if tag:
                assets = [a for a in assets if tag in a.tags]
            if keyword:
                kw = keyword.lower()
                assets = [a for a in assets if kw in a.dataset_name.lower() or kw in (a.description or "").lower()]
            return assets

    def delete_table(self, dataset_name: str) -> bool:
        with self._lock:
            # Persistent delete if needed
            return True

def get_meta_registry() -> MetaRegistry:
    return MetaRegistry.get_instance()
