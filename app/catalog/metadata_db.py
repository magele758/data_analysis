import sqlite3
import threading
import json
import os
import time
from typing import Dict, List, Any, Optional
from contextlib import contextmanager

class MetadataDB:
    _instance = None
    _lock = threading.RLock()

    def __init__(self, db_path: str = "data/catalog_metadata.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_tables()

    @classmethod
    def get_instance(cls) -> "MetadataDB":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        with self._get_conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS catalog_tables (
                dataset_name TEXT PRIMARY KEY,
                display_name TEXT,
                description TEXT,
                table_type TEXT,
                owner TEXT,
                tags_json TEXT,
                row_count INTEGER,
                column_count INTEGER,
                columns_json TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS semantic_metrics (
                name TEXT PRIMARY KEY,
                display_name TEXT,
                description TEXT,
                table_name TEXT,
                formula TEXT,
                aggregation_type TEXT,
                dimensions_json TEXT,
                filter_expr TEXT,
                format TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS dag_models_meta (
                name TEXT PRIMARY KEY,
                sql TEXT,
                materialization TEXT,
                depends_on_json TEXT,
                description TEXT,
                updated_at TEXT
            );
            """)

    # --- Table Asset Methods ---
    def save_table_asset(self, asset_dict: Dict[str, Any]):
        with self._lock:
            with self._get_conn() as conn:
                now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                conn.execute("""
                INSERT INTO catalog_tables (
                    dataset_name, display_name, description, table_type, owner,
                    tags_json, row_count, column_count, columns_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_name) DO UPDATE SET
                    display_name=excluded.display_name,
                    description=excluded.description,
                    table_type=excluded.table_type,
                    owner=excluded.owner,
                    tags_json=excluded.tags_json,
                    row_count=excluded.row_count,
                    column_count=excluded.column_count,
                    columns_json=excluded.columns_json,
                    updated_at=excluded.updated_at
                """, (
                    asset_dict["dataset_name"],
                    asset_dict.get("display_name"),
                    asset_dict.get("description", ""),
                    asset_dict.get("table_type", "TABLE"),
                    asset_dict.get("owner", "admin"),
                    json.dumps(asset_dict.get("tags", [])),
                    asset_dict.get("row_count", 0),
                    asset_dict.get("column_count", 0),
                    json.dumps([c if isinstance(c, dict) else c.model_dump() for c in asset_dict.get("columns", [])]),
                    asset_dict.get("created_at") or now_str,
                    asset_dict.get("updated_at") or now_str
                ))

    def get_table_asset(self, dataset_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with self._get_conn() as conn:
                row = conn.execute("SELECT * FROM catalog_tables WHERE dataset_name=?", (dataset_name,)).fetchone()
                if not row:
                    return None
                return self._row_to_asset(row)

    def list_table_assets(self) -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_conn() as conn:
                rows = conn.execute("SELECT * FROM catalog_tables ORDER BY updated_at DESC").fetchall()
                return [self._row_to_asset(r) for r in rows]

    def _row_to_asset(self, r: sqlite3.Row) -> Dict[str, Any]:
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {
            "dataset_name": r["dataset_name"],
            "display_name": r["display_name"],
            "description": r["description"],
            "table_type": r["table_type"],
            "owner": r["owner"],
            "tags": json.loads(r["tags_json"] or "[]"),
            "row_count": r["row_count"],
            "column_count": r["column_count"],
            "columns": json.loads(r["columns_json"] or "[]"),
            "created_at": r["created_at"] or now_str,
            "updated_at": r["updated_at"] or now_str
        }

    # --- Semantic Metric Methods ---
    def save_metric(self, metric_dict: Dict[str, Any]):
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("""
                INSERT INTO semantic_metrics (
                    name, display_name, description, table_name, formula,
                    aggregation_type, dimensions_json, filter_expr, format, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(name) DO UPDATE SET
                    display_name=excluded.display_name,
                    description=excluded.description,
                    table_name=excluded.table_name,
                    formula=excluded.formula,
                    aggregation_type=excluded.aggregation_type,
                    dimensions_json=excluded.dimensions_json,
                    filter_expr=excluded.filter_expr,
                    format=excluded.format
                """, (
                    metric_dict["name"],
                    metric_dict.get("display_name"),
                    metric_dict.get("description", ""),
                    metric_dict["table_name"],
                    metric_dict["formula"],
                    metric_dict.get("aggregation_type", "SUM"),
                    json.dumps(metric_dict.get("dimensions", [])),
                    metric_dict.get("filter_expr"),
                    metric_dict.get("format", "number")
                ))

    def get_metric(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with self._get_conn() as conn:
                row = conn.execute("SELECT * FROM semantic_metrics WHERE name=?", (name,)).fetchone()
                if not row:
                    return None
                return self._row_to_metric(row)

    def list_metrics(self) -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_conn() as conn:
                rows = conn.execute("SELECT * FROM semantic_metrics").fetchall()
                return [self._row_to_metric(r) for r in rows]

    def _row_to_metric(self, r: sqlite3.Row) -> Dict[str, Any]:
        return {
            "name": r["name"],
            "display_name": r["display_name"],
            "description": r["description"],
            "table_name": r["table_name"],
            "formula": r["formula"],
            "aggregation_type": r["aggregation_type"],
            "dimensions": json.loads(r["dimensions_json"] or "[]"),
            "filter_expr": r["filter_expr"],
            "format": r["format"]
        }

    # --- DAG Model Methods ---
    def save_dag_model(self, model_dict: Dict[str, Any]):
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("""
                INSERT INTO dag_models_meta (name, sql, materialization, depends_on_json, description, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(name) DO UPDATE SET
                    sql=excluded.sql,
                    materialization=excluded.materialization,
                    depends_on_json=excluded.depends_on_json,
                    description=excluded.description,
                    updated_at=excluded.updated_at
                """, (
                    model_dict["name"],
                    model_dict["sql"],
                    model_dict.get("materialization", "table"),
                    json.dumps(model_dict.get("depends_on", [])),
                    model_dict.get("description", "")
                ))

    def list_dag_models(self) -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_conn() as conn:
                rows = conn.execute("SELECT * FROM dag_models_meta").fetchall()
                return [{
                    "name": r["name"],
                    "sql": r["sql"],
                    "materialization": r["materialization"],
                    "depends_on": json.loads(r["depends_on_json"] or "[]"),
                    "description": r["description"]
                } for r in rows]
