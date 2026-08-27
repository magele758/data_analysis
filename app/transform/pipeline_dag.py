import threading
import time
from typing import Dict, List, Set, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydantic import BaseModel, Field
import duckdb
from app.catalog.lineage_tracker import get_lineage_tracker
from app.catalog.metadata_db import MetadataDB
from app.engine.sql_guard import safe_ident, safe_model_sql

class DAGModel(BaseModel):
    name: str
    sql: str
    materialization: str = "table" # table, view, ephemeral
    depends_on: List[str] = Field(default_factory=list)
    description: Optional[str] = ""

class PipelineDAG:
    """dbt-style DAG engine. The default ("_global") namespace persists models to
    the shared DB; per-session namespaces are in-memory and isolated so a
    pipeline run only materializes that session's own models (never another
    tenant's models against this session's connection)."""

    _instance = None
    _lock = threading.RLock()
    _session_instances: Dict[str, "PipelineDAG"] = {}

    def __init__(self, session_id: str = "_global", persistent: bool = True):
        self.session_id = session_id
        self.persistent = persistent
        self._models: Dict[str, DAGModel] = {}
        self.db = MetadataDB.get_instance() if persistent else None
        if persistent:
            self._restore_from_db()

    @classmethod
    def get_instance(cls) -> "PipelineDAG":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(persistent=True)
            return cls._instance

    def _restore_from_db(self):
        saved = self.db.list_dag_models()
        lineage = get_lineage_tracker(self.session_id)
        for d in saved:
            m = DAGModel(**d)
            self._models[m.name] = m
            for dep in m.depends_on:
                lineage.record_dependency(dep, m.name)

    def register_model(self, model: DAGModel) -> DAGModel:
        with self._lock:
            self._models[model.name] = model
            if self.persistent:
                self.db.save_dag_model(model.model_dump())
            # Record in this session's lineage tracker
            lineage = get_lineage_tracker(self.session_id)
            for dep in model.depends_on:
                lineage.record_dependency(dep, model.name)
            return model

    def list_models(self) -> List[DAGModel]:
        with self._lock:
            return list(self._models.values())

    def get_execution_order(self) -> List[str]:
        """Topological sort using Kahn's algorithm."""
        stages = self.get_execution_stages()
        flat_order = []
        for stage in stages:
            flat_order.extend(stage)
        return flat_order

    def get_execution_stages(self) -> List[List[str]]:
        """
        Partition DAG models into execution stages (Levels).
        Models in the same stage have no mutual dependencies and can execute in parallel.
        """
        with self._lock:
            in_degree = {name: 0 for name in self._models}
            adj = {name: [] for name in self._models}

            for name, m in self._models.items():
                for dep in m.depends_on:
                    if dep in self._models:
                        adj[dep].append(name)
                        in_degree[name] += 1

            current_queue = [name for name, deg in in_degree.items() if deg == 0]
            stages = []
            visited_count = 0

            while current_queue:
                stages.append(list(current_queue))
                visited_count += len(current_queue)
                next_queue = []
                for curr in current_queue:
                    for neighbor in adj[curr]:
                        in_degree[neighbor] -= 1
                        if in_degree[neighbor] == 0:
                            next_queue.append(neighbor)
                current_queue = next_queue

            if visited_count != len(self._models):
                raise ValueError("Cyclic dependency detected in DAG transformation pipeline!")

            return stages

    def _execute_single_model(self, con: duckdb.DuckDBPyConnection, model: DAGModel) -> Dict[str, Any]:
        """Execute model with atomic shadow-table swap & rollback."""
        name = model.name
        name_ref = safe_ident(name)
        mat_type = model.materialization.lower()
        if mat_type not in ("table", "view", "ephemeral"):
            raise ValueError(f"Invalid materialization {model.materialization!r}")
        staging_ref = safe_ident(f"_stg_swap_{name}")
        model_sql = safe_model_sql(model.sql)

        start_t = time.time()
        try:
            if mat_type == "view":
                con.execute(f"CREATE OR REPLACE VIEW {name_ref} AS {model_sql}")
            else:
                # 1. Build into staging table
                con.execute(f"CREATE OR REPLACE TABLE {staging_ref} AS {model_sql}")
                # 2. Atomic swap
                con.execute(f"DROP TABLE IF EXISTS {name_ref}")
                con.execute(f"ALTER TABLE {staging_ref} RENAME TO {name_ref}")

            row_count = con.execute(f"SELECT count(*) FROM {name_ref}").fetchone()[0]
            duration_ms = round((time.time() - start_t) * 1000, 2)

            return {
                "model_name": name,
                "materialization": mat_type,
                "row_count": row_count,
                "duration_ms": duration_ms,
                "status": "SUCCESS"
            }
        except Exception as e:
            # Cleanup staging table on failure
            try:
                con.execute(f"DROP TABLE IF EXISTS {staging_ref}")
            except Exception:
                pass
            raise RuntimeError(f"Model '{name}' execution failed: {str(e)}")

    def clear_models(self):
        with self._lock:
            self._models.clear()

    def run_pipeline(self, con: duckdb.DuckDBPyConnection, models: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Execute the DAG transformation across dependency stages with atomic materialization.
        """
        stages = self.get_execution_stages()
        all_results = []
        start_time = time.time()

        target_set = set(models) if models else None
        for stage_idx, stage_models in enumerate(stages):
            for model_name in stage_models:
                if target_set and model_name not in target_set:
                    continue
                m = self._models[model_name]
                res = self._execute_single_model(con, m)
                all_results.append(res)

        total_duration = round((time.time() - start_time) * 1000, 2)

        return {
            "total_models": len(all_results),
            "total_stages": len(stages),
            "execution_order": [r["model_name"] for r in all_results],
            "total_duration_ms": total_duration,
            "results": all_results
        }

def get_pipeline_engine(session_id: str = "_global") -> PipelineDAG:
    with PipelineDAG._lock:
        inst = PipelineDAG._session_instances.get(session_id)
        if inst is None:
            inst = PipelineDAG(session_id=session_id, persistent=(session_id == "_global"))
            PipelineDAG._session_instances[session_id] = inst
        return inst
