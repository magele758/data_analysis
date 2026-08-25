import threading
from typing import Dict, List, Set, Any, Optional
from pydantic import BaseModel, Field
import duckdb
from app.catalog.lineage_tracker import get_lineage_tracker

class DAGModel(BaseModel):
    name: str
    sql: str
    materialization: str = "table" # table, view, ephemeral
    depends_on: List[str] = Field(default_factory=list)
    description: Optional[str] = ""

class PipelineDAG:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._models: Dict[str, DAGModel] = {}

    @classmethod
    def get_instance(cls) -> "PipelineDAG":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def register_model(self, model: DAGModel) -> DAGModel:
        with self._lock:
            self._models[model.name] = model
            # Record in lineage tracker
            lineage = get_lineage_tracker()
            for dep in model.depends_on:
                lineage.record_dependency(dep, model.name)
            return model

    def list_models(self) -> List[DAGModel]:
        with self._lock:
            return list(self._models.values())

    def get_execution_order(self) -> List[str]:
        """Topological sort using Kahn's algorithm."""
        with self._lock:
            in_degree = {name: 0 for name in self._models}
            adj = {name: [] for name in self._models}

            for name, m in self._models.items():
                for dep in m.depends_on:
                    if dep in self._models:
                        adj[dep].append(name)
                        in_degree[name] += 1

            queue = [name for name, deg in in_degree.items() if deg == 0]
            order = []

            while queue:
                curr = queue.pop(0)
                order.append(curr)
                for neighbor in adj[curr]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            if len(order) != len(self._models):
                raise ValueError("Cyclic dependency detected in DAG transformation pipeline!")

            return order

    def run_pipeline(self, con: duckdb.DuckDBPyConnection) -> Dict[str, Any]:
        """Execute the entire DAG transformation in dependency order."""
        order = self.get_execution_order()
        results = []

        with self._lock:
            for model_name in order:
                m = self._models[model_name]
                mat_type = m.materialization.lower()
                
                if mat_type == "view":
                    con.execute(f"CREATE OR REPLACE VIEW {model_name} AS {m.sql}")
                else:
                    con.execute(f"CREATE OR REPLACE TABLE {model_name} AS {m.sql}")

                row_count = con.execute(f"SELECT count(*) FROM {model_name}").fetchone()[0]
                results.append({
                    "model_name": model_name,
                    "materialization": mat_type,
                    "row_count": row_count,
                    "status": "SUCCESS"
                })

        return {
            "total_models": len(order),
            "execution_order": order,
            "results": results
        }

def get_pipeline_engine() -> PipelineDAG:
    return PipelineDAG.get_instance()
