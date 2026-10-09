from typing import Any, Dict, List, Optional

from app.cluster.session_manager import SessionManager
from app.distributed_ops.variance_decomp import VarianceDecomposition


def run_variance_decomposition(
    session_id: str,
    dataset_name: str,
    metric: str,
    dimensions: List[str],
    filters: Optional[str] = None,
) -> Dict[str, Any]:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")
    return VarianceDecomposition.decompose(
        sess.get_duckdb_conn(),
        dataset_name,
        metric,
        dimensions,
        filters,
    )
